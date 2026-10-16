from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker
from sqlalchemy.pool import StaticPool

from tools import load_local_store_data


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:///./marketplace.db")
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


DATABASE_URL = _database_url()
if DATABASE_URL.startswith("sqlite:///./"):
    Path(DATABASE_URL.removeprefix("sqlite:///./")).parent.mkdir(parents=True, exist_ok=True)

engine_options: dict[str, object] = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
    if DATABASE_URL in {"sqlite://", "sqlite:///:memory:"}:
        engine_options["poolclass"] = StaticPool
engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    if os.getenv("ENVIRONMENT", "development").lower() == "production":
        raise RuntimeError("SECRET_KEY must be configured in production.")
    SECRET_KEY = secrets.token_urlsafe(48)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(20))
    store_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    products: Mapped[list[Product]] = relationship(back_populates="merchant")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    merchant_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    product: Mapped[str] = mapped_column(String(160), index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    store: Mapped[str] = mapped_column(String(120), index=True)
    price: Mapped[float] = mapped_column(Float)
    discount_price: Mapped[float] = mapped_column(Float)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    distance_km: Mapped[float] = mapped_column(Float, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    merchant: Mapped[User | None] = relationship(back_populates="products")
    reservations: Mapped[list[Reservation]] = relationship(back_populates="product")


class Reservation(Base):
    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    fulfillment: Mapped[str] = mapped_column(String(20))
    delivery_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    product: Mapped[Product] = relationship(back_populates="reservations")


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Literal["buyer", "merchant"] = "buyer"
    store_name: str | None = Field(default=None, min_length=2, max_length=120)

    @field_validator("store_name")
    @classmethod
    def clean_store_name(cls, value: str | None) -> str | None:
        cleaned = value.strip() if value else value
        if cleaned == "":
            raise ValueError("Store name cannot be blank.")
        return cleaned


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ProductRequest(BaseModel):
    product: str = Field(min_length=2, max_length=160)
    category: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=2000)
    store: str = Field(min_length=2, max_length=120)
    price: float = Field(gt=0, le=1000000, allow_inf_nan=False)
    discount_price: float = Field(gt=0, le=1000000, allow_inf_nan=False)
    quantity: int = Field(ge=0, le=1000000)
    distance_km: float = Field(ge=0, le=500, allow_inf_nan=False)

    @field_validator("product", "category", "description", "store")
    @classmethod
    def trim_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned and value:
            raise ValueError("This field cannot be blank.")
        return cleaned


class ReservationRequest(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=1000)
    fulfillment: Literal["pickup", "delivery"]
    delivery_address: str | None = Field(default=None, max_length=500)

    @field_validator("delivery_address")
    @classmethod
    def trim_address(cls, value: str | None) -> str | None:
        return value.strip() if value else value


class ReservationStatusRequest(BaseModel):
    status: Literal["confirmed", "ready", "completed", "cancelled"]


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
    return f"{salt.hex()}:{digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split(":", maxsplit=1)
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 310_000)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def create_token(user: User) -> str:
    payload = _b64encode(
        json.dumps(
            {"sub": user.id, "role": user.role, "exp": int(time.time()) + 60 * 60 * 24},
            separators=(",", ":"),
        ).encode("utf-8")
    )
    signature = hmac.new(str(SECRET_KEY).encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest()
    return f"{payload}.{_b64encode(signature)}"


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to continue.")
    try:
        payload, signature = authorization.removeprefix("Bearer ").split(".", maxsplit=1)
        expected = hmac.new(str(SECRET_KEY).encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest()
        padded_signature = signature + "=" * (-len(signature) % 4)
        if not hmac.compare_digest(expected, base64.urlsafe_b64decode(padded_signature)):
            raise ValueError("Invalid token signature")
        padded_payload = payload + "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(padded_payload))
        if int(claims["exp"]) <= int(time.time()):
            raise ValueError("Expired token")
        user = db.get(User, int(claims["sub"]))
        if user is None or user.role != claims["role"]:
            raise ValueError("Unknown user")
        return user
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your session is invalid or expired.") from None


def require_role(role: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role != role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"{role.title()} access is required.")
        return user

    return dependency


def product_json(product: Product) -> dict[str, object]:
    discount = round((1 - product.discount_price / product.price) * 100) if product.price else 0
    return {
        "id": product.id,
        "product": product.product,
        "category": product.category,
        "description": product.description,
        "store": product.store,
        "price": product.price,
        "discount_price": product.discount_price,
        "discount_percent": discount,
        "quantity": product.quantity,
        "distance_km": product.distance_km,
        "active": product.active,
    }


def reservation_json(reservation: Reservation) -> dict[str, object]:
    return {
        "id": reservation.id,
        "product_id": reservation.product_id,
        "product": product_json(reservation.product),
        "quantity": reservation.quantity,
        "fulfillment": reservation.fulfillment,
        "delivery_address": reservation.delivery_address,
        "status": reservation.status,
        "created_at": reservation.created_at.isoformat(),
    }


def seed_sample_products(db: Session) -> None:
    if db.scalar(select(Product.id).limit(1)) is not None:
        return
    for item in load_local_store_data():
        db.add(
            Product(
                product=item["product"],
                category=item["category"],
                description=f"Locally available at {item['store']}.",
                store=item["store"],
                price=item["price"],
                discount_price=item["discount_price"],
                quantity=12,
                distance_km=item["distance_km"],
                active=True,
            )
        )
    db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_sample_products(db)
    yield


app = FastAPI(title="Neighborhood Market API", version="1.0.0", lifespan=lifespan)

allowed_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

STATIC_DIR = Path(__file__).parent / "frontend"


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    if payload.role == "merchant" and not payload.store_name:
        raise HTTPException(status_code=422, detail="Store name is required for merchant accounts.")
    user = User(
        email=str(payload.email).lower(),
        password_hash=hash_password(payload.password),
        role=payload.role,
        store_name=payload.store_name,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists.") from None
    db.refresh(user)
    return {"token": create_token(user), "user": {"id": user.id, "email": user.email, "role": user.role, "store_name": user.store_name}}


@app.post("/api/auth/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == str(payload.email).lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    return {"token": create_token(user), "user": {"id": user.id, "email": user.email, "role": user.role, "store_name": user.store_name}}


@app.get("/api/auth/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email, "role": user.role, "store_name": user.store_name}


@app.get("/api/products")
def list_products(
    q: str = Query(default="", max_length=120),
    category: str | None = Query(default=None, max_length=80),
    max_distance: float = Query(default=50, ge=0, le=500),
    discounted: bool = False,
    db: Session = Depends(get_db),
):
    query = select(Product).where(Product.active.is_(True), Product.quantity > 0, Product.distance_km <= max_distance)
    if category and category.lower() != "all":
        query = query.where(Product.category == category)
    if discounted:
        query = query.where(Product.discount_price < Product.price)
    search_text = q.strip()
    if search_text:
        pattern = f"%{search_text}%"
        query = query.where(
            or_(
                Product.product.ilike(pattern),
                Product.category.ilike(pattern),
                Product.store.ilike(pattern),
                Product.description.ilike(pattern),
            )
        )
    products = db.scalars(query.order_by(Product.distance_km.asc(), Product.product.asc())).all()
    return {"products": [product_json(product) for product in products], "count": len(products)}


@app.post("/api/products", status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductRequest,
    db: Session = Depends(get_db),
    merchant: User = Depends(require_role("merchant")),
):
    if payload.discount_price > payload.price:
        raise HTTPException(status_code=422, detail="Discount price cannot be greater than the regular price.")
    product = Product(
        **{
            **payload.model_dump(),
            "merchant_id": merchant.id,
            "store": merchant.store_name or payload.store,
        }
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product_json(product)


@app.patch("/api/products/{product_id}")
def update_product(
    product_id: int,
    payload: ProductRequest,
    db: Session = Depends(get_db),
    merchant: User = Depends(require_role("merchant")),
):
    if payload.discount_price > payload.price:
        raise HTTPException(status_code=422, detail="Discount price cannot be greater than the regular price.")
    product = db.get(Product, product_id)
    if product is None or product.merchant_id != merchant.id:
        raise HTTPException(status_code=404, detail="Product not found.")
    for key, value in payload.model_dump().items():
        if key != "store":
            setattr(product, key, value)
    product.store = merchant.store_name or payload.store
    db.commit()
    db.refresh(product)
    return product_json(product)


@app.delete("/api/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_product(
    product_id: int,
    db: Session = Depends(get_db),
    merchant: User = Depends(require_role("merchant")),
):
    product = db.get(Product, product_id)
    if product is None or product.merchant_id != merchant.id:
        raise HTTPException(status_code=404, detail="Product not found.")
    product.active = False
    db.commit()


@app.post("/api/reservations", status_code=status.HTTP_201_CREATED)
def create_reservation(
    payload: ReservationRequest,
    db: Session = Depends(get_db),
    buyer: User = Depends(require_role("buyer")),
):
    if payload.fulfillment == "delivery" and not payload.delivery_address:
        raise HTTPException(status_code=422, detail="Enter a delivery address or choose store pickup.")
    result = db.execute(
        update(Product)
        .where(
            Product.id == payload.product_id,
            Product.active.is_(True),
            Product.quantity >= payload.quantity,
        )
        .values(quantity=Product.quantity - payload.quantity)
    )
    if result.rowcount != 1:
        exists = db.scalar(select(Product.id).where(Product.id == payload.product_id))
        if exists is None:
            raise HTTPException(status_code=404, detail="Product not found.")
        raise HTTPException(status_code=409, detail="This listing is unavailable or there is not enough stock.")
    reservation = Reservation(
        buyer_id=buyer.id,
        product_id=payload.product_id,
        quantity=payload.quantity,
        fulfillment=payload.fulfillment,
        delivery_address=payload.delivery_address if payload.fulfillment == "delivery" else None,
        status="pending",
    )
    db.add(reservation)
    db.commit()
    db.refresh(reservation)
    return reservation_json(reservation)


@app.get("/api/reservations")
def buyer_reservations(
    db: Session = Depends(get_db),
    buyer: User = Depends(require_role("buyer")),
):
    reservations = db.scalars(
        select(Reservation).where(Reservation.buyer_id == buyer.id).order_by(Reservation.created_at.desc())
    ).all()
    return {"reservations": [reservation_json(reservation) for reservation in reservations]}


@app.post("/api/reservations/{reservation_id}/cancel")
def cancel_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    buyer: User = Depends(require_role("buyer")),
):
    reservation = db.get(Reservation, reservation_id)
    if reservation is None or reservation.buyer_id != buyer.id:
        raise HTTPException(status_code=404, detail="Reservation not found.")
    result = db.execute(
        update(Reservation)
        .where(
            Reservation.id == reservation_id,
            Reservation.buyer_id == buyer.id,
            Reservation.status.not_in(("completed", "cancelled")),
        )
        .values(status="cancelled")
    )
    if result.rowcount != 1:
        raise HTTPException(status_code=409, detail="This reservation can no longer be cancelled.")
    product = db.get(Product, reservation.product_id)
    if product is not None:
        product.quantity += reservation.quantity
    db.commit()
    return reservation_json(db.get(Reservation, reservation_id))


@app.get("/api/merchant/products")
def merchant_products(
    db: Session = Depends(get_db),
    merchant: User = Depends(require_role("merchant")),
):
    products = db.scalars(select(Product).where(Product.merchant_id == merchant.id).order_by(Product.created_at.desc())).all()
    return {"products": [product_json(product) for product in products]}


@app.get("/api/merchant/reservations")
def merchant_reservations(
    db: Session = Depends(get_db),
    merchant: User = Depends(require_role("merchant")),
):
    reservations = db.scalars(
        select(Reservation)
        .join(Product)
        .where(Product.merchant_id == merchant.id)
        .order_by(Reservation.created_at.desc())
    ).all()
    return {"reservations": [reservation_json(reservation) for reservation in reservations]}


@app.patch("/api/merchant/reservations/{reservation_id}")
def update_reservation_status(
    reservation_id: int,
    payload: ReservationStatusRequest,
    db: Session = Depends(get_db),
    merchant: User = Depends(require_role("merchant")),
):
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise HTTPException(status_code=404, detail="Reservation not found.")
    product = db.get(Product, reservation.product_id)
    if product is None or product.merchant_id != merchant.id:
        raise HTTPException(status_code=404, detail="Reservation not found.")
    previous_status = reservation.status
    allowed_transitions = {
        "pending": {"confirmed", "cancelled"},
        "confirmed": {"ready", "cancelled"},
        "ready": {"completed", "cancelled"},
    }
    if payload.status not in allowed_transitions.get(previous_status, set()):
        raise HTTPException(status_code=409, detail=f"A reservation cannot move from {previous_status} to {payload.status}.")
    result = db.execute(
        update(Reservation)
        .where(
            Reservation.id == reservation_id,
            Reservation.status == previous_status,
        )
        .values(status=payload.status)
    )
    if result.rowcount != 1:
        raise HTTPException(status_code=409, detail="This reservation is already closed.")
    if payload.status == "cancelled":
        product.quantity += reservation.quantity
    db.commit()
    return reservation_json(db.get(Reservation, reservation_id))


@app.get("/api/categories")
def categories(db: Session = Depends(get_db)):
    return {
        "categories": db.scalars(
            select(Product.category).where(Product.active.is_(True)).distinct().order_by(Product.category)
        ).all()
    }


app.mount("/", StaticFiles(directory=STATIC_DIR), name="frontend")
