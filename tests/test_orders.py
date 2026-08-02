from unittest.mock import AsyncMock

from tests.conftest import DEFAULT_USER_ID, make_token

USER_ID = DEFAULT_USER_ID

ORDER = {
    "order_id": "0b0e5a6a-2f2b-4b0a-9c1a-2c1e9b6b3a11",
    "order_number": "ORD-2026-000123",
    "user_id": USER_ID,
    "status": "paid",
    "items": [],
    "pricing": {"subtotal": 259.98, "shipping": 0.0, "total": 259.98,
                "currency": "USD"},
    "shipping_address": {
        "full_name": "Daniel Cohen", "street": "Example Street 10",
        "city": "Netanya", "postal_code": "1234567", "country": "Israel",
    },
    "payment": {"payment_id": "pay_123", "idempotency_key": "ORD-2026-000123"},
    "created_at": "2026-07-18T00:00:00+00:00",
    "updated_at": "2026-07-18T00:00:00+00:00",
}


def test_list_orders_own_history(client, mock_table, auth_headers):
    mock_table.scan = AsyncMock(return_value={"Items": [dict(ORDER)]})
    response = client.get("/api/orders", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["order_number"] == "ORD-2026-000123"
    assert "_id" not in body[0]
    scan_kwargs = mock_table.scan.call_args.kwargs
    filter_expr = scan_kwargs["FilterExpression"]
    attr, value = filter_expr._values
    assert attr.name == "user_id"
    assert value == USER_ID


def test_list_orders_paginates_scan(client, mock_table, auth_headers):
    mock_table.scan = AsyncMock(
        side_effect=[
            {"Items": [dict(ORDER, order_number="ORD-2026-000001")],
             "LastEvaluatedKey": {"order_id": "page-1"}},
            {"Items": [dict(ORDER, order_number="ORD-2026-000002")]},
        ]
    )
    response = client.get("/api/orders", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert {o["order_number"] for o in body} == {"ORD-2026-000001", "ORD-2026-000002"}
    assert mock_table.scan.await_count == 2
    second_call_kwargs = mock_table.scan.call_args_list[1].kwargs
    assert second_call_kwargs["ExclusiveStartKey"] == {"order_id": "page-1"}


def test_get_order_by_number(client, mock_table, auth_headers):
    mock_table.scan = AsyncMock(return_value={"Items": [dict(ORDER)]})
    response = client.get("/api/orders/ORD-2026-000123", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["status"] == "paid"


def test_get_foreign_order_404(client, mock_table):
    other_user = make_token(user_id="4b6f0a0e-2b6b-4b0a-9c1a-2c1e9b6b3a99")
    mock_table.scan = AsyncMock(return_value={"Items": [dict(ORDER)]})
    response = client.get(
        "/api/orders/ORD-2026-000123",
        headers={"Authorization": f"Bearer {other_user}"},
    )

    assert response.status_code == 404


def test_admin_can_view_any_order(client, mock_table, admin_headers):
    mock_table.scan = AsyncMock(return_value={"Items": [dict(ORDER)]})
    response = client.get("/api/orders/ORD-2026-000123", headers=admin_headers)

    assert response.status_code == 200


def test_get_unknown_order_404(client, mock_table, auth_headers):
    mock_table.scan = AsyncMock(return_value={"Items": []})
    response = client.get("/api/orders/ORD-0000-000000", headers=auth_headers)

    assert response.status_code == 404


def test_list_orders_requires_token(client):
    response = client.get("/api/orders")
    assert response.status_code == 401
