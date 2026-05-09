"""
Background data polling scheduler.

Only runs in HTTP mode — stdio mode doesn't support background threads
in the same way. The scheduler periodically fetches real-time quotes and
K-line data for watched stocks, caching everything in SQLite.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

import akshare as ak
import pandas as pd

from . import storage

logger = logging.getLogger("a-stock-mcp.scheduler")

# Global scheduler state
_watch_tasks: dict[str, asyncio.Task] = {}
_intervals: dict[str, int] = {}  # symbol -> interval in minutes
_scheduler_active = False


async def _poll_quote(symbol: str) -> dict[str, Any] | None:
    """Fetch a single real-time quote from Sina."""
    try:
        df = ak.stock_zh_a_spot()
        df["代码"] = df["代码"].str.upper()
        row = df[df["代码"] == symbol]
        if row.empty:
            return None
        r = row.iloc[0]
        return {
            "symbol": symbol,
            "name": r.get("名称", ""),
            "price": float(r.get("最新价", 0)),
            "change_pct": float(r.get("涨跌幅", 0)),
            "volume": float(r.get("成交量", 0)),
            "amount": float(r.get("成交额", 0)),
            "open": float(r.get("今开", 0)),
            "high": float(r.get("最高", 0)),
            "low": float(r.get("最低", 0)),
            "prev_close": float(r.get("昨收", 0)),
        }
    except Exception as e:
        logger.warning("poll_quote failed for %s: %s", symbol, e)
        return None


async def _poll_kline(symbol: str) -> list[dict[str, Any]] | None:
    """Fetch recent K-line data."""
    try:
        prefix = "sh" if symbol.startswith("SH") else "sz"
        raw_symbol = symbol.replace("SH", "").replace("SZ", "").replace("BJ", "")
        sina_symbol = f"{prefix}{raw_symbol}"
        df = ak.stock_zh_a_daily(symbol=sina_symbol, adjust="qfq")
        if df.empty:
            return None
        df = df.rename(columns={
            "date": "日期", "open": "开盘", "high": "最高",
            "low": "最低", "close": "收盘", "volume": "成交量",
            "amount": "成交额",
        })
        records = df.tail(200).to_dict("records")
        # Normalize date to string
        for r in records:
            r["日期"] = str(r["日期"])
        return records
    except Exception as e:
        logger.warning("poll_kline failed for %s: %s", symbol, e)
        return None


async def _poll_one(symbol: str):
    """Poll a single symbol: quote + kline."""
    logger.info("Polling %s ...", symbol)
    quote = await _poll_quote(symbol)
    if quote:
        storage.save_quotes([quote])
    kline = await _poll_kline(symbol)
    if kline:
        storage.save_kline(symbol, kline)
    logger.info("Polled %s: quote=%s, kline=%d records", symbol, "OK" if quote else "FAIL", len(kline or []))


async def _scheduler_loop():
    """Main scheduler loop — runs forever, checking each watched stock."""
    global _scheduler_active
    _scheduler_active = True
    logger.info("Scheduler started")
    try:
        while _scheduler_active:
            symbols = storage.watchlist_list()
            for item in symbols:
                sym = item["symbol"]
                interval = _intervals.get(sym, 30)
                # Check last poll time from quote_snapshot
                last = storage.get_quote(sym)
                if last:
                    last_time = datetime.strptime(last["updated_at"], "%Y-%m-%d %H:%M:%S")
                    elapsed = (datetime.now() - last_time).total_seconds() / 60
                    if elapsed < interval:
                        continue
                await _poll_one(sym)
            # Wait before next scan
            await asyncio.sleep(60)  # check every minute
    except asyncio.CancelledError:
        logger.info("Scheduler cancelled")
    finally:
        _scheduler_active = False


async def start_monitoring(symbol: str, interval_minutes: int = 30) -> str:
    """Add a symbol to the watchlist and begin polling."""
    normalized = symbol.strip().upper()
    storage.watchlist_add(normalized)
    _intervals[normalized] = max(5, interval_minutes)

    # Do an immediate poll
    await _poll_one(normalized)
    return f"已开始监控 {normalized}，每{_intervals[normalized]}分钟更新一次"


async def stop_monitoring(symbol: str) -> str:
    """Remove a symbol from the watchlist."""
    normalized = symbol.strip().upper()
    storage.watchlist_remove(normalized)
    _intervals.pop(normalized, None)
    return f"已停止监控 {normalized}"


async def get_monitoring_status() -> list[dict[str, Any]]:
    """Get status of all monitored stocks."""
    items = storage.watchlist_list()
    result = []
    for item in items:
        sym = item["symbol"]
        quote = storage.get_quote(sym)
        result.append({
            "symbol": sym,
            "name": item.get("name", ""),
            "interval_min": _intervals.get(sym, 30),
            "last_price": quote["price"] if quote else None,
            "last_update": quote["updated_at"] if quote else None,
        })
    return result
