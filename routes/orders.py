from boto3.dynamodb.conditions import Attr
from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials

import orchestrator
from database import from_dynamo, get_db_table
from models import CheckoutRequest
from security import bearer_scheme, get_current_user

router = APIRouter(prefix="/orders", tags=["orders"])


def serialize(doc: dict) -> dict:
    return jsonable_encoder(from_dynamo(dict(doc)))


@router.post("/checkout")
async def checkout(
    payload: CheckoutRequest,
    user: dict = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    table=Depends(get_db_table),
):
    order = await orchestrator.checkout(
        table, user, credentials.credentials, payload.shipping_address, payload.card_number
    )
    body = serialize(order)
    if order["status"] != "paid":
        return JSONResponse(status_code=402, content=body)
    return body


@router.get("")
async def list_orders(user: dict = Depends(get_current_user), table=Depends(get_db_table)):
    orders = []
    scan_kwargs = {"FilterExpression": Attr("user_id").eq(user["sub"])}
    while True:
        response = await table.scan(**scan_kwargs)
        orders.extend(response.get("Items", []))
        last_evaluated_key = response.get("LastEvaluatedKey")
        if not last_evaluated_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_evaluated_key
    orders.sort(key=lambda o: o["created_at"], reverse=True)
    return [serialize(doc) for doc in orders]


@router.get("/{order_number}")
async def get_order(
    order_number: str, user: dict = Depends(get_current_user), table=Depends(get_db_table)
):
    response = await table.scan(FilterExpression=Attr("order_number").eq(order_number))
    items = response.get("Items", [])
    doc = items[0] if items else None
    if doc is None or (doc["user_id"] != user["sub"] and user.get("role") != "admin"):
        raise HTTPException(status_code=404, detail="Order not found")
    return serialize(doc)
