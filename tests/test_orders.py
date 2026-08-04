from unittest.mock import patch

from tests.conftest import make_token

USER_ID = "507f1f77bcf86cd799439011"

ORDER = {
    "order_number": "ORD-000123",
    "user_id": USER_ID,
    "status": "paid",
    "items": [],
    "pricing": {"subtotal": 259.98, "shipping": 0.0, "total": 259.98,
                "currency": "USD"},
    "shipping_address": {
        "full_name": "Daniel Cohen", "street": "Example Street 10",
        "city": "Netanya", "postal_code": "1234567", "country": "Israel",
    },
    "payment": {"payment_id": "pay_123", "idempotency_key": "ORD-000123"},
    "created_at": "2026-07-18T00:00:00+00:00",
    "updated_at": "2026-07-18T00:00:00+00:00",
}


def test_list_orders_own_history(client, auth_headers):
    with patch("routes.orders.orders_table") as mock_table:
        mock_table.query.return_value = {"Items": [ORDER.copy()]}
        response = client.get("/api/orders", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["order_number"] == "ORD-000123"
    kwargs = mock_table.query.call_args.kwargs
    assert kwargs["IndexName"] == "user-index"
    assert kwargs["ScanIndexForward"] is False


def test_get_order_by_number(client, auth_headers):
    with patch("routes.orders.orders_table") as mock_table:
        mock_table.get_item.return_value = {"Item": ORDER.copy()}
        response = client.get("/api/orders/ORD-000123", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["status"] == "paid"


def test_get_foreign_order_404(client):
    other_user = make_token(user_id="507f1f77bcf86cd799439099")
    with patch("routes.orders.orders_table") as mock_table:
        mock_table.get_item.return_value = {"Item": ORDER.copy()}
        response = client.get(
            "/api/orders/ORD-000123",
            headers={"Authorization": f"Bearer {other_user}"},
        )

    assert response.status_code == 404


def test_admin_can_view_any_order(client, admin_headers):
    with patch("routes.orders.orders_table") as mock_table:
        mock_table.get_item.return_value = {"Item": ORDER.copy()}
        response = client.get("/api/orders/ORD-000123", headers=admin_headers)

    assert response.status_code == 200


def test_get_unknown_order_404(client, auth_headers):
    with patch("routes.orders.orders_table") as mock_table:
        mock_table.get_item.return_value = {}
        response = client.get("/api/orders/ORD-000000", headers=auth_headers)

    assert response.status_code == 404


def test_list_orders_requires_token(client):
    response = client.get("/api/orders")
    assert response.status_code == 401
