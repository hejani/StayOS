"""Unit tests for the dataset_generator.writer module.

Tests the BatchWriter class (batch chunking, exponential backoff on
UnprocessedItems, success/failure counting) and the convert_floats_to_decimal
helper function.
"""

from decimal import Decimal
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import boto3
import moto
import pytest
from botocore.exceptions import ClientError

import sys
from types import ModuleType
from unittest.mock import MagicMock

# Stub out generator modules that don't exist yet so dataset_generator.__init__
# can be imported without errors during incremental development.
for _mod_name in (
    "dataset_generator.rooms_generator",
    "dataset_generator.guests_generator",
    "dataset_generator.revenue_generator",
    "dataset_generator.reservations_generator",
    "dataset_generator.work_orders_generator",
):
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = MagicMock()

from dataset_generator.writer import BatchWriter, convert_floats_to_decimal


# ---------------------------------------------------------------------------
# convert_floats_to_decimal tests
# ---------------------------------------------------------------------------


class TestConvertFloatsToDecimal:
    """Tests for the recursive float-to-Decimal conversion helper."""

    def test_converts_simple_float(self) -> None:
        """A standalone float becomes a Decimal via str intermediary."""
        result = convert_floats_to_decimal(3.14)
        assert result == Decimal("3.14")
        assert isinstance(result, Decimal)

    def test_converts_float_in_dict(self) -> None:
        """Float values nested in a dict are converted."""
        data: Dict[str, Any] = {"rate": 249.99, "name": "Suite"}
        result = convert_floats_to_decimal(data)
        assert result == {"rate": Decimal("249.99"), "name": "Suite"}
        assert isinstance(result["rate"], Decimal)

    def test_converts_float_in_nested_dict(self) -> None:
        """Deeply nested floats are converted recursively."""
        data: Dict[str, Any] = {"outer": {"inner": {"value": 0.1}}}
        result = convert_floats_to_decimal(data)
        assert result["outer"]["inner"]["value"] == Decimal("0.1")

    def test_converts_float_in_list(self) -> None:
        """Float values inside lists are converted."""
        data: List[Any] = [1.5, 2.5, "text", 3]
        result = convert_floats_to_decimal(data)
        assert result == [Decimal("1.5"), Decimal("2.5"), "text", 3]

    def test_preserves_non_float_types(self) -> None:
        """Strings, ints, bools, and None pass through unchanged."""
        data: Dict[str, Any] = {
            "name": "Chicago",
            "count": 42,
            "active": True,
            "notes": None,
        }
        result = convert_floats_to_decimal(data)
        assert result == data

    def test_handles_empty_structures(self) -> None:
        """Empty dict and list return unchanged."""
        assert convert_floats_to_decimal({}) == {}
        assert convert_floats_to_decimal([]) == []

    def test_precision_preserved(self) -> None:
        """Decimal conversion via str avoids float precision artifacts."""
        # 0.1 as float has precision issues; str("0.1") -> Decimal("0.1") is exact
        result = convert_floats_to_decimal(0.1)
        assert result == Decimal("0.1")
        assert str(result) == "0.1"


# ---------------------------------------------------------------------------
# BatchWriter tests
# ---------------------------------------------------------------------------


class TestBatchWriter:
    """Tests for the BatchWriter class batch writing and retry logic."""

    @moto.mock_aws
    def test_writes_items_successfully(self) -> None:
        """Items are written in batches and success count is reported."""
        # Create a real mocked DynamoDB table
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        dynamodb.create_table(
            TableName="test-table",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        # Patch the module-level _dynamodb resource to use moto's mock
        with patch("dataset_generator.writer._dynamodb", dynamodb):
            writer = BatchWriter(table_name="test-table")
            items = [{"pk": f"item-{i}", "value": 1.5} for i in range(10)]
            result = writer.write_items(items)

        assert result == {"success": 10, "failed": 0}
        assert writer.success_count == 10
        assert writer.failure_count == 0

    @moto.mock_aws
    def test_writes_more_than_25_items_in_multiple_batches(self) -> None:
        """Items exceeding batch size are split into multiple batches."""
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        dynamodb.create_table(
            TableName="test-table",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        with patch("dataset_generator.writer._dynamodb", dynamodb):
            writer = BatchWriter(table_name="test-table")
            # 60 items = 3 batches (25 + 25 + 10)
            items = [{"pk": f"item-{i}", "data": "test"} for i in range(60)]
            result = writer.write_items(items)

        assert result == {"success": 60, "failed": 0}

    @moto.mock_aws
    def test_writes_exactly_25_items_in_one_batch(self) -> None:
        """Exactly 25 items form a single batch."""
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        dynamodb.create_table(
            TableName="test-table",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        with patch("dataset_generator.writer._dynamodb", dynamodb):
            writer = BatchWriter(table_name="test-table")
            items = [{"pk": f"item-{i}"} for i in range(25)]
            result = writer.write_items(items)

        assert result == {"success": 25, "failed": 0}

    def test_handles_client_error(self) -> None:
        """ClientError from batch_write_item counts items as failed."""
        mock_dynamodb = MagicMock()
        mock_client = MagicMock()
        mock_dynamodb.meta.client = mock_client

        # Simulate a ClientError on batch_write_item
        mock_client.batch_write_item.side_effect = ClientError(
            error_response={
                "Error": {
                    "Code": "ResourceNotFoundException",
                    "Message": "Table not found",
                }
            },
            operation_name="BatchWriteItem",
        )

        with patch("dataset_generator.writer._dynamodb", mock_dynamodb):
            writer = BatchWriter(table_name="nonexistent-table")
            items = [{"pk": f"item-{i}"} for i in range(5)]
            result = writer.write_items(items)

        assert result == {"success": 0, "failed": 5}
        assert writer.failure_count == 5

    @patch("dataset_generator.writer.time.sleep")
    def test_retries_unprocessed_items_with_backoff(
        self, mock_sleep: MagicMock
    ) -> None:
        """UnprocessedItems trigger exponential backoff retries."""
        mock_dynamodb = MagicMock()
        mock_client = MagicMock()
        mock_dynamodb.meta.client = mock_client

        # First call returns 2 UnprocessedItems, second call succeeds
        unprocessed_response = {
            "UnprocessedItems": {
                "test-table": [
                    {"PutRequest": {"Item": {"pk": {"S": "item-0"}}}},
                    {"PutRequest": {"Item": {"pk": {"S": "item-1"}}}},
                ]
            }
        }
        success_response: Dict[str, Any] = {"UnprocessedItems": {}}

        mock_client.batch_write_item.side_effect = [
            unprocessed_response,
            success_response,
        ]

        with patch("dataset_generator.writer._dynamodb", mock_dynamodb):
            writer = BatchWriter(table_name="test-table")
            items = [{"pk": f"item-{i}"} for i in range(5)]
            result = writer.write_items(items)

        # 3 succeeded on first try, 2 succeeded on retry
        assert result["success"] == 5
        assert result["failed"] == 0
        # Backoff: 50ms * 2^1 = 100ms -> sleep(0.1)
        mock_sleep.assert_called_once_with(0.1)

    @patch("dataset_generator.writer.time.sleep")
    def test_max_retries_exhausted_counts_failures(
        self, mock_sleep: MagicMock
    ) -> None:
        """After MAX_RETRIES, remaining items are counted as failures."""
        mock_dynamodb = MagicMock()
        mock_client = MagicMock()
        mock_dynamodb.meta.client = mock_client

        # Always return unprocessed items (simulates persistent throttling)
        unprocessed_response = {
            "UnprocessedItems": {
                "test-table": [
                    {"PutRequest": {"Item": {"pk": {"S": "item-0"}}}},
                ]
            }
        }
        # 9 calls: 1 initial + 8 retries (MAX_RETRIES=8)
        mock_client.batch_write_item.return_value = unprocessed_response

        with patch("dataset_generator.writer._dynamodb", mock_dynamodb):
            writer = BatchWriter(table_name="test-table")
            items = [{"pk": "item-0"}]
            result = writer.write_items(items)

        # After MAX_RETRIES exhausted, the 1 remaining item is counted as failed
        assert result["failed"] == 1
        # sleep called MAX_RETRIES - 1 times (first call counts as attempt 0,
        # then attempts 1 through 8 with sleep before each retry)
        assert mock_sleep.call_count == 7

    @patch("dataset_generator.writer.time.sleep")
    def test_backoff_caps_at_max(self, mock_sleep: MagicMock) -> None:
        """Backoff delay is capped at BACKOFF_MAX_MS (5000ms)."""
        mock_dynamodb = MagicMock()
        mock_client = MagicMock()
        mock_dynamodb.meta.client = mock_client

        # Return unprocessed items for all attempts
        unprocessed_response = {
            "UnprocessedItems": {
                "test-table": [
                    {"PutRequest": {"Item": {"pk": {"S": "item-0"}}}},
                ]
            }
        }
        mock_client.batch_write_item.return_value = unprocessed_response

        with patch("dataset_generator.writer._dynamodb", mock_dynamodb):
            writer = BatchWriter(table_name="test-table")
            items = [{"pk": "item-0"}]
            writer.write_items(items)

        # Verify the backoff values:
        # attempt 1: min(50*2^1, 5000) = 100ms -> 0.1s
        # attempt 2: min(50*2^2, 5000) = 200ms -> 0.2s
        # attempt 3: min(50*2^3, 5000) = 400ms -> 0.4s
        # attempt 4: min(50*2^4, 5000) = 800ms -> 0.8s
        # attempt 5: min(50*2^5, 5000) = 1600ms -> 1.6s
        # attempt 6: min(50*2^6, 5000) = 3200ms -> 3.2s
        # attempt 7: min(50*2^7, 5000) = 5000ms -> 5.0s (capped)
        sleep_values = [call.args[0] for call in mock_sleep.call_args_list]
        assert sleep_values[-1] == 5.0  # Last sleep hits the cap

    @moto.mock_aws
    def test_float_to_decimal_conversion_in_write(self) -> None:
        """Float values in items are converted to Decimal before writing."""
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName="test-table",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        with patch("dataset_generator.writer._dynamodb", dynamodb):
            writer = BatchWriter(table_name="test-table")
            items = [{"pk": "item-1", "rate": 249.99, "occupancy": 0.87}]
            writer.write_items(items)

        # Verify the item was written with Decimal values
        response = table.get_item(Key={"pk": "item-1"})
        item = response["Item"]
        assert item["rate"] == Decimal("249.99")
        assert item["occupancy"] == Decimal("0.87")

    def test_empty_items_list(self) -> None:
        """An empty items list returns zero counts without errors."""
        mock_dynamodb = MagicMock()

        with patch("dataset_generator.writer._dynamodb", mock_dynamodb):
            writer = BatchWriter(table_name="test-table")
            result = writer.write_items([])

        assert result == {"success": 0, "failed": 0}
        # No batch_write_item calls should be made
        mock_dynamodb.meta.client.batch_write_item.assert_not_called()
