"""Room inventory generator for the LUMI hotel dataset seeder.

Generates a complete room inventory for each of the 5 pilot properties based on
PROPERTY_PROFILES room counts and ROOM_TYPE_DISTRIBUTION percentages. Each room
item includes floor assignment, view, premium status, amenities, and a default
AVAILABLE status that is later reconciled by reconcile_room_status() after
reservations and work orders are generated.

Supports REQ-DS-2 (per-room detail), REQ-DS-9 (cross-table consistency via
room lookup dict), and REQ-DS-8 (deterministic generation).
"""

import logging
import os
from typing import Any, Dict, List, Tuple

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from dataset_generator.config import (
    PROPERTY_PROFILES,
    PROPERTY_VIEWS,
    ROOM_TYPE_DISTRIBUTION,
    ROOM_TYPE_FLOOR_RANGES,
)
from dataset_generator.writer import BatchWriter

logger = logging.getLogger(__name__)

# Amenity sets by room type - premium rooms have richer amenity lists
AMENITIES_BY_ROOM_TYPE: Dict[str, List[str]] = {
    "PENTHOUSE": [
        "minibar", "safe", "wifi", "jacuzzi", "private_terrace",
        "butler_service", "espresso_machine", "smart_tv", "robes",
    ],
    "SUITE": [
        "minibar", "safe", "wifi", "separate_living", "espresso_machine",
        "smart_tv", "robes", "bathrobes",
    ],
    "KING_DELUXE": [
        "minibar", "safe", "wifi", "smart_tv", "espresso_machine", "robes",
    ],
    "QUEEN_DELUXE": [
        "minibar", "safe", "wifi", "smart_tv", "iron",
    ],
    "KING_STANDARD": [
        "minibar", "safe", "wifi",
    ],
}

# Max occupancy by room type
MAX_OCCUPANCY_BY_ROOM_TYPE: Dict[str, int] = {
    "PENTHOUSE": 6,
    "SUITE": 4,
    "KING_DELUXE": 2,
    "QUEEN_DELUXE": 2,
    "KING_STANDARD": 2,
}

# Module-level DynamoDB client for UpdateItem in reconcile_room_status.
# Standard retry mode handles transient errors at the SDK level.
_dynamodb_client = boto3.client(
    "dynamodb",
    config=Config(retries={"mode": "standard"}),
)


def _compute_room_counts(total_rooms: int) -> Dict[str, int]:
    """Compute the number of rooms per type based on distribution percentages.

    Distributes totalRooms across room types using ROOM_TYPE_DISTRIBUTION.
    The last type (KING_STANDARD) absorbs any rounding remainder to ensure
    the sum equals totalRooms exactly.

    Args:
        total_rooms: Total number of rooms for the property.

    Returns:
        Dict mapping room type string to integer count.
    """
    # Ordered list ensures deterministic iteration and remainder assignment
    ordered_types: List[str] = [
        "PENTHOUSE", "SUITE", "KING_DELUXE", "QUEEN_DELUXE", "KING_STANDARD",
    ]

    counts: Dict[str, int] = {}
    allocated = 0

    for room_type in ordered_types[:-1]:
        count = round(total_rooms * ROOM_TYPE_DISTRIBUTION[room_type])
        counts[room_type] = count
        allocated += count

    # KING_STANDARD absorbs the rounding remainder
    counts["KING_STANDARD"] = total_rooms - allocated
    return counts


def _assign_floor(room_type: str, room_index_within_type: int, count_for_type: int) -> int:
    """Assign a floor number to a room based on its type and position.

    Rooms are distributed evenly across the floor range for their type.
    The floor is determined by the room's index within its type group
    mapped proportionally across the available floor range.

    Args:
        room_type: One of the 5 room type strings (e.g., "KING_DELUXE").
        room_index_within_type: Zero-based index of this room within its type.
        count_for_type: Total number of rooms of this type for the property.

    Returns:
        Integer floor number within the type's floor range.
    """
    start_floor, end_floor = ROOM_TYPE_FLOOR_RANGES[room_type]
    floor_span = end_floor - start_floor + 1

    # Distribute rooms evenly across the floor range
    if count_for_type <= floor_span:
        # Fewer rooms than floors - one room per floor starting from start_floor
        floor = start_floor + (room_index_within_type % floor_span)
    else:
        # More rooms than floors - distribute proportionally
        floor = start_floor + (room_index_within_type * floor_span // count_for_type)

    return floor


def _assign_view(property_id: str, room_index: int, floor: int) -> str:
    """Assign a view based on property view list, room index, and floor.

    Higher floors and even-indexed rooms get premium views (earlier in the
    property's view list). The view is selected by cycling through the
    property's available views based on a combined index.

    Args:
        property_id: The property identifier (e.g., "ALOHA-CHI-001").
        room_index: Zero-based global room index within the property.
        floor: The assigned floor number for this room.

    Returns:
        View string from the property's PROPERTY_VIEWS list.
    """
    views = PROPERTY_VIEWS[property_id]
    # Higher floors bias toward premium views (lower index in list)
    # Use a combined score: floor contribution + room index rotation
    view_index = (room_index + floor) % len(views)
    return views[view_index]


def _is_premium_room(room_type: str, floor: int) -> bool:
    """Determine if a room qualifies as premium.

    Premium rooms are SUITE, PENTHOUSE, or KING_DELUXE on floors >= 15.
    This is used for VIP assignment and work order priority escalation.

    Args:
        room_type: The room's type classification.
        floor: The room's floor number.

    Returns:
        True if the room is considered premium, False otherwise.
    """
    if room_type in ("SUITE", "PENTHOUSE"):
        return True
    if room_type == "KING_DELUXE" and floor >= 15:
        return True
    return False


def _generate_room_number(floor: int, sequence: int) -> str:
    """Generate a room number string from floor and sequence.

    Room number follows the pattern: floor * 100 + sequence.
    For example, floor 12, sequence 3 produces "1203".

    Args:
        floor: The floor number (2-24).
        sequence: The room's sequence number on that floor (1-based).

    Returns:
        String room number (e.g., "1203").
    """
    return str(floor * 100 + sequence)


def generate_rooms(writer: BatchWriter) -> Dict[str, List[Dict[str, Any]]]:
    """Generate full room inventory for all 5 pilot properties.

    Iterates over PROPERTY_PROFILES and generates totalRooms items per property,
    distributed across room types per ROOM_TYPE_DISTRIBUTION. All rooms start
    with AVAILABLE status. The returned lookup dict is used by reservations and
    work orders generators to reference valid room numbers.

    Args:
        writer: BatchWriter instance configured for the stayos-rooms table.
            Used to write generated items to DynamoDB in batches of 25.

    Returns:
        Dict keyed by propertyId, where each value is a list of room item
        dicts. Each room dict contains all DynamoDB attributes for that room.
        Structure: Dict[str, List[Dict[str, Any]]]
    """
    rooms_lookup: Dict[str, List[Dict[str, Any]]] = {}

    for profile in PROPERTY_PROFILES:
        property_id: str = profile["propertyId"]
        total_rooms: int = profile["totalRooms"]

        logger.info(
            "Generating room inventory for %s (%d rooms)",
            property_id,
            total_rooms,
        )

        room_counts = _compute_room_counts(total_rooms)
        property_rooms: List[Dict[str, Any]] = []

        # Track floor-level sequence counters for room numbering.
        # Key: floor number, Value: next sequence number on that floor.
        floor_sequences: Dict[int, int] = {}

        # Generation order matches ordered_types in _compute_room_counts
        generation_order: List[str] = [
            "PENTHOUSE", "SUITE", "KING_DELUXE", "QUEEN_DELUXE", "KING_STANDARD",
        ]

        global_room_index = 0

        for room_type in generation_order:
            count = room_counts[room_type]

            for i in range(count):
                floor = _assign_floor(room_type, i, count)

                # Determine sequence number on this floor
                if floor not in floor_sequences:
                    floor_sequences[floor] = 1
                sequence = floor_sequences[floor]
                floor_sequences[floor] += 1

                room_number = _generate_room_number(floor, sequence)
                view = _assign_view(property_id, global_room_index, floor)
                is_premium = _is_premium_room(room_type, floor)
                amenities = AMENITIES_BY_ROOM_TYPE[room_type]
                max_occupancy = MAX_OCCUPANCY_BY_ROOM_TYPE[room_type]

                room_item: Dict[str, Any] = {
                    "propertyId": property_id,
                    "roomNumber": room_number,
                    "roomType": room_type,
                    "floor": floor,
                    "view": view,
                    "status": "AVAILABLE",
                    "statusRoomNumber": f"AVAILABLE#{room_number}",
                    "isPremiumRoom": is_premium,
                    "currentGuestId": None,
                    "currentWorkOrderId": None,
                    "maxOccupancy": max_occupancy,
                    "amenities": amenities,
                }

                property_rooms.append(room_item)
                global_room_index += 1

        # Write all rooms for this property to DynamoDB
        result = writer.write_items(property_rooms)
        logger.info(
            "Room inventory written for %s: %d succeeded, %d failed",
            property_id,
            result["success"],
            result["failed"],
        )

        rooms_lookup[property_id] = property_rooms

    total_generated = sum(len(rooms) for rooms in rooms_lookup.values())
    logger.info("Total room inventory generated: %d items across %d properties",
                total_generated, len(rooms_lookup))

    return rooms_lookup


def reconcile_room_status(
    reservations: List[Dict[str, Any]],
    work_orders: List[Dict[str, Any]],
    rooms_lookup: Dict[str, List[Dict[str, Any]]],
    table_name: str,
) -> Dict[str, int]:
    """Update room statuses based on current reservations and work orders.

    Called after all generators have run. Examines today's CHECKED_IN
    reservations and OPEN/IN_PROGRESS work orders to set rooms to OCCUPIED,
    OOO, or MAINTENANCE. Rooms not affected remain AVAILABLE.

    Uses DynamoDB UpdateItem (not BatchWriteItem) since only specific
    attributes are being updated on existing items.

    Args:
        reservations: List of all generated reservation dicts. Only those
            with status CHECKED_IN are considered for OCCUPIED assignment.
        work_orders: List of all generated work order dicts. Those with
            status OPEN or IN_PROGRESS are considered for OOO/MAINTENANCE.
        rooms_lookup: Dict keyed by propertyId mapping to lists of room items.
            Used to resolve room existence and premium status.
        table_name: Name of the stayos-rooms DynamoDB table to update.

    Returns:
        Dict with update counts: {"occupied": N, "ooo": N, "maintenance": N,
        "errors": N} representing how many rooms were updated per status.
    """
    update_counts: Dict[str, int] = {
        "occupied": 0,
        "ooo": 0,
        "maintenance": 0,
        "errors": 0,
    }

    # Build a set of (propertyId, roomNumber) -> status updates to apply.
    # Work orders take precedence for OOO/MAINTENANCE, then reservations for OCCUPIED.
    status_updates: Dict[Tuple[str, str], Dict[str, Any]] = {}

    # Process work orders first: OPEN/IN_PROGRESS -> OOO (HIGH/CRITICAL) or MAINTENANCE (LOW/MEDIUM)
    for work_order in work_orders:
        wo_status = work_order.get("status", "")
        if wo_status not in ("OPEN", "IN_PROGRESS"):
            continue

        property_id = work_order.get("propertyId", "")
        room_number = work_order.get("roomNumber", "")
        priority = work_order.get("priority", "MEDIUM")
        work_order_id = work_order.get("workOrderId", "")

        if not property_id or not room_number:
            continue

        # HIGH/CRITICAL priority -> OOO, LOW/MEDIUM -> MAINTENANCE
        if priority in ("HIGH", "CRITICAL"):
            new_status = "OOO"
        else:
            new_status = "MAINTENANCE"

        key = (property_id, room_number)
        # If already marked OOO (from a higher-priority order), don't downgrade
        if key in status_updates and status_updates[key]["status"] == "OOO":
            continue

        status_updates[key] = {
            "status": new_status,
            "currentWorkOrderId": work_order_id,
            "currentGuestId": None,
        }

    # Process reservations: CHECKED_IN today -> OCCUPIED
    for reservation in reservations:
        res_status = reservation.get("status", "")
        if res_status != "CHECKED_IN":
            continue

        property_id = reservation.get("propertyId", "")
        room_number = reservation.get("roomNumber", "")
        guest_id = reservation.get("guestId", "")

        if not property_id or not room_number:
            continue

        key = (property_id, room_number)
        # Work order status takes precedence over reservation status
        if key in status_updates:
            continue

        status_updates[key] = {
            "status": "OCCUPIED",
            "currentGuestId": guest_id,
            "currentWorkOrderId": None,
        }

    # Apply all updates via DynamoDB UpdateItem
    for (property_id, room_number), update_data in status_updates.items():
        new_status = update_data["status"]
        composite_key = f"{new_status}#{room_number}"

        try:
            # Update status, statusRoomNumber composite key, and reference fields
            _dynamodb_client.update_item(
                TableName=table_name,
                Key={
                    "propertyId": {"S": property_id},
                    "roomNumber": {"S": room_number},
                },
                UpdateExpression=(
                    "SET #s = :status, "
                    "statusRoomNumber = :srn, "
                    "currentGuestId = :gid, "
                    "currentWorkOrderId = :woid"
                ),
                ExpressionAttributeNames={
                    "#s": "status",
                },
                ExpressionAttributeValues={
                    ":status": {"S": new_status},
                    ":srn": {"S": composite_key},
                    ":gid": {"S": update_data["currentGuestId"]}
                    if update_data["currentGuestId"]
                    else {"NULL": True},
                    ":woid": {"S": update_data["currentWorkOrderId"]}
                    if update_data["currentWorkOrderId"]
                    else {"NULL": True},
                },
            )

            # Track the update type for reporting
            if new_status == "OCCUPIED":
                update_counts["occupied"] += 1
            elif new_status == "OOO":
                update_counts["ooo"] += 1
            elif new_status == "MAINTENANCE":
                update_counts["maintenance"] += 1

        except ClientError as error:
            error_code = error.response["Error"]["Code"]
            logger.error(
                "Failed to update room status for %s/%s: %s - %s",
                property_id,
                room_number,
                error_code,
                error.response["Error"]["Message"],
            )
            update_counts["errors"] += 1

    logger.info(
        "Room status reconciliation complete: %d occupied, %d ooo, "
        "%d maintenance, %d errors",
        update_counts["occupied"],
        update_counts["ooo"],
        update_counts["maintenance"],
        update_counts["errors"],
    )

    return update_counts
