from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import ai, database
from app.main import FRONTEND_BUILD_DIR, app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "unit-test-secret-key")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "shop365-test.db")
    with TestClient(app) as test_client:
        yield test_client


def guest_token(client: TestClient, name: str = "Guest Shopper") -> str:
    response = client.post("/api/auth/guest", json={"display_name": name})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_health_and_fresh_seed_catalog(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}
    products = client.get("/api/products").json()
    assert len(products) == 6
    assert "Brass Diya Set" in {product["title"] for product in products}
    assert client.get("/api/categories").json() == ["Decor", "Gifts", "Lighting", "Sweets"]


def test_react_build_is_served_when_present(client: TestClient) -> None:
    page = client.get("/")
    if not (FRONTEND_BUILD_DIR / "index.html").is_file():
        assert page.status_code == 503
        assert "npm run build" in page.json()["detail"]
        return

    assert page.status_code == 200
    assert 'id="root"' in page.text
    assert "Shop365" in page.text
    script_path = next(
        line.split('src="', 1)[1].split('"', 1)[0]
        for line in page.text.splitlines()
        if ".js" in line and "src=" in line
    )
    script = client.get(script_path)
    assert script.status_code == 200
    assert "createRoot" in script.text


def test_guest_can_place_demo_order_and_stock_is_reduced(client: TestClient) -> None:
    token = guest_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    before = client.get("/api/products").json()[0]

    order = client.post(
        "/api/orders",
        headers=headers,
        json={"items": [{"product_id": before["id"], "quantity": 2}]},
    )

    assert order.status_code == 201
    assert order.json()["total"] == before["price"] * 2
    assert "No payment was collected" in order.json()["message"]
    assert client.get("/api/orders", headers=headers).json()[0]["id"] == order.json()["id"]
    updated = next(
        product for product in client.get("/api/products").json()
        if product["id"] == before["id"]
    )
    assert updated["stock"] == before["stock"] - 2


def test_registration_login_and_seller_sales(client: TestClient) -> None:
    registered = client.post(
        "/api/auth/register",
        json={
            "email": "seller@example.com",
            "display_name": "Festive Maker",
            "password": "a-secure-password",
        },
    )
    assert registered.status_code == 201
    duplicate = client.post(
        "/api/auth/register",
        json={
            "email": "seller@example.com",
            "display_name": "Another Name",
            "password": "a-secure-password",
        },
    )
    assert duplicate.status_code == 409

    login = client.post(
        "/api/auth/login",
        json={"email": "seller@example.com", "password": "a-secure-password"},
    )
    assert login.status_code == 200
    seller_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    product = client.post(
        "/api/products",
        headers=seller_headers,
        json={
            "title": "Hand-painted Diya",
            "description": "Made with care",
            "category": "Decor",
            "price": 250,
            "stock": 3,
        },
    )
    assert product.status_code == 201

    buyer_headers = {"Authorization": f"Bearer {guest_token(client)}"}
    order = client.post(
        "/api/orders",
        headers=buyer_headers,
        json={"items": [{"product_id": product.json()["id"], "quantity": 1}]},
    )
    assert order.status_code == 201
    sales = client.get("/api/sales", headers=seller_headers)
    assert sales.status_code == 200
    assert sales.json()[0]["title"] == "Hand-painted Diya"
    assert sales.json()[0]["subtotal"] == 250


def test_order_stock_validation_is_atomic(client: TestClient) -> None:
    headers = {"Authorization": f"Bearer {guest_token(client)}"}
    existing = client.get("/api/products").json()[0]
    seller = client.post(
        "/api/auth/register",
        json={
            "email": "empty-stock@example.com",
            "display_name": "Stock Seller",
            "password": "a-secure-password",
        },
    ).json()
    product = client.post(
        "/api/products",
        headers={"Authorization": f"Bearer {seller['access_token']}"},
        json={"title": "Sold Out Item", "price": 99, "stock": 0},
    )
    assert product.status_code == 201

    failed = client.post(
        "/api/orders",
        headers=headers,
        json={
            "items": [
                {"product_id": existing["id"], "quantity": 1},
                {"product_id": product.json()["id"], "quantity": 1},
            ]
        },
    )
    assert failed.status_code == 409
    assert client.get("/api/orders", headers=headers).json() == []
    still_available = next(
        item for item in client.get("/api/products").json()
        if item["id"] == existing["id"]
    )
    assert still_available["stock"] == existing["stock"]


def test_guest_cannot_list_products_and_ai_reports_missing_key(client: TestClient) -> None:
    guest_headers = {"Authorization": f"Bearer {guest_token(client)}"}
    create_product = client.post(
        "/api/products",
        headers=guest_headers,
        json={"title": "Guest Listing", "price": 20, "stock": 1},
    )
    assert create_product.status_code == 403
    assistant = client.post("/api/assistant", json={"message": "Suggest a gift"})
    assert assistant.status_code == 503


def test_assistant_rejects_malformed_conversation_id(client: TestClient) -> None:
    response = client.post(
        "/api/assistant",
        json={"message": "Suggest a gift", "conversation_id": "not-a-valid-id"},
    )
    assert response.status_code == 422


def test_assistant_uses_the_authenticated_user_and_requested_thread(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    account = client.post(
        "/api/auth/register",
        json={
            "email": "assistant-user@example.com",
            "display_name": "Assistant User",
            "password": "a-secure-password",
        },
    ).json()
    observed: list[tuple[str, str, int | None]] = []

    def fake_answer(question, conversation_id, user):
        observed.append((
            question,
            conversation_id,
            user["id"] if user else None,
        ))
        return "Found it."

    monkeypatch.setattr(ai, "answer_shopping_question", fake_answer)
    conversation_id = "c" * 32
    anonymous_response = client.post(
        "/api/assistant",
        json={"message": "Find a gift", "conversation_id": conversation_id},
    )
    signed_in_response = client.post(
        "/api/assistant",
        headers={"Authorization": f"Bearer {account['access_token']}"},
        json={"message": "Find a gift", "conversation_id": conversation_id},
    )

    expected_response = {
        "answer": "Found it.",
        "conversation_id": conversation_id,
    }
    assert anonymous_response.status_code == 200
    assert anonymous_response.json() == expected_response
    assert signed_in_response.status_code == 200
    assert signed_in_response.json() == expected_response
    assert observed == [
        ("Find a gift", conversation_id, None),
        ("Find a gift", conversation_id, account["user"]["id"]),
    ]


def test_assistant_failures_are_logged_and_return_a_clear_error(
    client: TestClient,
    monkeypatch,
    caplog,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    def fail_request(*_args):
        raise TimeoutError("simulated upstream timeout")

    monkeypatch.setattr(ai, "answer_shopping_question", fail_request)
    response = client.post("/api/assistant", json={"message": "Suggest a gift"})

    assert response.status_code == 502
    assert "could not complete" in response.json()["detail"]
    assert "LangGraph shopping assistant request failed" in caplog.text


def test_account_and_product_fields_cannot_be_whitespace_only(client: TestClient) -> None:
    registration = client.post(
        "/api/auth/register",
        json={"email": "valid@example.com", "display_name": "   ", "password": "password-123"},
    )
    assert registration.status_code == 422

    account = client.post(
        "/api/auth/register",
        json={
            "email": "seller@example.com",
            "display_name": "Seller",
            "password": "password-123",
        },
    ).json()
    product = client.post(
        "/api/products",
        headers={"Authorization": f"Bearer {account['access_token']}"},
        json={"title": "  ", "category": "Decor", "price": 99, "stock": 1},
    )
    assert product.status_code == 422


def test_storefront_and_react_source_are_independent_of_react_cdn() -> None:
    source_dir = Path(__file__).parents[1] / "frontend"
    html = (source_dir / "index.html").read_text(encoding="utf-8")
    source = (source_dir / "src" / "main.jsx").read_text(encoding="utf-8")
    assert "cdn.jsdelivr.net" not in html
    assert "createRoot" in source
