from __future__ import annotations

import logging
import os
import re
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv()

from app import ai, database
from app.security import (
    create_access_token,
    get_token_user_id,
    hash_password,
    verify_password,
)

PROJECT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_BUILD_DIR = PROJECT_DIR / "app" / "static" / "dist"
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not os.getenv("SECRET_KEY"):
        raise RuntimeError("Set SECRET_KEY in your environment or .env file before startup.")
    database.initialize_database()
    yield


app = FastAPI(
    title="Shop365 Marketplace API",
    description="A React marketplace backed by FastAPI and a LangGraph shopping assistant.",
    version="1.0.0",
    lifespan=lifespan,
)
app.mount(
    "/static",
    StaticFiles(directory=FRONTEND_BUILD_DIR, check_dir=False),
    name="static",
)


class GuestCreate(BaseModel):
    display_name: str = Field(default="Diwali Guest", min_length=1, max_length=80)


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    display_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class ProductCreate(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=1000)
    category: str = Field(default="Festive", min_length=2, max_length=50)
    price: float = Field(gt=0, le=1_000_000)
    stock: int = Field(ge=0, le=100_000)
    image_url: str = Field(default="", max_length=1000)


class CartItem(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=100)


class OrderCreate(BaseModel):
    items: list[CartItem] = Field(min_length=1, max_length=50)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    conversation_id: str = Field(
        default_factory=lambda: uuid4().hex,
        pattern=r"^[a-f0-9]{32}$",
    )


def current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Sign in or continue as a guest first.")
    user_id = get_token_user_id(authorization.removeprefix("Bearer ").strip())
    if user_id is None:
        raise HTTPException(status_code=401, detail="Your session is invalid or expired.")
    with database.connect() as connection:
        row = connection.execute(
            "SELECT id, email, display_name, is_guest FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Your account could not be found.")
    return database.row_to_dict(row)


def optional_user(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object] | None:
    return current_user(authorization) if authorization is not None else None


def auth_response(user: dict[str, object]) -> dict[str, object]:
    return {
        "access_token": create_access_token(int(user["id"])),
        "token_type": "bearer",
        "user": user,
    }


@app.get("/")
def storefront() -> FileResponse:
    index_file = FRONTEND_BUILD_DIR / "index.html"
    if not index_file.is_file():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "The React frontend is not built. Run `npm install` and "
                "`npm run build` in the frontend folder."
            ),
        )
    return FileResponse(index_file)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/ai/status")
def ai_status() -> dict[str, object]:
    return {
        "configured": ai.is_ai_configured(),
        "memory_turns": ai.MAX_MEMORY_TURNS,
        "max_graph_steps": ai.MAX_GRAPH_STEPS,
    }


@app.post("/api/auth/guest")
def create_guest(payload: GuestCreate) -> dict[str, object]:
    display_name = payload.display_name.strip() or "Diwali Guest"
    with database.connect() as connection:
        cursor = connection.execute(
            "INSERT INTO users (display_name, is_guest) VALUES (?, 1)",
            (display_name,),
        )
        user = {
            "id": cursor.lastrowid,
            "email": None,
            "display_name": display_name,
            "is_guest": 1,
        }
    return auth_response(user)


@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest) -> dict[str, object]:
    email = payload.email.strip().lower()
    display_name = payload.display_name.strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    if not display_name:
        raise HTTPException(status_code=422, detail="Your name cannot be blank.")
    try:
        with database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO users (email, display_name, password_hash)
                VALUES (?, ?, ?)
                """,
                (email, display_name, hash_password(payload.password)),
            )
            user = {
                "id": cursor.lastrowid,
                "email": email,
                "display_name": display_name,
                "is_guest": 0,
            }
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists.",
        ) from exc
    return auth_response(user)


@app.post("/api/auth/login")
def login(payload: LoginRequest) -> dict[str, object]:
    with database.connect() as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE email = ? AND is_guest = 0",
            (payload.email.strip().lower(),),
        ).fetchone()
    if row is None or not row["password_hash"] or not verify_password(
        payload.password, row["password_hash"]
    ):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    return auth_response(
        {
            "id": row["id"],
            "email": row["email"],
            "display_name": row["display_name"],
            "is_guest": row["is_guest"],
        }
    )


@app.get("/api/me")
def me(user: Annotated[dict[str, object], Depends(current_user)]) -> dict[str, object]:
    return user


@app.get("/api/products")
def list_products(
    category: str | None = None,
    search: str | None = None,
) -> list[dict[str, object]]:
    query = """
        SELECT p.id, p.title, p.description, p.category, p.price, p.stock,
               p.image_url, u.display_name AS seller_name
        FROM products p JOIN users u ON u.id = p.seller_id
        WHERE p.stock > 0
    """
    parameters: list[object] = []
    if category and category.lower() != "all":
        query += " AND p.category = ?"
        parameters.append(category)
    if search:
        query += " AND (p.title LIKE ? OR p.description LIKE ? OR p.category LIKE ?)"
        term = f"%{search.strip()}%"
        parameters.extend((term, term, term))
    query += " ORDER BY p.id DESC"
    with database.connect() as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [database.row_to_dict(row) for row in rows]


@app.get("/api/categories")
def list_categories() -> list[str]:
    with database.connect() as connection:
        rows = connection.execute(
            "SELECT DISTINCT category FROM products ORDER BY category"
        ).fetchall()
    return [str(row["category"]) for row in rows]


@app.post("/api/products", status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    user: Annotated[dict[str, object], Depends(current_user)],
) -> dict[str, object]:
    if user["is_guest"]:
        raise HTTPException(status_code=403, detail="Create an account to list products for sale.")
    if not payload.title.strip() or not payload.category.strip():
        raise HTTPException(status_code=422, detail="Product name and category cannot be blank.")
    with database.connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO products
                (seller_id, title, description, category, price, stock, image_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                payload.title.strip(),
                payload.description.strip(),
                payload.category.strip(),
                payload.price,
                payload.stock,
                payload.image_url.strip(),
            ),
        )
        row = connection.execute(
            """
            SELECT p.id, p.title, p.description, p.category, p.price, p.stock,
                   p.image_url, ? AS seller_name
            FROM products p WHERE p.id = ?
            """,
            (user["display_name"], cursor.lastrowid),
        ).fetchone()
    return database.row_to_dict(row)


@app.post("/api/orders", status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderCreate,
    user: Annotated[dict[str, object], Depends(current_user)],
) -> dict[str, object]:
    quantities: dict[int, int] = {}
    for item in payload.items:
        quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity

    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        order_lines: list[tuple[int, int, str, float, int]] = []
        total = 0.0
        for product_id, quantity in quantities.items():
            product = connection.execute(
                "SELECT id, seller_id, title, price, stock FROM products WHERE id = ?",
                (product_id,),
            ).fetchone()
            if product is None:
                raise HTTPException(status_code=404, detail="A product in your cart no longer exists.")
            if product["stock"] < quantity:
                raise HTTPException(
                    status_code=409,
                    detail=f"Not enough stock for {product['title']}. Please update your cart.",
                )
            price = float(product["price"])
            total += price * quantity
            order_lines.append(
                (product_id, product["seller_id"], product["title"], price, quantity)
            )

        cursor = connection.execute(
            "INSERT INTO orders (buyer_id, total) VALUES (?, ?)",
            (user["id"], round(total, 2)),
        )
        order_id = cursor.lastrowid
        for product_id, seller_id, title, price, quantity in order_lines:
            connection.execute(
                """
                INSERT INTO order_items
                    (order_id, product_id, seller_id, title, price, quantity)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (order_id, product_id, seller_id, title, price, quantity),
            )
            connection.execute(
                "UPDATE products SET stock = stock - ? WHERE id = ?",
                (quantity, product_id),
            )
    return {
        "id": order_id,
        "total": round(total, 2),
        "status": "confirmed",
        "message": "Demo order confirmed. No payment was collected.",
    }


@app.get("/api/orders")
def my_orders(
    user: Annotated[dict[str, object], Depends(current_user)],
) -> list[dict[str, object]]:
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT o.id, o.total, o.status, o.created_at,
                   GROUP_CONCAT(oi.title || ' x' || oi.quantity, ', ') AS items
            FROM orders o JOIN order_items oi ON oi.order_id = o.id
            WHERE o.buyer_id = ?
            GROUP BY o.id ORDER BY o.id DESC
            """,
            (user["id"],),
        ).fetchall()
    return [database.row_to_dict(row) for row in rows]


@app.get("/api/sales")
def my_sales(
    user: Annotated[dict[str, object], Depends(current_user)],
) -> list[dict[str, object]]:
    if user["is_guest"]:
        raise HTTPException(status_code=403, detail="Create an account to view seller sales.")
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT oi.order_id, oi.title, oi.price, oi.quantity,
                   ROUND(oi.price * oi.quantity, 2) AS subtotal,
                   o.status, o.created_at, buyer.display_name AS buyer_name
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            JOIN users buyer ON buyer.id = o.buyer_id
            WHERE oi.seller_id = ? ORDER BY o.id DESC
            """,
            (user["id"],),
        ).fetchall()
    return [database.row_to_dict(row) for row in rows]


@app.post("/api/assistant")
def shopping_assistant(
    payload: ChatRequest,
    user: Annotated[dict[str, object] | None, Depends(optional_user)],
) -> dict[str, str]:
    if not ai.is_ai_configured():
        raise HTTPException(
            status_code=503,
            detail="AI help is not configured. Add GROQ_API_KEY to your .env file.",
        )
    question = payload.message.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Please enter a shopping question.")
    try:
        answer = ai.answer_shopping_question(
            question,
            payload.conversation_id,
            user,
        )
    except Exception as exc:
        logger.exception("LangGraph shopping assistant request failed")
        raise HTTPException(
            status_code=502,
            detail="The AI shopping assistant could not complete that request. Please try again.",
        ) from exc
    return {"answer": answer, "conversation_id": payload.conversation_id}
