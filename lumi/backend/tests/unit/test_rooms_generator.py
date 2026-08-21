"""Unit tests for the dataset_generator.rooms_generator module.

Tests room inventory generation including room count distribution, floor
assignment, view assignment, premium status determination, room number
generation, and room status reconciliation.
"""

import sys
from decimal import Decimal
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

# Stub out generator modules that don't exist yet so dataset_generator.__init__
# can be imported without errors during incremental development.
for _mod_name in (
    "dataset_generator.guests_generator",
    "dataset_generator.revenue_generator",
    "dataset_generator.reservations_generator",
    "dataset_generator.work_orders_generator",
):
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = MagicMock()

from dataset_generator.config import PROPERTY_PROFILES, PROPERTY_VIEWS
from dataset_generator.rooms_generator import (
    AMENITIES_BY_ROOM_TYPE,
    MAX_OCCUPANCY_BY_ROOM_TYPE,
    _assign_floor,
    _assign_view,
    _compute_room_counts,
    _generate_room_number,
    _is_premium_room,
    generate_rooms,
    reconcile_room_status,
)


# ---------------------------------------------------------------------------
# _compute_room_counts tests
# ---------------------------------------------------------------------------


class TestComputeRoomCounts:
    """Tests for room count distribution calculation."""

    def test_sum_equals_total_rooms(self) -> None:
        """Room count sum must equal the input total exactly."""
        for profile in PROPERTY_PROFILES:
            counts = _compute_room_counts(profile["totalRooms"])
            assert sum(counts.values()) == profile["totalRooms"]

    def test_all_room_types_present(self) -> None:
        """All 5 room types must have at least 1 room."""
        counts = _compute_room_counts(368)
        expected_types = {"PENTHOUSE", "SUITE", "KING_DELUXE", "QUEEN_DELUXE", "KING_STANDARD"}
        assert set(counts.keys()) == expected_types
        assert all(count > 0 for count in counts.values())

    def test_premium_about_5_percent(self) -> None:
        """PENTHOUSE + SUITE should be approximately 5% of total."""
        counts = _compute_room_counts(368)
        premium_pct = (counts["PENTHOUSE"] + counts["SUITE"]) / 368 * 100
        assert 3.0 <= premium_pct <= 7.0

    def test_deluxe_about_30_percent(self) -> None:
        """KING_DELUXE + QUEEN_DELUXE should be approximately 30% of total."""
        counts = _compute_room_counts(368)
        deluxe_pct = (counts["KING_DELUXE"] + counts["QUEEN_DELUXE"]) / 368 * 100
        assert 25.0 <= deluxe_pct <= 35.0

    def test_standard_about_65_percent(self) -> None:
        """KING_STANDARD should be approximately 65% of total."""
        counts = _compute_room_counts(368)
        standard_pct = counts["KING_STANDARD"] / 368 * 100
        assert 60.0 <= standard_pct <= 70.0

    def test_king_standard_absorbs_remainder(self) -> None:
        """KING_STANDARD gets whatever remains after rounding other types."""
        counts = _compute_room_counts(100)
        non_standard = (
            counts["PENTHOUSE"] + counts["SUITE"]
            + counts["KING_DELUXE"] + counts["QUEEN_DELUXE"]
        )
        assert counts["KING_STANDARD"] == 100 - non_standard


# ---------------------------------------------------------------------------
# _assign_floor tests
# ---------------------------------------------------------------------------


class TestAssignFloor:
    """Tests for floor assignment logic."""

    def test_penthouse_in_range(self) -> None:
        """Penthouse rooms are assigned to floors 20-24."""
        for i in range(7):
            floor = _assign_floor("PENTHOUSE", i, 7)
            assert 20 <= floor <= 24

    def test_suite_in_range(self) -> None:
        """Suite rooms are assigned to floors 18-22."""
        for i in range(11):
            floor = _assign_floor("SUITE", i, 11)
            assert 18 <= floor <= 22

    def test_king_standard_in_range(self) -> None:
        """Standard rooms are assigned to floors 2-11."""
        for i in range(240):
            floor = _assign_floor("KING_STANDARD", i, 240)
            assert 2 <= floor <= 11

    def test_deterministic(self) -> None:
        """Same inputs always produce same floor."""
        floor_a = _assign_floor("KING_DELUXE", 5, 55)
        floor_b = _assign_floor("KING_DELUXE", 5, 55)
        assert floor_a == floor_b


# ---------------------------------------------------------------------------
# _assign_view tests
# ---------------------------------------------------------------------------


class TestAssignView:
    """Tests for view assignment logic."""

    def test_returns_valid_view_for_property(self) -> None:
        """Assigned view must be in the property's view list."""
        for property_id, views in PROPERTY_VIEWS.items():
            for room_index in range(50):
                view = _assign_view(property_id, room_index, 10)
                assert view in views

    def test_deterministic(self) -> None:
        """Same inputs always produce same view."""
        view_a = _assign_view("ALOHA-CHI-001", 7, 12)
        view_b = _assign_view("ALOHA-CHI-001", 7, 12)
        assert view_a == view_b

    def test_cycles_through_views(self) -> None:
        """Different room indices produce different views (cycling)."""
        views_assigned = set()
        for room_index in range(20):
            view = _assign_view("ALOHA-CHI-001", room_index, 5)
            views_assigned.add(view)
        # Should have multiple different views
        assert len(views_assigned) > 1


# ---------------------------------------------------------------------------
# _is_premium_room tests
# ---------------------------------------------------------------------------


class TestIsPremiumRoom:
    """Tests for premium room classification."""

    def test_suite_always_premium(self) -> None:
        """SUITE is always premium regardless of floor."""
        assert _is_premium_room("SUITE", 2) is True
        assert _is_premium_room("SUITE", 18) is True

    def test_penthouse_always_premium(self) -> None:
        """PENTHOUSE is always premium regardless of floor."""
        assert _is_premium_room("PENTHOUSE", 20) is True

    def test_king_deluxe_premium_on_high_floor(self) -> None:
        """KING_DELUXE is premium on floor >= 15."""
        assert _is_premium_room("KING_DELUXE", 15) is True
        assert _is_premium_room("KING_DELUXE", 17) is True

    def test_king_deluxe_not_premium_on_low_floor(self) -> None:
        """KING_DELUXE is not premium below floor 15."""
        assert _is_premium_room("KING_DELUXE", 14) is False
        assert _is_premium_room("KING_DELUXE", 12) is False

    def test_queen_deluxe_never_premium(self) -> None:
        """QUEEN_DELUXE is never premium."""
        assert _is_premium_room("QUEEN_DELUXE", 14) is False
        assert _is_premium_room("QUEEN_DELUXE", 20) is False

    def test_king_standard_never_premium(self) -> None:
        """KING_STANDARD is never premium."""
        assert _is_premium_room("KING_STANDARD", 11) is False
        assert _is_premium_room("KING_STANDARD", 2) is False


# ---------------------------------------------------------------------------
# _generate_room_number tests
# ---------------------------------------------------------------------------


class TestGenerateRoomNumber:
    """Tests for room number string generation."""

    def test_basic_format(self) -> None:
        """Room number follows floor * 100 + sequence pattern."""
        assert _generate_room_number(12, 3) == "1203"
        assert _generate_room_number(2, 1) == "201"
        assert _generate_room_number(20, 15) == "2015"

    def test_returns_string(self) -> None:
        """Room number is always returned as a string."""
        result = _generate_room_number(5, 7)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# generate_rooms tests
# ---------------------------------------------------------------------------


class TestGenerateRooms:
    """Tests for the full room inventory generation function."""

    def setup_method(self) -> None:
        """Create a mock writer for each test."""
        self.mock_writer = MagicMock()
        self.mock_writer.write_items.return_value = {"success": 25, "failed": 0}

    def test_returns_all_properties(self) -> None:
        """Lookup dict contains all 5 properties."""
        result = generate_rooms(self.mock_writer)
        expected_ids = {p["propertyId"] for p in PROPERTY_PROFILES}
        assert set(result.keys()) == expected_ids

    def test_correct_room_counts_per_property(self) -> None:
        """Each property has its expected totalRooms count."""
        result = generate_rooms(self.mock_writer)
        for profile in PROPERTY_PROFILES:
            assert len(result[profile["propertyId"]]) == profile["totalRooms"]

    def test_total_rooms_approximately_2000(self) -> None:
        """Total across all properties should be ~2,000."""
        result = generate_rooms(self.mock_writer)
        total = sum(len(rooms) for rooms in result.values())
        assert 1900 <= total <= 2100

    def test_all_rooms_start_available(self) -> None:
        """Every room item has status AVAILABLE initially."""
        result = generate_rooms(self.mock_writer)
        for rooms in result.values():
            for room in rooms:
                assert room["status"] == "AVAILABLE"

    def test_status_room_number_composite_key(self) -> None:
        """statusRoomNumber follows AVAILABLE#roomNumber format."""
        result = generate_rooms(self.mock_writer)
        for rooms in result.values():
            for room in rooms:
                expected = f"AVAILABLE#{room['roomNumber']}"
                assert room["statusRoomNumber"] == expected

    def test_room_item_has_all_required_fields(self) -> None:
        """Each room item contains all required DynamoDB attributes."""
        required = {
            "propertyId", "roomNumber", "roomType", "floor", "view",
            "status", "statusRoomNumber", "isPremiumRoom", "currentGuestId",
            "currentWorkOrderId", "maxOccupancy", "amenities",
        }
        result = generate_rooms(self.mock_writer)
        first_room = result["ALOHA-CHI-001"][0]
        assert required.issubset(set(first_room.keys()))

    def test_unique_room_numbers_per_property(self) -> None:
        """No duplicate room numbers within a single property."""
        result = generate_rooms(self.mock_writer)
        for prop_id, rooms in result.items():
            room_numbers = [r["roomNumber"] for r in rooms]
            assert len(room_numbers) == len(set(room_numbers)), (
                f"Duplicate room numbers in {prop_id}"
            )

    def test_writer_called_for_each_property(self) -> None:
        """Writer.write_items is called once per property."""
        generate_rooms(self.mock_writer)
        assert self.mock_writer.write_items.call_count == 5

    def test_amenities_match_room_type(self) -> None:
        """Room amenities correspond to the room's type."""
        result = generate_rooms(self.mock_writer)
        for rooms in result.values():
            for room in rooms:
                expected_amenities = AMENITIES_BY_ROOM_TYPE[room["roomType"]]
                assert room["amenities"] == expected_amenities

    def test_max_occupancy_matches_room_type(self) -> None:
        """Max occupancy corresponds to the room's type."""
        result = generate_rooms(self.mock_writer)
        for rooms in result.values():
            for room in rooms:
                expected = MAX_OCCUPANCY_BY_ROOM_TYPE[room["roomType"]]
                assert room["maxOccupancy"] == expected


# ---------------------------------------------------------------------------
# reconcile_room_status tests
# ---------------------------------------------------------------------------


class TestReconcileRoomStatus:
    """Tests for room status reconciliation logic."""

    def _make_rooms_lookup(self) -> Dict[str, List[Dict[str, Any]]]:
        """Create a minimal rooms lookup for testing."""
        return {
            "ALOHA-CHI-001": [
                {"propertyId": "ALOHA-CHI-001", "roomNumber": "1201", "isPremiumRoom": True},
                {"propertyId": "ALOHA-CHI-001", "roomNumber": "1202", "isPremiumRoom": False},
                {"propertyId": "ALOHA-CHI-001", "roomNumber": "501", "isPremiumRoom": False},
            ],
        }

    @patch("dataset_generator.rooms_generator._dynamodb_client")
    def test_checked_in_sets_occupied(self, mock_client: MagicMock) -> None:
        """CHECKED_IN reservation marks room as OCCUPIED."""
        mock_client.update_item.return_value = {}

        reservations = [
            {
                "propertyId": "ALOHA-CHI-001",
                "roomNumber": "1201",
                "status": "CHECKED_IN",
                "guestId": "GUEST-001",
            },
        ]
        work_orders: List[Dict[str, Any]] = []

        result = reconcile_room_status(
            reservations, work_orders, self._make_rooms_lookup(), "stayos-rooms"
        )

        assert result["occupied"] == 1
        mock_client.update_item.assert_called_once()
        call_kwargs = mock_client.update_item.call_args[1]
        assert call_kwargs["ExpressionAttributeValues"][":status"] == {"S": "OCCUPIED"}
        assert call_kwargs["ExpressionAttributeValues"][":gid"] == {"S": "GUEST-001"}

    @patch("dataset_generator.rooms_generator._dynamodb_client")
    def test_high_priority_work_order_sets_ooo(self, mock_client: MagicMock) -> None:
        """HIGH priority OPEN work order marks room as OOO."""
        mock_client.update_item.return_value = {}

        reservations: List[Dict[str, Any]] = []
        work_orders = [
            {
                "propertyId": "ALOHA-CHI-001",
                "roomNumber": "1202",
                "status": "OPEN",
                "priority": "HIGH",
                "workOrderId": "WO-001",
            },
        ]

        result = reconcile_room_status(
            reservations, work_orders, self._make_rooms_lookup(), "stayos-rooms"
        )

        assert result["ooo"] == 1
        call_kwargs = mock_client.update_item.call_args[1]
        assert call_kwargs["ExpressionAttributeValues"][":status"] == {"S": "OOO"}
        assert call_kwargs["ExpressionAttributeValues"][":woid"] == {"S": "WO-001"}

    @patch("dataset_generator.rooms_generator._dynamodb_client")
    def test_low_priority_work_order_sets_maintenance(self, mock_client: MagicMock) -> None:
        """LOW priority OPEN work order marks room as MAINTENANCE."""
        mock_client.update_item.return_value = {}

        reservations: List[Dict[str, Any]] = []
        work_orders = [
            {
                "propertyId": "ALOHA-CHI-001",
                "roomNumber": "501",
                "status": "IN_PROGRESS",
                "priority": "LOW",
                "workOrderId": "WO-002",
            },
        ]

        result = reconcile_room_status(
            reservations, work_orders, self._make_rooms_lookup(), "stayos-rooms"
        )

        assert result["maintenance"] == 1
        call_kwargs = mock_client.update_item.call_args[1]
        assert call_kwargs["ExpressionAttributeValues"][":status"] == {"S": "MAINTENANCE"}

    @patch("dataset_generator.rooms_generator._dynamodb_client")
    def test_work_order_takes_precedence_over_reservation(
        self, mock_client: MagicMock
    ) -> None:
        """Work order OOO/MAINTENANCE takes precedence over OCCUPIED status."""
        mock_client.update_item.return_value = {}

        # Same room has both a checked-in reservation and a critical work order
        reservations = [
            {
                "propertyId": "ALOHA-CHI-001",
                "roomNumber": "1201",
                "status": "CHECKED_IN",
                "guestId": "GUEST-001",
            },
        ]
        work_orders = [
            {
                "propertyId": "ALOHA-CHI-001",
                "roomNumber": "1201",
                "status": "OPEN",
                "priority": "CRITICAL",
                "workOrderId": "WO-003",
            },
        ]

        result = reconcile_room_status(
            reservations, work_orders, self._make_rooms_lookup(), "stayos-rooms"
        )

        # OOO from work order takes precedence
        assert result["ooo"] == 1
        assert result["occupied"] == 0
        # Only one update call should be made (not two)
        assert mock_client.update_item.call_count == 1

    @patch("dataset_generator.rooms_generator._dynamodb_client")
    def test_ignores_non_checked_in_reservations(self, mock_client: MagicMock) -> None:
        """Only CHECKED_IN reservations contribute to OCCUPIED status."""
        reservations = [
            {
                "propertyId": "ALOHA-CHI-001",
                "roomNumber": "1201",
                "status": "CONFIRMED",
                "guestId": "GUEST-001",
            },
            {
                "propertyId": "ALOHA-CHI-001",
                "roomNumber": "1202",
                "status": "CHECKED_OUT",
                "guestId": "GUEST-002",
            },
        ]
        work_orders: List[Dict[str, Any]] = []

        result = reconcile_room_status(
            reservations, work_orders, self._make_rooms_lookup(), "stayos-rooms"
        )

        assert result["occupied"] == 0
        mock_client.update_item.assert_not_called()

    @patch("dataset_generator.rooms_generator._dynamodb_client")
    def test_ignores_resolved_work_orders(self, mock_client: MagicMock) -> None:
        """Only OPEN and IN_PROGRESS work orders affect room status."""
        reservations: List[Dict[str, Any]] = []
        work_orders = [
            {
                "propertyId": "ALOHA-CHI-001",
                "roomNumber": "1201",
                "status": "RESOLVED",
                "priority": "HIGH",
                "workOrderId": "WO-004",
            },
        ]

        result = reconcile_room_status(
            reservations, work_orders, self._make_rooms_lookup(), "stayos-rooms"
        )

        assert result["ooo"] == 0
        assert result["maintenance"] == 0
        mock_client.update_item.assert_not_called()

    @patch("dataset_generator.rooms_generator._dynamodb_client")
    def test_handles_client_error_gracefully(self, mock_client: MagicMock) -> None:
        """ClientError during update increments error count."""
        mock_client.update_item.side_effect = ClientError(
            error_response={
                "Error": {"Code": "ConditionalCheckFailedException", "Message": "Condition not met"},
            },
            operation_name="UpdateItem",
        )

        reservations = [
            {
                "propertyId": "ALOHA-CHI-001",
                "roomNumber": "1201",
                "status": "CHECKED_IN",
                "guestId": "GUEST-001",
            },
        ]

        result = reconcile_room_status(
            reservations, [], self._make_rooms_lookup(), "stayos-rooms"
        )

        assert result["errors"] == 1
        assert result["occupied"] == 0

    @patch("dataset_generator.rooms_generator._dynamodb_client")
    def test_empty_inputs_no_updates(self, mock_client: MagicMock) -> None:
        """No reservations or work orders means no updates needed."""
        result = reconcile_room_status(
            [], [], self._make_rooms_lookup(), "stayos-rooms"
        )

        assert result == {"occupied": 0, "ooo": 0, "maintenance": 0, "errors": 0}
        mock_client.update_item.assert_not_called()

    @patch("dataset_generator.rooms_generator._dynamodb_client")
    def test_status_room_number_composite_key_in_update(
        self, mock_client: MagicMock
    ) -> None:
        """UpdateItem sets statusRoomNumber to status#roomNumber."""
        mock_client.update_item.return_value = {}

        reservations = [
            {
                "propertyId": "ALOHA-CHI-001",
                "roomNumber": "1201",
                "status": "CHECKED_IN",
                "guestId": "GUEST-001",
            },
        ]

        reconcile_room_status(
            reservations, [], self._make_rooms_lookup(), "stayos-rooms"
        )

        call_kwargs = mock_client.update_item.call_args[1]
        assert call_kwargs["ExpressionAttributeValues"][":srn"] == {"S": "OCCUPIED#1201"}
