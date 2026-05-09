"""
A 股 MCP Server - 基于 AKShare 的 A 股数据服务

为 AI 助手（如 Claude Code）提供 A 股实时行情、历史数据、技术分析、基本面查询等能力。
"""

import argparse
import asyncio
import logging
from datetime import datetime, date
from typing import Any

import akshare as ak
import pandas as pd

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource

from . import storage
from .analysis import run_analysis
from .portfolio import parse_portfolio, resolve_symbol
from .scheduler import start_monitoring, stop_monitoring, get_monitoring_status

logger = logging.getLogger("a-stock-mcp")


# ── 工具定义 ──────────────────────────────────────────────

TOOLS = [
    Tool(
        name="get_stock_list",
        description="获取A股股票列表（代码、名称、交易所）",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    Tool(
        name="get_realtime_quote",
        description="获取单只A股实时行情",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "股票代码，如 600519"},
            },
            "required": ["symbol"],
        },
    ),
    Tool(
        name="get_realtime_quotes",
        description="批量获取多只A股实时行情（最多50只）",
        inputSchema={
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "string",
                    "description": "股票代码，多个用逗号分隔，如 600519,000001,300750",
                },
            },
            "required": ["symbols"],
        },
    ),
    Tool(
        name="get_hist_kline",
        description="获取历史K线数据（日/周/月）",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "股票代码，如 600519"},
                "period": {
                    "type": "string",
                    "description": "K线周期：daily=日线, weekly=周线, monthly=月线",
                    "enum": ["daily", "weekly", "monthly"],
                },
                "start_date": {"type": "string", "description": "开始日期 YYYYMMDD，默认1年前"},
                "end_date": {"type": "string", "description": "结束日期 YYYYMMDD，默认今天"},
                "adjust": {
                    "type": "string",
                    "description": "复权类型：qfq=前复权, hfq=后复权, ''=不复权",
                    "enum": ["qfq", "hfq", ""],
                },
            },
            "required": ["symbol"],
        },
    ),
    Tool(
        name="get_intraday",
        description="获取当日分时数据（5分钟频次）",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "股票代码，如 600519"},
            },
            "required": ["symbol"],
        },
    ),
    Tool(
        name="get_financial_indicators",
        description="获取财务指标（ROE/毛利率/净利率等）",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "股票代码，如 600519"},
            },
            "required": ["symbol"],
        },
    ),
    Tool(
        name="get_balance_sheet",
        description="获取资产负债表",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "股票代码，如 600519"},
            },
            "required": ["symbol"],
        },
    ),
    Tool(
        name="get_income_statement",
        description="获取利润表",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "股票代码，如 600519"},
            },
            "required": ["symbol"],
        },
    ),
    Tool(
        name="get_dragon_tiger",
        description="获取龙虎榜数据",
        inputSchema={
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "日期 YYYYMMDD，默认最近交易日"},
            },
        },
    ),
    Tool(
        name="get_north_flow",
        description="获取北向资金流向数据",
        inputSchema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "开始日期 YYYYMMDD"},
                "end_date": {"type": "string", "description": "结束日期 YYYYMMDD"},
            },
        },
    ),
    Tool(
        name="get_margin_detail",
        description="获取融资融券明细数据",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "股票代码，如 600519"},
                "date": {"type": "string", "description": "日期 YYYYMMDD，默认最近交易日"},
            },
            "required": ["symbol"],
        },
    ),
    Tool(
        name="get_technical_indicators",
        description="计算技术指标（MACD/RSI/KDJ/BOLL等）",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "股票代码，如 600519"},
                "indicators": {
                    "type": "string",
                    "description": "指标列表，逗号分隔。可选: MACD,RSI,KDJ,BOLL,MA",
                },
                "period": {
                    "type": "string",
                    "description": "K线周期：daily=日线, weekly=周线, monthly=月线",
                },
            },
            "required": ["symbol"],
        },
    ),
    Tool(
        name="get_stock_info",
        description="获取股票基本信息（行业、市值、PE等）",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "股票代码，如 600519"},
            },
            "required": ["symbol"],
        },
    ),
    Tool(
        name="analyze_stock",
        description="综合技术分析：多指标加权评分（MACD/RSI/KDJ/BOLL/MA/OBV等），返回-100到+100的综合评分及信号明细",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "股票代码，如 600519"},
            },
            "required": ["symbol"],
        },
    ),
    Tool(
        name="start_monitoring",
        description="开始持续监控一只股票，定时获取最新行情并缓存到本地数据库",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "股票代码，如 600519"},
                "interval_minutes": {
                    "type": "number",
                    "description": "更新间隔（分钟），默认30，最小5",
                },
            },
            "required": ["symbol"],
        },
    ),
    Tool(
        name="stop_monitoring",
        description="停止监控一只股票",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "股票代码，如 600519"},
            },
            "required": ["symbol"],
        },
    ),
    Tool(
        name="monitoring_status",
        description="查看当前正在监控的所有股票及状态",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    Tool(
        name="set_portfolio",
        description="设置/更新持仓信息。接受自然语言或结构化文本，例如：茅台100股成本1500，宁德200股成本420，或 JSON 数组",
        inputSchema={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "持仓描述文本或 JSON",
                },
            },
            "required": ["text"],
        },
    ),
    Tool(
        name="portfolio_analysis",
        description="分析当前持仓所有股票，返回综合评分、盈亏、技术信号",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
]


# ── 工具实现 ──────────────────────────────────────────────


def df_to_text(df: pd.DataFrame, max_rows: int = 100) -> str:
    """DataFrame 转可读文本"""
    if df is None or df.empty:
        return "暂无数据"
    return df.head(max_rows).to_string(index=False)


def _get_all_spots() -> pd.DataFrame:
    """获取全量实时行情，使用新浪源（国内网络友好）"""
    df = ak.stock_zh_a_spot()
    # Sina 返回小写代码如 sh600519，统一转大写以便匹配
    if "代码" in df.columns:
        df["代码"] = df["代码"].str.upper()
    cols = ["代码", "名称", "最新价", "涨跌幅", "涨跌额", "成交量", "成交额", "今开", "昨收", "最高", "最低"]
    return df[cols] if all(c in df.columns for c in cols) else df


def _normalize_symbol(symbol: str) -> str:
    """补齐股票代码前缀，统一转大写"""
    s = symbol.strip().upper()
    if s.startswith("SH") or s.startswith("SZ") or s.startswith("BJ"):
        return s
    if s.startswith("6"):
        return f"SH{s}"
    if s.startswith("0") or s.startswith("3"):
        return f"SZ{s}"
    if s.startswith("4") or s.startswith("8"):
        return f"BJ{s}"
    return s


async def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
    try:
        if name == "get_stock_list":
            df = _get_all_spots()
            return [TextContent(type="text", text=df_to_text(df.head(200)))]

        elif name == "get_realtime_quote":
            symbol = _normalize_symbol(arguments["symbol"])
            df = _get_all_spots()
            row = df[df["代码"] == symbol]
            if row.empty:
                return [TextContent(type="text", text=f"未找到股票 {arguments['symbol']}")]
            return [TextContent(type="text", text=df_to_text(row))]

        elif name == "get_realtime_quotes":
            symbols_str = arguments["symbols"]
            symbols = [_normalize_symbol(s) for s in symbols_str.split(",")]
            df = _get_all_spots()
            mask = df["代码"].isin(symbols)
            result = df[mask]
            return [TextContent(type="text", text=df_to_text(result))]

        elif name == "get_hist_kline":
            symbol = arguments["symbol"]
            period = arguments.get("period", "daily")
            adjust = arguments.get("adjust", "")
            start = arguments.get("start_date", "")
            end = arguments.get("end_date", "")

            # 使用 Sina 源（国内网络友好），symbol 需带 sh/sz 前缀
            prefix = "sh" if symbol.startswith("6") else "sz"
            sina_symbol = f"{prefix}{symbol[-6:]}"
            df = ak.stock_zh_a_daily(symbol=sina_symbol, adjust=adjust or "qfq")
            if not df.empty:
                df = df.rename(columns={
                    "date": "日期", "open": "开盘", "high": "最高",
                    "low": "最低", "close": "收盘", "volume": "成交量",
                    "amount": "成交额",
                })
                if start:
                    df = df[df["日期"].astype(str) >= start]
                if end:
                    df = df[df["日期"].astype(str) <= end]
            return [TextContent(type="text", text=df_to_text(df))]

        elif name == "get_intraday":
            symbol = arguments["symbol"]
            df = ak.stock_zh_a_tick_tx(symbol, trade_date="")
            return [TextContent(type="text", text=df_to_text(df))]

        elif name == "get_financial_indicators":
            symbol = arguments["symbol"]
            df = ak.stock_financial_abstract_ths(symbol)
            return [TextContent(type="text", text=df_to_text(df))]

        elif name == "get_balance_sheet":
            symbol = arguments["symbol"]
            df = ak.stock_financial_balance_sheet_by_yearly_em(symbol)
            return [TextContent(type="text", text=df_to_text(df))]

        elif name == "get_income_statement":
            symbol = arguments["symbol"]
            df = ak.stock_financial_profit_by_yearly_em(symbol)
            return [TextContent(type="text", text=df_to_text(df))]

        elif name == "get_dragon_tiger":
            date_str = arguments.get("date", "")
            try:
                df = ak.stock_lhb_detail_em() if date_str else ak.stock_lhb_detail_em()
                if not df.empty and date_str:
                    df = df[df["日期"].astype(str) == date_str]
                return [TextContent(type="text", text=df_to_text(df))]
            except Exception:
                # Fallback to block trade data
                df = ak.stock_dzjy_mrmx()
                return [TextContent(type="text", text=df_to_text(df) + "\n\n注：龙虎榜数据暂不可用，已展示大宗交易数据作为替代")]

        elif name == "get_north_flow":
            start = arguments.get("start_date", "")
            end = arguments.get("end_date", "")
            df = ak.stock_hsgt_hist_em(symbol="北上")
            return [TextContent(type="text", text=df_to_text(df))]

        elif name == "get_margin_detail":
            symbol = arguments["symbol"]
            date_str = arguments.get("date", "")
            df = ak.stock_margin_detail_szse(date_str) if symbol.startswith("0") else ak.stock_margin_detail_sse(date_str)
            return [TextContent(type="text", text=df_to_text(df))]

        elif name == "get_technical_indicators":
            symbol = arguments["symbol"]
            indicators = arguments.get("indicators", "MACD,RSI,KDJ,BOLL")
            period = arguments.get("period", "daily")

            prefix = "sh" if symbol.startswith("6") else "sz"
            sina_symbol = f"{prefix}{symbol[-6:]}"
            df = ak.stock_zh_a_daily(symbol=sina_symbol, adjust="qfq")
            if not df.empty:
                df = df.rename(columns={
                    "date": "日期", "open": "开盘", "high": "最高",
                    "low": "最低", "close": "收盘", "volume": "成交量",
                    "amount": "成交额",
                })
            if df.empty:
                return [TextContent(type="text", text=f"未获取到 {symbol} 的K线数据")]

            # 计算技术指标
            want = [s.upper().strip() for s in indicators.split(",")]
            close = df["收盘"].values.astype(float)
            high = df["最高"].values.astype(float)
            low = df["最低"].values.astype(float)
            volume = df["成交量"].values.astype(float)

            result_df = df[["日期", "开盘", "收盘", "最高", "最低", "成交量"]].copy()

            if "MA" in want:
                for n in [5, 10, 20, 60]:
                    if len(close) >= n:
                        result_df[f"MA{n}"] = pd.Series(close).rolling(n).mean().round(2)

            if "MACD" in want and len(close) >= 26:
                ema12 = pd.Series(close).ewm(span=12).mean()
                ema26 = pd.Series(close).ewm(span=26).mean()
                dif = ema12 - ema26
                dea = dif.ewm(span=9).mean()
                macd = 2 * (dif - dea)
                result_df["DIF"] = dif.round(2)
                result_df["DEA"] = dea.round(2)
                result_df["MACD"] = macd.round(2)

            if "RSI" in want and len(close) >= 14:
                delta = pd.Series(close).diff()
                gain = delta.clip(lower=0).rolling(14).mean()
                loss = (-delta.clip(upper=0)).rolling(14).mean()
                rs = gain / loss.replace(0, float("nan"))
                result_df["RSI"] = (100 - (100 / (1 + rs))).round(2)

            if "KDJ" in want and len(close) >= 9:
                low9 = pd.Series(low).rolling(9).min()
                high9 = pd.Series(high).rolling(9).max()
                rsv = ((pd.Series(close) - low9) / (high9 - low9).replace(0, float("nan"))) * 100
                k = rsv.ewm(com=2).mean()
                d = k.ewm(com=2).mean()
                j = 3 * k - 2 * d
                result_df["K"] = k.round(2)
                result_df["D"] = d.round(2)
                result_df["J"] = j.round(2)

            if "BOLL" in want and len(close) >= 20:
                mid = pd.Series(close).rolling(20).mean()
                std = pd.Series(close).rolling(20).std()
                result_df["BOLL_MID"] = mid.round(2)
                result_df["BOLL_UP"] = (mid + 2 * std).round(2)
                result_df["BOLL_DN"] = (mid - 2 * std).round(2)

            return [TextContent(type="text", text=df_to_text(result_df))]

        elif name == "get_stock_info":
            symbol = arguments["symbol"]
            # 先用新浪实时行情获取基础信息（更稳定）
            prefix = "sh" if symbol.startswith("6") else "sz"
            sina_symbol = f"{prefix}{symbol[-6:]}"
            spot = ak.stock_zh_a_spot()
            spot["代码"] = spot["代码"].str.upper()
            row = spot[spot["代码"] == _normalize_symbol(symbol)]
            if not row.empty:
                return [TextContent(type="text", text=df_to_text(row.T.reset_index().rename(columns={"index": "项目", 0: "值"})))]
            # 回退到东财
            df = ak.stock_individual_info_em(symbol)
            return [TextContent(type="text", text=df_to_text(df))]

        elif name == "analyze_stock":
            symbol = arguments["symbol"]
            norm = _normalize_symbol(symbol)
            raw_code = norm.replace("SH", "").replace("SZ", "").replace("BJ", "")

            # 1) Get current price from spot
            spot = _get_all_spots()
            row = spot[spot["代码"] == norm]
            if row.empty:
                return [TextContent(type="text", text=f"未找到股票 {symbol}")]
            s = row.iloc[0]
            price = float(s.get("最新价", 0))

            # 2) Get K-line for indicators
            prefix = "sh" if raw_code.startswith("6") else "sz"
            sina_symbol = f"{prefix}{raw_code}"
            df = ak.stock_zh_a_daily(symbol=sina_symbol, adjust="qfq")
            if not df.empty:
                df = df.rename(columns={
                    "date": "日期", "open": "开盘", "high": "最高",
                    "low": "最低", "close": "收盘", "volume": "成交量",
                    "amount": "成交额",
                })
            if df.empty:
                return [TextContent(type="text", text=f"未获取到 {symbol} 的K线数据")]

            closes = df["收盘"].values.astype(float).tolist()
            highs = df["最高"].values.astype(float).tolist()
            lows = df["最低"].values.astype(float).tolist()
            volumes = df["成交量"].values.astype(float).tolist()

            # 3) Get PE ratio — try multiple sources
            pe_ratio = None
            high_52w = None
            low_52w = None
            # 52-week from K-line
            try:
                recent = df.tail(250)
                if not recent.empty:
                    high_52w = float(recent["最高"].max())
                    low_52w = float(recent["最低"].min())
            except Exception:
                pass
            # PE from financial analysis indicator — calculate from EPS
            try:
                fin_df = ak.stock_financial_analysis_indicator(symbol, start_year="2024")
                if not fin_df.empty:
                    for col in fin_df.columns:
                        col_str = str(col)
                        if "每股" in col_str and ("收益" in col_str or "益" in col_str):
                            eps = float(fin_df.iloc[-1][col])
                            if eps and eps > 0 and price and price > 0:
                                pe_ratio = round(price / eps, 2)
                            break
            except Exception:
                pass
            # Fallback: East Money individual info
            if pe_ratio is None:
                try:
                    info_df = ak.stock_individual_info_em(symbol)
                    if not info_df.empty:
                        pe_row = info_df[info_df["item"] == "市盈率-动态"]
                        if not pe_row.empty:
                            pe_ratio = float(pe_row.iloc[0]["value"])
                except Exception:
                    pass

            # 4) Run analysis
            result = run_analysis(
                symbol=symbol,
                price=price,
                closes=closes,
                highs=highs,
                lows=lows,
                volumes=volumes,
                pe_ratio=pe_ratio,
                high_52w=high_52w,
                low_52w=low_52w,
            )

            # Cache
            try:
                storage.save_analysis(symbol, result)
            except Exception:
                pass

            # Format output
            lines = [
                f"═══ {symbol} 技术分析报告 ═══",
                f"当前价格: {price:.2f}",
                f"综合评分: {result['score']}/100",
                f" verdict: {result['verdict']}",
                f"看多信号: {result['bullish_count']} | 看空信号: {result['bearish_count']}",
                "",
                "--- 指标详情 ---",
                f"RSI(14): {result.get('rsi', 'N/A')}",
                f"MACD: {result.get('macd', 'N/A')} | Signal: {result.get('macd_signal', 'N/A')}",
                f"SMA20: {result.get('sma_20', 'N/A')} | SMA50: {result.get('sma_50', 'N/A')} | SMA200: {result.get('sma_200', 'N/A')}",
                f"PE: {pe_ratio or 'N/A'}",
                "",
                "--- 信号明细 ---",
            ]
            for sig in result["signals"]:
                icon = {"bullish": "▲", "bearish": "▼", "neutral": "◆"}.get(sig["type"], "?")
                lines.append(f"  {icon} [{sig['type']}] {sig['name']} (权重:{sig['weight']:+d})")
                lines.append(f"     {sig['detail']}")
            lines.append("")
            lines.append(result["summary"])

            return [TextContent(type="text", text="\n".join(lines))]

        elif name == "start_monitoring":
            symbol = arguments["symbol"]
            interval = int(arguments.get("interval_minutes", 30))
            msg = await start_monitoring(symbol, interval)
            return [TextContent(type="text", text=msg)]

        elif name == "stop_monitoring":
            symbol = arguments["symbol"]
            msg = await stop_monitoring(symbol)
            return [TextContent(type="text", text=msg)]

        elif name == "monitoring_status":
            items = await get_monitoring_status()
            if not items:
                return [TextContent(type="text", text="当前没有正在监控的股票")]
            lines = ["═══ 监控状态 ═══"]
            for i in items:
                last = i.get("last_price", "N/A")
                updated = i.get("last_update", "N/A")
                lines.append(f"  {i['symbol']} ({i.get('name', '')})")
                lines.append(f"    间隔: {i['interval_min']}分钟 | 最新价: {last} | 更新: {updated}")
            return [TextContent(type="text", text="\n".join(lines))]

        elif name == "set_portfolio":
            text = arguments["text"]
            positions = parse_portfolio(text)
            if not positions:
                return [TextContent(type="text", text="未能解析持仓信息，请提供格式如：600519 100 1500 或 茅台100股成本1500")]
            # Resolve names to symbols
            for p in positions:
                resolve_symbol(p)
            storage.portfolio_set(positions)
            lines = [
                f"持仓已保存 ({len(positions)} 只)：",
            ]
            for p in positions:
                sym = p.get("symbol", "?")
                name = p.get("name", "")
                lines.append(f"  {sym} {name} | {p['shares']:.0f}股 | 成本 {p['cost']:.2f}")
            lines.append("")
            lines.append("可用 portfolio_analysis 分析持仓")
            return [TextContent(type="text", text="\n".join(lines))]

        elif name == "portfolio_analysis":
            positions = storage.portfolio_get()
            if not positions:
                return [TextContent(type="text", text="暂无持仓数据。请先用 set_portfolio 输入你的持仓。")]
            spot = _get_all_spots()

            lines = ["═══ 持仓分析报告 ═══", ""]
            total_cost = 0.0
            total_value = 0.0
            overall_score = 0.0

            for i, pos in enumerate(positions, 1):
                sym = pos["symbol"].strip().upper()
                name = pos.get("name", "")
                shares = pos["shares"]
                cost = pos["cost"]
                item_cost = cost * shares
                total_cost += item_cost

                lines.append(f"── {i}. {sym} {name} ──")
                lines.append(f"   持仓: {shares:.0f}股 | 成本价: {cost:.2f}")

                # Get realtime price from spot
                row = spot[spot["代码"] == sym]
                if row.empty:
                    lines.append("   ⚠ 未找到实时数据")
                    lines.append("")
                    continue
                s = row.iloc[0]
                price = float(s.get("最新价", 0))
                change_pct = float(s.get("涨跌幅", 0))
                item_value = price * shares
                total_value += item_value
                profit = item_value - item_cost
                profit_pct = (price / cost - 1) * 100

                lines.append(f"   现价: {price:.2f} ({change_pct:+.2f}%)")
                pct_icon = "▲" if profit >= 0 else "▼"
                lines.append(f"   盈亏: {pct_icon} {profit:+.2f} ({profit_pct:+.2f}%)")

                # Run analysis
                try:
                    raw_code = sym.replace("SH", "").replace("SZ", "").replace("BJ", "")
                    prefix = "sh" if raw_code.startswith("6") else "sz"
                    df = ak.stock_zh_a_daily(symbol=f"{prefix}{raw_code}", adjust="qfq")
                    if not df.empty:
                        df = df.rename(columns={
                            "date": "日期", "open": "开盘", "high": "最高",
                            "low": "最低", "close": "收盘", "volume": "成交量",
                            "amount": "成交额",
                        })
                        closes = df["收盘"].values.astype(float).tolist()
                        highs = df["最高"].values.astype(float).tolist()
                        lows = df["最低"].values.astype(float).tolist()
                        volumes = df["成交量"].values.astype(float).tolist()
                        ra = run_analysis(sym, price, closes, highs, lows, volumes)
                        overall_score += ra["score"]
                        lines.append(f"   技术评分: {ra['score']}/100 ({ra['verdict']})")
                        lines.append(f"   看多/看空: {ra['bullish_count']}/{ra['bearish_count']}")
                        lines.append(f"   RSI: {ra.get('rsi', 'N/A')} | MACD: {ra.get('macd', 'N/A')}")
                    else:
                        lines.append("   技术分析: 数据不足")
                except Exception as e:
                    lines.append(f"   技术分析失败: {e}")
                lines.append("")

            # Summary
            portfolio_profit = total_value - total_cost
            portfolio_pct = (total_value / total_cost - 1) * 100 if total_cost else 0
            avg_score = overall_score / len(positions) if positions else 0

            lines.append("═══ 组合总览 ═══")
            lines.append(f"总市值: {total_value:,.2f}")
            lines.append(f"总成本: {total_cost:,.2f}")
            profit_icon = "▲" if portfolio_profit >= 0 else "▼"
            lines.append(f"总盈亏: {profit_icon} {portfolio_profit:+,.2f} ({portfolio_pct:+.2f}%)")
            q_icon = "🟢" if avg_score >= 10 else ("🔴" if avg_score <= -10 else "🟡")
            lines.append(f"平均技术评分: {avg_score:.1f}/100 {q_icon}")

            return [TextContent(type="text", text="\n".join(lines))]

        else:
            return [TextContent(type="text", text=f"未知工具: {name}")]

    except ConnectionError as e:
        return [TextContent(type="text", text=f"网络连接失败，请检查网络: {e!s}")]
    except Exception as e:
        logger.error(f"调用 {name} 失败: {e}", exc_info=True)
        return [TextContent(type="text", text=f"错误: {e!s}")]


# ── 服务入口 ──────────────────────────────────────────────


async def serve_http(host: str, port: int):
    """启动 HTTP 模式"""
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.middleware import Middleware

    storage.init_db()
    logger.info("数据库已初始化")

    server = Server("a-stock-mcp")
    server.tools = TOOLS

    sse = SseServerTransport("/messages")

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Route("/messages", endpoint=sse.handle_post_message, methods=["POST"]),
        ],
    )

    import uvicorn
    logger.info(f"HTTP MCP server listening on {host}:{port}")
    await uvicorn.run(app, host=host, port=port, log_level="info")


async def serve_stdio():
    """启动 stdio 模式（供 Claude Code 等 MCP 客户端使用）"""
    storage.init_db()
    logger.info("数据库已初始化")
    server = Server("a-stock-mcp")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
        return await handle_call_tool(name, arguments or {})

    async with stdio_server() as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())


def main():
    parser = argparse.ArgumentParser(description="A 股 MCP Server")
    parser.add_argument("--http", action="store_true", help="启用 HTTP 模式（默认 stdio）")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP 监听地址")
    parser.add_argument("--port", type=int, default=8080, help="HTTP 监听端口")

    args = parser.parse_known_args()[0]

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if args.http:
        asyncio.run(serve_http(args.host, args.port))
    else:
        asyncio.run(serve_stdio())


if __name__ == "__main__":
    main()
