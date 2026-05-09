"""SQLite persistence layer for caching market data and managing watchlists."""

import json
import logging
import sqlite3
import threading
from datetime import datetime, date
from pathlib import Path
from typing import Any

logger = logging.getLogger("a-stock-mcp.storage")

DB_PATH = Path(__file__).resolve().parent / "data" / "stock.db"


def _get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db():
    """Initialize schema — safe to call multiple times."""
    with _get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS watchlist (
                symbol TEXT PRIMARY KEY,
                name TEXT,
                added_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS kline_cache (
                symbol TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL, high REAL, low REAL, close REAL,
                volume REAL, amount REAL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                PRIMARY KEY (symbol, date)
            );

            CREATE TABLE IF NOT EXISTS quote_snapshot (
                symbol TEXT PRIMARY KEY,
                name TEXT,
                price REAL,
                change_pct REAL,
                volume REAL,
                amount REAL,
                open REAL, high REAL, low REAL, prev_close REAL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS analysis_cache (
                symbol TEXT PRIMARY KEY,
                result TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS portfolio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                name TEXT DEFAULT '',
                shares REAL NOT NULL,
                cost REAL NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS stock_name_index (
                name TEXT PRIMARY KEY,
                symbol TEXT NOT NULL
            );
        """)


# ── Watchlist ──────────────────────────────────────────────

def watchlist_add(symbol: str, name: str = "", notes: str = "") -> bool:
    with _get_db() as conn:
        try:
            conn.execute(
                "INSERT OR REPLACE INTO watchlist (symbol, name, notes) VALUES (?, ?, ?)",
                (symbol, name, notes),
            )
            return True
        except Exception as e:
            logger.error("watchlist_add failed: %s", e)
            return False


def watchlist_remove(symbol: str) -> bool:
    with _get_db() as conn:
        conn.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol,))
        return conn.total_changes > 0


def watchlist_list() -> list[dict[str, Any]]:
    with _get_db() as conn:
        rows = conn.execute("SELECT * FROM watchlist ORDER BY added_at DESC").fetchall()
        return [dict(r) for r in rows]


def watchlist_exists(symbol: str) -> bool:
    with _get_db() as conn:
        row = conn.execute("SELECT 1 FROM watchlist WHERE symbol = ?", (symbol,)).fetchone()
        return row is not None


# ── Quote Cache ────────────────────────────────────────────

def save_quotes(quotes: list[dict[str, Any]]):
    """Upsert batch of real-time quotes."""
    with _get_db() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO quote_snapshot
               (symbol, name, price, change_pct, volume, amount, open, high, low, prev_close, updated_at)
               VALUES (:symbol, :name, :price, :change_pct, :volume, :amount, :open, :high, :low, :prev_close,
                       datetime('now','localtime'))""",
            quotes,
        )


def get_quote(symbol: str) -> dict[str, Any] | None:
    with _get_db() as conn:
        row = conn.execute(
            "SELECT * FROM quote_snapshot WHERE symbol = ?", (symbol,)
        ).fetchone()
        return dict(row) if row else None


# ── K-line Cache ───────────────────────────────────────────

def save_kline(symbol: str, records: list[dict[str, Any]]):
    """Bulk upsert K-line records."""
    with _get_db() as conn:
        for r in records:
            conn.execute(
                """INSERT OR REPLACE INTO kline_cache
                   (symbol, date, open, high, low, close, volume, amount)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (symbol, r.get("日期"), r.get("开盘"), r.get("最高"),
                 r.get("最低"), r.get("收盘"), r.get("成交量"), r.get("成交额")),
            )


def get_kline(symbol: str, limit: int = 500) -> list[dict[str, Any]]:
    with _get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM kline_cache WHERE symbol = ?
               ORDER BY date DESC LIMIT ?""",
            (symbol, limit),
        ).fetchall()
        return [dict(r) for r in rows]


# ── Analysis Cache ─────────────────────────────────────────

def save_analysis(symbol: str, result: dict[str, Any]):
    with _get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO analysis_cache (symbol, result, created_at) VALUES (?, ?, datetime('now','localtime'))",
            (symbol, json.dumps(result, ensure_ascii=False, default=str)),
        )


def get_cached_analysis(symbol: str) -> dict[str, Any] | None:
    with _get_db() as conn:
        row = conn.execute(
            "SELECT * FROM analysis_cache WHERE symbol = ?", (symbol,)
        ).fetchone()
        if row:
            return json.loads(row["result"])
        return None


# ── Portfolio / Positions ────────────────────────────────────

def portfolio_set(positions: list[dict[str, Any]]):
    """Replace all positions with a new list (clear + insert)."""
    with _get_db() as conn:
        conn.execute("DELETE FROM portfolio")
        for p in positions:
            conn.execute(
                "INSERT INTO portfolio (symbol, name, shares, cost) VALUES (?, ?, ?, ?)",
                (p.get("symbol", ""), p.get("name", ""), p.get("shares", 0), p.get("cost", 0)),
            )


def portfolio_get() -> list[dict[str, Any]]:
    """Return all stored positions."""
    with _get_db() as conn:
        rows = conn.execute("SELECT * FROM portfolio ORDER BY id").fetchall()
        return [dict(r) for r in rows]


def portfolio_clear():
    """Delete all positions."""
    with _get_db() as conn:
        conn.execute("DELETE FROM portfolio")


def get_cached_stock_by_name(name: str) -> dict[str, str] | None:
    """Look up symbol by stock name in cache."""
    with _get_db() as conn:
        row = conn.execute(
            "SELECT * FROM stock_name_index WHERE name = ?", (name,)
        ).fetchone()
        return {"name": row["name"], "symbol": row["symbol"]} if row else None


def cache_stock_name(name: str, symbol: str):
    with _get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO stock_name_index (name, symbol) VALUES (?, ?)",
            (name, symbol),
        )
