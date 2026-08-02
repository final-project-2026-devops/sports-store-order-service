from decimal import Decimal

from boto3.dynamodb.conditions import Key
from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials

import orchestrator
from database import orders_table
from models import CheckoutRequest
from security import bearer_scheme, get_current_user

router = APIRouter(prefix="/orders", tags=["orders"])


def _from_decimal(obj):
    """Recursively convert Decimal values for JSON serialisation."""
    if isinstance(obj, list):
        return [_from_decimal(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _from_decimal(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        f = float(obj)
        return int(f) if f == int(f) else f
    return obj


def serialize(doc: dict) -> dict:
    doc = _from_decimal(dict(doc))
    # Remove the counter sentinel item if it somehow ends up in results
    doc.pop("seq", None)
    return jsonable_encoder(doc)


@router.post("/checkout")
async def checkout(
    payload: CheckoutRequest,
    user: dict = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    order = await orchestrator.checkout(
        user, credentials.credentials, payload.shipping_address, payload.card_number
    )
    body = serialize(order)
    if order["status"] != "paid":
        return JSONResponse(status_code=402, content=body)
    return body


@router.get("")
async def list_orders(user: dict = Depends(get_current_user)):
    result = orders_table.query(
        IndexName="user-index",
        KeyConditionExpression=Key("user_id").eq(user["sub"]),
        ScanIndexForward=False,
    )
    orders = []
    for doc in result.get("Items", []):
        # Skip the counter sentinel item
        if doc["order_number"].startswith("COUNTER#"):
            continue
        orders.append(serialize(doc))
    return orders


@router.get("/{order_number}")
async def get_order(order_number: str, user: dict = Depends(get_current_user)):
    result = orders_table.get_item(Key={"order_number": order_number})
    doc = result.get("Item")
    if doc is None or (doc["user_id"] != user["sub"] and user.get("role") != "admin"):
        raise HTTPException(status_code=404, detail="Order not found")
    return serialize(doc)
