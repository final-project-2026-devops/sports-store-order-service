import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DYNAMODB_TABLE_NAME", "test-table")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ["JWT_SECRET"] = "test-secret"

import jwt
import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient

from database import get_db_table
from main import app

DEFAULT_USER_ID = "9c858901-8a57-4791-81fe-4c455b099bc9"


def make_token(user_id=DEFAULT_USER_ID, email="user@test.com",
               role="customer", expires_minutes=60):
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, "test-secret", algorithm="HS256")


@pytest.fixture
def mock_table():
    """AsyncMock standing in for the aioboto3 DynamoDB Table resource."""
    return AsyncMock()


@pytest.fixture
def client(mock_table):
    async def override_get_db_table():
        yield mock_table

    app.dependency_overrides[get_db_table] = override_get_db_table
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db_table, None)


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {make_token()}"}


@pytest.fixture
def admin_headers():
    return {"Authorization": f"Bearer {make_token(role='admin')}"}
