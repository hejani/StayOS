"""Shared pytest fixtures for LUMI backend tests."""

import os

import pytest


@pytest.fixture(autouse=True)
def aws_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set mock AWS environment variables for all tests.

    This fixture ensures Lambda function code that reads environment
    variables at module level will find valid values during testing.
    """
    monkeypatch.setenv("BRIEFS_TABLE_NAME", "stayos-briefs-test")
    monkeypatch.setenv("SETTINGS_TABLE_NAME", "stayos-settings-test")
    monkeypatch.setenv("AUDIO_BUCKET_NAME", "stayos-audio-test-000000000000")
    monkeypatch.setenv("AUDIO_CLOUDFRONT_DOMAIN", "d1234567890.cloudfront.net")
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_TestPool")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "amazon.claude-3-5-sonnet-20241022-v2:0")
    monkeypatch.setenv("SPOG_API_ENDPOINT", "https://spog-api.test.example.com")
    monkeypatch.setenv("MDP_API_ENDPOINT", "https://mdp-api.test.example.com")
    monkeypatch.setenv("SPOG_SECRET_ARN", "arn:aws:secretsmanager:us-east-1:000000000000:secret:lumi/spog/api-key")
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://test.cloudfront.net")
    monkeypatch.setenv("MOCK_MODE", "true")
    monkeypatch.setenv("RESERVATIONS_TABLE_NAME", "stayos-reservations-test")
    monkeypatch.setenv("ROOMS_TABLE_NAME", "stayos-rooms-test")
    monkeypatch.setenv("GUESTS_TABLE_NAME", "stayos-guests-test")
    monkeypatch.setenv("REVENUES_TABLE_NAME", "stayos-revenues-test")
    monkeypatch.setenv("WORK_ORDERS_TABLE_NAME", "stayos-work-orders-test")
    monkeypatch.setenv("DEMO_PASSWORD", "TestPassword123!")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("SCHEDULE_GROUP_NAME", "stayos-briefs")
    monkeypatch.setenv("SCHEDULER_ROLE_ARN", "arn:aws:iam::000000000000:role/stayos-scheduler-role")
    monkeypatch.setenv("ORCHESTRATOR_ARN", "arn:aws:lambda:us-east-1:000000000000:function:stayos-orchestrator")
    monkeypatch.setenv("STACK_PREFIX", "lumi")

