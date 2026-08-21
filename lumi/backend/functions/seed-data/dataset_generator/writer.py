"""DynamoDB BatchWriteItem utility with exponential backoff for LUMI dataset seeding.

Provides the BatchWriter class that handles bulk loading of items into DynamoDB
tables using BatchWriteItem. Supports automatic chunking (25 items per batch),
exponential backoff on UnprocessedItems, and Decimal conversion for float values.

Used by all dataset generator modules (rooms, guests, revenue, reservations,
work orders) to write generated data to DynamoDB during the seed-data Lambda
custom resource execution.

Supports REQ-DS-8 (BatchWriteItem with 25 items/batch, exponential backoff).
"""

import logging
import time
from decimal import Decimal
from typing import Any, Dict, List, Union

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from dataset_generator.config import (
    BACKOFF_BASE_MS,
    BACKOFF_MAX_MS,
    BATCH_WRITE_SIZE,
    MAX_RETRIES,
)

logger = logging.getLogger(__name__)

# Module-level boto3 DynamoDB resource for connection reuse across invocations.
# Standard retry mode handles transient errors at the SDK level.
_dynamodb = boto3.resource(
    "dynamodb",
    config=Config(retries={"mode": "standard"}),
)


def convert_floats_to_decimal(obj: Any) -> Any:
    """Recursively convert float values to Decimal for DynamoDB compatibility.

    DynamoDB does not accept Python float types. This function walks a nested
    dict/list structure and converts any float values to Decimal using string
    intermediary to avoid floating-point precision artifacts.

    Args:
        obj: A value of any type — dict, list, float, or primitive. Nested
            structures are traversed recursively.

    Returns:
        The same structure with all float values replaced by Decimal equivalents.
        Non-float primitives (str, int, bool, None) are returned unchanged.
    """
    if isinstance(obj, dict):
        return {key: convert_floats_to_decimal(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [convert_floats_to_decimal(item) for item in obj]
    if isinstance(obj, float):
        # Use str() intermediary to preserve the decimal representation
        # and avoid float precision issues (e.g., 0.1 -> 0.1000000000000000055...)
        return Decimal(str(obj))
    return obj


class BatchWriter:
    """Writes items to a DynamoDB table in batches with retry logic.

    Splits items into chunks of 25 (DynamoDB BatchWriteItem limit), submits
    each batch, and retries UnprocessedItems with fixed exponential backoff.
    Tracks success and failure counts for reporting.

    Attributes:
        table_name: The DynamoDB table name to write to.
        success_count: Number of items successfully written.
        failure_count: Number of items that failed after max retries.
    """

    def __init__(self, table_name: str) -> None:
        """Initialize the BatchWriter for a specific DynamoDB table.

        Args:
            table_name: Name of the DynamoDB table to write items to.
                Must match an existing table accessible by the Lambda role.
        """
        self.table_name = table_name
        self.success_count: int = 0
        self.failure_count: int = 0

    def write_items(self, items: List[Dict[str, Any]]) -> Dict[str, int]:
        """Write a list of items to DynamoDB in batches of 25.

        Splits the input list into chunks of BATCH_WRITE_SIZE, converts float
        values to Decimal, and submits each chunk via batch_write_item. Any
        UnprocessedItems are retried with exponential backoff up to MAX_RETRIES.

        Args:
            items: List of item dicts to write. Each dict represents a single
                DynamoDB item with attribute names as keys. Float values are
                automatically converted to Decimal before writing.

        Returns:
            A dict with counts: {"success": N, "failed": N} representing
            how many items were successfully written vs failed after retries.
        """
        # Split items into chunks of 25 (BatchWriteItem limit)
        chunks = [
            items[i : i + BATCH_WRITE_SIZE]
            for i in range(0, len(items), BATCH_WRITE_SIZE)
        ]

        for chunk_index, chunk in enumerate(chunks):
            self._write_batch(chunk, chunk_index)

        logger.info(
            "Completed writing to %s: %d succeeded, %d failed",
            self.table_name,
            self.success_count,
            self.failure_count,
        )

        return {"success": self.success_count, "failed": self.failure_count}

    def _write_batch(self, chunk: List[Dict[str, Any]], chunk_index: int) -> None:
        """Write a single batch of up to 25 items with retry on UnprocessedItems.

        Submits the batch to DynamoDB and retries any UnprocessedItems using
        fixed exponential backoff (no jitter) up to MAX_RETRIES attempts.

        Args:
            chunk: A list of up to 25 item dicts to write in one batch request.
            chunk_index: Zero-based index of this chunk within the overall
                write operation, used for logging context.

        Raises:
            ClientError: If a non-retryable DynamoDB error occurs (e.g.,
                ValidationException, ResourceNotFoundException).
        """
        # Convert floats to Decimal for DynamoDB compatibility
        converted_chunk = [convert_floats_to_decimal(item) for item in chunk]

        # Build the PutRequest structure for batch_write_item
        request_items: Dict[str, List[Dict[str, Any]]] = {
            self.table_name: [
                {"PutRequest": {"Item": item}} for item in converted_chunk
            ]
        }

        attempt = 0
        items_in_batch = len(converted_chunk)

        while request_items:
            try:
                # Submit the batch to DynamoDB
                response = _dynamodb.meta.client.batch_write_item(
                    RequestItems=request_items
                )
            except ClientError as error:
                error_code = error.response["Error"]["Code"]
                logger.error(
                    "DynamoDB batch_write_item failed for table %s, "
                    "chunk %d, attempt %d: %s - %s",
                    self.table_name,
                    chunk_index,
                    attempt,
                    error_code,
                    error.response["Error"]["Message"],
                )
                # Count all remaining items as failed
                remaining = sum(
                    len(puts) for puts in request_items.values()
                )
                self.failure_count += remaining
                return

            # Check for UnprocessedItems that need retry
            unprocessed = response.get("UnprocessedItems", {})

            if not unprocessed:
                # All items in this batch succeeded
                self.success_count += items_in_batch
                logger.info(
                    "Batch %d written to %s: %d items",
                    chunk_index,
                    self.table_name,
                    items_in_batch,
                )
                return

            # Some items were not processed — prepare retry
            attempt += 1
            unprocessed_count = sum(
                len(puts) for puts in unprocessed.values()
            )
            processed_this_round = items_in_batch - unprocessed_count
            self.success_count += processed_this_round
            # Update items_in_batch for the next iteration to track only remaining
            items_in_batch = unprocessed_count

            if attempt >= MAX_RETRIES:
                logger.error(
                    "Max retries (%d) exhausted for table %s, chunk %d. "
                    "%d items remain unprocessed.",
                    MAX_RETRIES,
                    self.table_name,
                    chunk_index,
                    unprocessed_count,
                )
                self.failure_count += unprocessed_count
                return

            # Fixed exponential backoff: min(base * 2^attempt, max)
            delay_ms = min(
                BACKOFF_BASE_MS * (2 ** attempt),
                BACKOFF_MAX_MS,
            )

            logger.warning(
                "Retrying %d UnprocessedItems for table %s, chunk %d "
                "(attempt %d/%d, backoff %dms)",
                unprocessed_count,
                self.table_name,
                chunk_index,
                attempt,
                MAX_RETRIES,
                delay_ms,
            )

            time.sleep(delay_ms / 1000.0)
            request_items = unprocessed
