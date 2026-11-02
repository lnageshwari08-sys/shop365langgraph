from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

PROJECT_DIR = Path(__file__).resolve().parent.parent
_database_setting = Path(os.getenv("DATABASE_PATH", "data/shop365.db"))
DATABASE_PATH = (
    _database_setting
    if _database_setting.is_absolute()
    else PROJECT_DIR / _database_setting
)


@contextmanager
def connect() -> Generator[sqlite3.Connection, None, None]:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 15000")
    try:
        yield connection
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()
    finally:
        connection.close()


def initialize_database() -> None:
    with connect() as connection:
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE,
                display_name TEXT NOT NULL,
                password_hash TEXT,
                is_guest INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER NOT NULL REFERENCES users(id),
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'Festive',
                price REAL NOT NULL CHECK (price > 0),
                stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
                image_url TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                buyer_id INTEGER NOT NULL REFERENCES users(id),
                total REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'confirmed',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL REFERENCES orders(id),
                product_id INTEGER NOT NULL REFERENCES products(id),
                seller_id INTEGER NOT NULL REFERENCES users(id),
                title TEXT NOT NULL,
                price REAL NOT NULL,
                quantity INTEGER NOT NULL CHECK (quantity > 0)
            );
            CREATE INDEX IF NOT EXISTS idx_products_stock_category
                ON products(stock, category);
            CREATE INDEX IF NOT EXISTS idx_orders_buyer
                ON orders(buyer_id, id DESC);
            CREATE INDEX IF NOT EXISTS idx_order_items_seller
                ON order_items(seller_id, order_id DESC);
            """
        )
        seller = connection.execute(
            "SELECT id FROM users WHERE email = ?",
            ("shop@shop365.local",),
        ).fetchone()
        if seller is not None:
            return

        seller_id = connection.execute(
            """
            INSERT INTO users (email, display_name, password_hash)
            VALUES (?, ?, ?)
            """,
            ("shop@shop365.local", "Shop365 Bazaar", "system-account"),
        ).lastrowid
        products = [
            ("Brass Diya Set", "Hand-finished brass diyas for a warm festive glow.", "Decor", 799, 24),
            ("Rangoli Color Kit", "A bright set of festive rangoli colors.", "Decor", 349, 40),
            ("Kaju Katli Gift Box", "A celebratory assorted mithai box, perfect for gifting.", "Sweets", 599, 18),
            ("Festive String Lights", "Warm white LED lights for your home or balcony.", "Lighting", 499, 30),
            ("Decorative Toran", "A colorful handcrafted toran for your doorway.", "Decor", 449, 16),
            ("Diwali Gift Hamper", "A festive hamper with snacks, candles, and keepsakes.", "Gifts", 1299, 12),
        ]
        connection.executemany(
            """
            INSERT INTO products
                (seller_id, title, description, category, price, stock)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [(seller_id, *product) for product in products],
        )


def row_to_dict(row: sqlite3.Row) -> dict[str, object]:
    return dict(row)
