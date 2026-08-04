import re
from unittest.mock import AsyncMock, patch

USER_ID = "507f1f77bcf86cd799439011"

CART = {
    "items": [
        {
            "product_id": "507f1f77bcf86cd799439021",
            "sku": "VR-BLK-42",
            "name": "Velocity Runner",
            "size": "42",
            "color": "Black",
            "quantity": 2,
            "unit_price": 129.99,
            "image_url": "",
        }
    ],
    "subtotal": 259.98,
}

CHECKOUT_PAYLOAD = {
    "shipping_address": {
        "full_name": "Daniel Cohen",
        "street": "Example Street 10",
        "city": "Netanya",
        "postal_code": "1234567",
        "country": "Israel",
    },
    "card_number": "4242424242424242",
}


def setup_mocks(mock_clients, mock_orders_table, payment_status="succeeded"):
    mock_clients.get_cart = AsyncMock(return_value=CART)
    mock_clients.check_stock = AsyncMock(
        return_value=[{"sku": "VR-BLK-42", "available": 15, "in_stock": True}]
    )
    mock_clients.charge = AsyncMock(
        return_value={"payment_id": "pay_123", "status": payment_status}
    )
    mock_clients.decrement_stock = AsyncMock(return_value=True)
    mock_clients.clear_cart = AsyncMock()
    # orders_table is a real (synchronous) boto3 Table object in production.
    mock_orders_table.update_item.return_value = {"Attributes": {"seq": 123}}


def test_checkout_happy_path(client, auth_headers):
    with patch("orchestrator.clients") as mock_clients, \
         patch("orchestrator.orders_table") as mock_orders_table:
        setup_mocks(mock_clients, mock_orders_table)
        response = client.post(
            "/api/orders/checkout", json=CHECKOUT_PAYLOAD, headers=auth_headers
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "paid"
    assert re.fullmatch(r"ORD-\d{6}", body["order_number"])
    assert body["order_number"] == "ORD-000123"
    # subtotal 259.98 > 100 → free shipping
    assert body["pricing"] == {
        "subtotal": 259.98,
        "shipping": 0.0,
        "total": 259.98,
        "currency": "USD",
    }
    assert body["payment"]["payment_id"] == "pay_123"
    mock_clients.decrement_stock.assert_awaited_once()
    mock_clients.clear_cart.assert_awaited_once()
    charge_payload = mock_clients.charge.call_args.args[0]
    assert charge_payload["idempotency_key"] == body["order_number"]
    assert charge_payload["amount"] == 259.98
    mock_orders_table.put_item.assert_called_once()
    # once to allocate the order number, once to record the final status
    assert mock_orders_table.update_item.call_count == 2


def test_checkout_payment_failure_402(client, auth_headers):
    with patch("orchestrator.clients") as mock_clients, \
         patch("orchestrator.orders_table") as mock_orders_table:
        setup_mocks(mock_clients, mock_orders_table, payment_status="failed")
        response = client.post(
            "/api/orders/checkout", json=CHECKOUT_PAYLOAD, headers=auth_headers
        )

    assert response.status_code == 402
    assert response.json()["status"] == "payment_failed"
    mock_clients.decrement_stock.assert_not_awaited()
    mock_clients.clear_cart.assert_not_awaited()


def test_checkout_empty_cart_400(client, auth_headers):
    with patch("orchestrator.clients") as mock_clients, \
         patch("orchestrator.orders_table") as mock_orders_table:
        mock_clients.get_cart = AsyncMock(return_value={"items": [], "subtotal": 0})
        response = client.post(
            "/api/orders/checkout", json=CHECKOUT_PAYLOAD, headers=auth_headers
        )

    assert response.status_code == 400
    mock_orders_table.put_item.assert_not_called()


def test_checkout_out_of_stock_409(client, auth_headers):
    with patch("orchestrator.clients") as mock_clients, \
         patch("orchestrator.orders_table") as mock_orders_table:
        mock_clients.get_cart = AsyncMock(return_value=CART)
        mock_clients.check_stock = AsyncMock(
            return_value=[{"sku": "VR-BLK-42", "available": 1, "in_stock": False}]
        )
        response = client.post(
            "/api/orders/checkout", json=CHECKOUT_PAYLOAD, headers=auth_headers
        )

    assert response.status_code == 409
    assert response.json()["detail"]["skus"] == ["VR-BLK-42"]
    mock_orders_table.put_item.assert_not_called()


def test_checkout_shipping_added_below_threshold(client, auth_headers):
    small_cart = {
        "items": [dict(CART["items"][0], quantity=1, unit_price=49.99)],
        "subtotal": 49.99,
    }
    with patch("orchestrator.clients") as mock_clients, \
         patch("orchestrator.orders_table") as mock_orders_table:
        setup_mocks(mock_clients, mock_orders_table)
        mock_clients.get_cart = AsyncMock(return_value=small_cart)
        response = client.post(
            "/api/orders/checkout", json=CHECKOUT_PAYLOAD, headers=auth_headers
        )

    assert response.status_code == 200
    assert response.json()["pricing"] == {
        "subtotal": 49.99,
        "shipping": 5.0,
        "total": 54.99,
        "currency": "USD",
    }


def test_checkout_requires_token(client):
    response = client.post("/api/orders/checkout", json=CHECKOUT_PAYLOAD)
    assert response.status_code == 401
