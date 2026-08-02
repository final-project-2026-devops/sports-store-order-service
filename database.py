import os
from decimal import Decimal

import aioboto3
from dotenv import load_dotenv

load_dotenv()

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
DYNAMODB_TABLE_NAME = os.environ["DYNAMODB_TABLE_NAME"]

session = aioboto3.Session()


async def get_db_table():
    async with session.resource("dynamodb", region_name=AWS_REGION) as dynamodb:
        table = await dynamodb.Table(DYNAMODB_TABLE_NAME)
        yield table


def to_dynamo(value):
    """Recursively convert Python floats to Decimal for DynamoDB storage
    (the DynamoDB item serializer rejects native float values)."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: to_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_dynamo(v) for v in value]
    return value


def from_dynamo(value):
    """Recursively convert Decimal values read back from DynamoDB to floats."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: from_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [from_dynamo(v) for v in value]
    return value
