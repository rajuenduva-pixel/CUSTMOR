import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-not-used-outside-tests"
os.environ["ENVIRONMENT"] = "test"

import pytest
from fastapi.testclient import TestClient

from server import Base, app, engine


@pytest.fixture
def client():
    Base.metadata.drop_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client


def register(client: TestClient, email: str, role: str = "buyer", store_name: str | None = None):
    return client.post(
        "/api/auth/register",
        json={"email": email, "password": "safe-password-123", "role": role, "store_name": store_name},
    )


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_listing(client: TestClient, token: str, quantity: int = 3):
    return client.post(
        "/api/products",
        headers=auth(token),
        json={
            "product": "Local honey",
            "category": "Pantry",
            "description": "Small-batch neighborhood honey",
            "store": "Ignored display name",
            "price": 200,
            "discount_price": 150,
            "quantity": quantity,
            "distance_km": 1.2,
        },
    )


def test_sample_catalog_and_filters(client: TestClient):
    response = client.get("/api/products", params={"category": "Dairy", "max_distance": 2})
    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["products"][0]["product"] == "Organic Milk (1L)"
    assert client.get("/api/health").json() == {"status": "ok"}


def test_auth_and_merchant_listing_ownership(client: TestClient):
    merchant_response = register(client, "shop@example.com", "merchant", "Sunny Corner Shop")
    assert merchant_response.status_code == 201
    merchant_token = merchant_response.json()["token"]
    listing_response = create_listing(client, merchant_token)
    assert listing_response.status_code == 201
    assert listing_response.json()["store"] == "Sunny Corner Shop"

    other_merchant = register(client, "other@example.com", "merchant", "Other Shop").json()["token"]
    product_id = listing_response.json()["id"]
    update_response = client.patch(
        f"/api/products/{product_id}",
        headers=auth(other_merchant),
        json={
            "product": "Changed",
            "category": "Pantry",
            "description": "",
            "store": "Other Shop",
            "price": 100,
            "discount_price": 80,
            "quantity": 3,
            "distance_km": 1,
        },
    )
    assert update_response.status_code == 404
    assert register(client, "shop@example.com").status_code == 409


def test_reservation_inventory_and_cancellation(client: TestClient):
    merchant_token = register(client, "seller@example.com", "merchant", "Bee & Bloom").json()["token"]
    listing = create_listing(client, merchant_token, quantity=3).json()
    buyer_token = register(client, "buyer@example.com").json()["token"]

    invalid = client.post(
        "/api/reservations",
        headers=auth(buyer_token),
        json={"product_id": listing["id"], "quantity": 4, "fulfillment": "pickup"},
    )
    assert invalid.status_code == 409
    no_address = client.post(
        "/api/reservations",
        headers=auth(buyer_token),
        json={"product_id": listing["id"], "quantity": 1, "fulfillment": "delivery"},
    )
    assert no_address.status_code == 422

    created = client.post(
        "/api/reservations",
        headers=auth(buyer_token),
        json={
            "product_id": listing["id"],
            "quantity": 2,
            "fulfillment": "delivery",
            "delivery_address": "12 Green Lane",
        },
    )
    assert created.status_code == 201
    reservation = created.json()
    assert reservation["status"] == "pending"
    assert client.get("/api/products", params={"q": "Local honey"}).json()["products"][0]["quantity"] == 1

    cancelled = client.post(
        f"/api/reservations/{reservation['id']}/cancel",
        headers=auth(buyer_token),
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert client.get("/api/products", params={"q": "Local honey"}).json()["products"][0]["quantity"] == 3
    assert client.post(
        f"/api/reservations/{reservation['id']}/cancel",
        headers=auth(buyer_token),
    ).status_code == 409


def test_merchant_reservation_flow_and_role_guards(client: TestClient):
    merchant_token = register(client, "merchant@example.com", "merchant", "Harvest Table").json()["token"]
    listing = create_listing(client, merchant_token).json()
    buyer_token = register(client, "customer@example.com").json()["token"]
    reservation = client.post(
        "/api/reservations",
        headers=auth(buyer_token),
        json={"product_id": listing["id"], "quantity": 1, "fulfillment": "pickup"},
    ).json()
    merchant_update = client.patch(
        f"/api/merchant/reservations/{reservation['id']}",
        headers=auth(merchant_token),
        json={"status": "confirmed"},
    )
    assert merchant_update.status_code == 200
    assert merchant_update.json()["status"] == "confirmed"
    assert client.get("/api/merchant/products", headers=auth(buyer_token)).status_code == 403
    assert client.get("/api/merchant/reservations", headers=auth(merchant_token)).json()["reservations"][0]["id"] == reservation["id"]


def test_invalid_discount_and_unauthenticated_writes(client: TestClient):
    merchant_token = register(client, "invalid@example.com", "merchant", "Corner Shop").json()["token"]
    create_listing(client, merchant_token)
    listing = {
        "product": "Price test",
        "category": "Pantry",
        "description": "",
        "store": "Corner Shop",
        "price": 10,
        "discount_price": 12,
        "quantity": 2,
        "distance_km": 1,
    }
    assert client.post("/api/products", json=listing).status_code == 401
    invalid_price = client.post(
        "/api/products",
        headers=auth(merchant_token),
        json=listing,
    )
    assert invalid_price.status_code == 422
