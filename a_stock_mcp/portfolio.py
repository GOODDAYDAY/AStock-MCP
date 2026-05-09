"""Portfolio (positions) management."""

import json
import re
import logging
from typing import Any

from . import storage

logger = logging.getLogger("a-stock-mcp.portfolio")


def parse_portfolio(text: str) -> list[dict[str, Any]]:
    """Parse free-form text into a list of positions.

    Supports:
      - JSON array: [{"symbol":"600519","shares":100,"cost":1500}]
      - Line-by-line:  600519 100 15.00  or  贵州茅台 100 15.00
      - Natural: 茅台100股成本1500，宁德200股成本420
    """
    text = text.strip()
    # Try JSON first
    if text.startswith("["):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    positions = []
    lines = re.split(r"[，,;；\n]+", text)
    for line in lines:
        line = line.strip()
        if not line:
            continue
        pos = _parse_line(line)
        if pos:
            positions.append(pos)
    return positions


def _parse_line(line: str) -> dict[str, Any] | None:
    """Parse a single position line."""
    # Pattern 1: code shares cost  (600519 100 1500)
    m = re.match(
        r"(?P<code>(?:SH|SZ|BJ)?\d{6})\s+(?P<shares>\d+\.?\d*)\s+(?P<cost>\d+\.?\d*)",
        line,
    )
    if m:
        return {
            "symbol": m.group("code"),
            "shares": float(m.group("shares")),
            "cost": float(m.group("cost")),
        }

    # Pattern 2: natural: "茅台100股成本1500" or "茅台 100 股 成本 1500"
    m = re.match(
        r".*?(?P<name>[一-鿿]+?)\s*(?P<shares>\d+\.?\d*)\s*股.*?(?:成本|均价|买入价)[约]?\s*(?P<cost>\d+\.?\d*)",
        line,
    )
    if m:
        return {
            "name": m.group("name"),
            "shares": float(m.group("shares")),
            "cost": float(m.group("cost")),
        }

    return None


def resolve_symbol(pos: dict) -> dict:
    """Resolve a position's symbol if only name is given, via cached stock list."""
    if "symbol" in pos and pos["symbol"]:
        return pos
    name = pos.get("name", "")
    if not name:
        return pos
    # Look up in DB
    cached = storage.get_cached_stock_by_name(name)
    if cached:
        pos["symbol"] = cached["symbol"]
        pos["name"] = cached["name"]
    else:
        # Fallback: try to fetch from spot list (may be slow)
        try:
            import akshare as ak

            df = ak.stock_zh_a_spot()
            df["名称"] = df["名称"].str.strip()
            row = df[df["名称"] == name]
            if not row.empty:
                code = str(row.iloc[0]["代码"]).strip().upper()
                pos["symbol"] = code
                pos["name"] = name
                # Cache it for next time
                storage.cache_stock_name(name, code)
        except Exception as e:
            logger.warning("resolve_symbol(%s) failed: %s", name, e)
    return pos
