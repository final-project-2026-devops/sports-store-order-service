import logging
from datetime import datetime, timezone
from decimal import Decimal
from os import environ

from fastapi import HTTPException

import clients
from database import orders_table
from models import ShippingAddress

logger = logging.getLogger("order-service")

SHIPPING_FLAT_RATE = float(environ.get("SHIPPING_FLAT_RATE", "5.00"))
FREE_SHIPPING_THRESHOLD = float(environ.get("FREE_SHIPPING_THRESHOLD", "100"))


def next_order_number() -> str:
    year = datetime.now(timezone.utc).year
    result = orders_table.update_item(
        Key={"order_number": f"COUNTER#{year}"},
        UpdateExpression="ADD seq :one",
        ExpressionAttributeValues={":one": 1},
        ReturnValues="UPDATED_NEW",
    )
    seq = int(result["Attributes"]["seq"])
    return f"ORD-{seq:06d}"


def build_pricing(items: list[dict]) -> dict:
    subtotal = round(sum(i["quantity"] * i["unit_price"] for i in items), 2)
    shipping = 0.0 if subtotal >= FREE_SHIPPING_THRESHOLD else SHIPPING_FLAT_RATE
    return {
        "subtotal": subtotal,
        "shipping": shipping,
        "total": round(subtotal + shipping, 2),
        "currency": "USD",
    }


def _to_decimal(obj):
    """Recursively convert floats to Decimal for DynamoDB storage."""
    if isinstance(obj, list):
        return [_to_decimal(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, float):
        return Decimal(str(obj))
    return obj


def _from_decimal(obj):
    """Recursively convert Decimal back to float/int for response serialisation."""
    if isinstance(obj, list):
        return [_from_decimal(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _from_decimal(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        f = float(obj)
        return int(f) if f == int(f) else f
    return obj


async def checkout(
    user: dict, token: str, shipping_address: ShippingAddress, card_number: str
) -> dict:
    cart = await clients.get_cart(token)
    items = cart.get("items", [])
    if not items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    stock_items = [{"sku": i["sku"], "quantity": i["quantity"]} for i in items]
    stock = await clients.check_stock(stock_items, token)
    short = [entry["sku"] for entry in stock if not entry["in_stock"]]
    if short:
        raise HTTPException(
            status_code=409,
            detail={"message": "Insufficient stock", "skus": short},
        )

    order_number = next_order_number()
    pricing = build_pricing(items)
    order = {
        "order_number": order_number,
        "user_id": user["sub"],
        "status": "pending",
        "items": items,
        "pricing": pricing,
        "shipping_address": shipping_address.model_dump(),
        "payment": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    orders_table.put_item(Item=_to_decimal(order))

    payment = await clients.charge(
        {
            "idempotency_key": order_number,
            "order_number": order_number,
            "amount": pricing["total"],
            "currency": pricing["currency"],
            "card_number": card_number,
        },
        token,
    )

    if payment["status"] == "succeeded":
        decremented = await clients.decrement_stock(stock_items, token)
        if not decremented:
            logger.error("Stock decrement failed after payment for %s", order_number)
        await clients.clear_cart(token)
        new_status = "paid"
    else:
        new_status = "payment_failed"

    order["status"] = new_status
    order["payment"] = {
        "payment_id": payment["payment_id"],
        "idempotency_key": order_number,
    }
    order["updated_at"] = datetime.now(timezone.utc).isoformat()

    orders_table.update_item(
        Key={"order_number": order_number},
        UpdateExpression="SET #s = :status, payment = :payment, updated_at = :updated_at",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":status": new_status,
            ":payment": order["payment"],
            ":updated_at": order["updated_at"],
        },
    )
    return order
