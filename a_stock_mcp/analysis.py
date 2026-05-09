"""
Quantitative analysis engine — ported from ai-project multi-agent system.

Computes weighted signals from multiple technical indicators and returns
a composite score from -100 (strong sell) to +100 (strong buy).

Signal categories:
  - MA system: golden/death cross, price vs MA200
  - RSI: oversold/overbought zones
  - MACD: crossover direction
  - Bollinger Bands: band break, squeeze
  - ATR: volatility assessment
  - Stochastic: overbought/oversold
  - OBV: volume divergence
  - 52-week range position
"""

import logging
import math

logger = logging.getLogger("a-stock-mcp.analysis")


def compute_ma_signals(price: float, sma_20: float | None, sma_50: float | None, sma_200: float | None) -> list[dict]:
    signals = []
    if sma_20 and sma_50:
        if sma_20 > sma_50:
            signals.append({"name": "金叉 Golden Cross", "type": "bullish", "detail": f"SMA20({sma_20:.2f}) > SMA50({sma_50:.2f})", "weight": 15})
        else:
            signals.append({"name": "死叉 Death Cross", "type": "bearish", "detail": f"SMA20({sma_20:.2f}) < SMA50({sma_50:.2f})", "weight": -15})
    if sma_200 and price:
        if price > sma_200:
            signals.append({"name": "站上MA200", "type": "bullish", "detail": f"股价({price:.2f})在长期均线上方", "weight": 10})
        else:
            pct = (sma_200 - price) / sma_200 * 100
            signals.append({"name": "跌破MA200", "type": "bearish", "detail": f"股价低于长期均线{pct:.1f}%", "weight": -10})
    if sma_20 and price:
        if price > sma_20:
            signals.append({"name": "短期趋势向上", "type": "bullish", "detail": "Price > SMA20", "weight": 5})
        else:
            signals.append({"name": "短期趋势向下", "type": "bearish", "detail": "Price < SMA20", "weight": -5})
    return signals


def compute_rsi_signals(rsi: float | None) -> list[dict]:
    if rsi is None:
        return []
    if rsi > 80:
        return [{"name": "RSI极度超买", "type": "bearish", "detail": f"RSI={rsi:.1f}，强烈卖出信号", "weight": -20}]
    if rsi > 70:
        return [{"name": "RSI超买", "type": "bearish", "detail": f"RSI={rsi:.1f}，警戒区", "weight": -10}]
    if rsi < 20:
        return [{"name": "RSI极度超卖", "type": "bullish", "detail": f"RSI={rsi:.1f}，强烈买入信号", "weight": 20}]
    if rsi < 30:
        return [{"name": "RSI超卖", "type": "bullish", "detail": f"RSI={rsi:.1f}，可能反弹", "weight": 10}]
    if 45 <= rsi <= 55:
        return [{"name": "RSI中性", "type": "neutral", "detail": f"RSI={rsi:.1f}，无信号", "weight": 0}]
    if rsi > 55:
        return [{"name": "RSI多头动能", "type": "bullish", "detail": f"RSI={rsi:.1f}，正向动能", "weight": 5}]
    return [{"name": "RSI空头动能", "type": "bearish", "detail": f"RSI={rsi:.1f}，负向动能", "weight": -5}]


def compute_macd_signals(macd: float | None, macd_signal: float | None) -> list[dict]:
    if macd is None or macd_signal is None:
        return []
    if macd > macd_signal > 0:
        return [{"name": "MACD强势多头", "type": "bullish", "detail": f"MACD({macd:.4f})在信号线上方且为正", "weight": 15}]
    if macd > macd_signal:
        return [{"name": "MACD金叉", "type": "bullish", "detail": f"MACD上穿信号线, diff={macd - macd_signal:.4f}", "weight": 8}]
    if macd < macd_signal < 0:
        return [{"name": "MACD强势空头", "type": "bearish", "detail": f"MACD({macd:.4f})在信号线下方且为负", "weight": -15}]
    return [{"name": "MACD死叉", "type": "bearish", "detail": f"MACD下穿信号线, diff={macd - macd_signal:.4f}", "weight": -8}]


def compute_bollinger_signals(close: float, closes: list[float], period: int = 20, num_std: float = 2.0) -> list[dict]:
    if len(closes) < period:
        return []
    window = closes[-period:]
    mean = sum(window) / period
    variance = sum((x - mean) ** 2 for x in window) / period
    std = variance ** 0.5
    upper = mean + num_std * std
    lower = mean - num_std * std
    width = (upper - lower) / mean * 100 if mean else 0

    signals = []
    if close >= upper:
        signals.append({"name": "布林上轨突破", "type": "bearish", "detail": f"股价{close:.2f}突破上轨{upper:.2f}，均值回归风险", "weight": -8})
    elif close <= lower:
        signals.append({"name": "布林下轨突破", "type": "bullish", "detail": f"股价{close:.2f}跌破下轨{lower:.2f}，超卖", "weight": 8})
    else:
        band_range = upper - lower
        if band_range > 0:
            pct = (close - lower) / band_range * 100
            if pct >= 80:
                signals.append({"name": "布林上轨区", "type": "bearish", "detail": f"股价在布林带{pct:.0f}%位置", "weight": -3})
            elif pct <= 20:
                signals.append({"name": "布林下轨区", "type": "bullish", "detail": f"股价在布林带{pct:.0f}%位置", "weight": 3})
    if 0 < width < 5:
        signals.append({"name": "布林收缩", "type": "neutral", "detail": f"带宽{width:.1f}%，低波动，变盘在即", "weight": 0})
    return signals


def compute_atr_signals(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[dict]:
    if len(closes) < period + 1:
        return []
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    atr = sum(trs[-period:]) / period
    atr_pct = atr / closes[-1] * 100 if closes[-1] else 0
    if atr_pct >= 5:
        return [{"name": "高波动(ATR)", "type": "bearish", "detail": f"ATR={atr_pct:.2f}%估值，风险偏高", "weight": -5}]
    if atr_pct <= 1:
        return [{"name": "低波动(ATR)", "type": "neutral", "detail": f"ATR={atr_pct:.2f}%估值，波动压缩", "weight": 0}]
    return [{"name": "正常波动(ATR)", "type": "neutral", "detail": f"ATR={atr_pct:.2f}%估值", "weight": 0}]


def compute_stochastic_signals(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[dict]:
    if len(closes) < period:
        return []
    window_high = max(highs[-period:])
    window_low = min(lows[-period:])
    close = closes[-1]
    if window_high == window_low:
        return []
    k = (close - window_low) / (window_high - window_low) * 100
    if k >= 80:
        return [{"name": "随机指标超买", "type": "bearish", "detail": f"%K={k:.1f}(>80)", "weight": -8}]
    if k <= 20:
        return [{"name": "随机指标超卖", "type": "bullish", "detail": f"%K={k:.1f}(<20)", "weight": 8}]
    return []


def compute_obv_signals(closes: list[float], volumes: list[float]) -> list[dict]:
    if len(closes) < 21 or len(volumes) < 21:
        return []
    obv = [0.0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            obv.append(obv[-1] + volumes[i])
        elif closes[i] < closes[i - 1]:
            obv.append(obv[-1] - volumes[i])
        else:
            obv.append(obv[-1])
    recent = obv[-10:]
    slope = recent[-1] - recent[0]
    baseline = max(abs(obv[-11]), 1)
    pct_change = slope / baseline * 100
    price_change_pct = (closes[-1] / closes[-11] - 1) * 100 if closes[-11] else 0

    if pct_change > 5 and price_change_pct > 0:
        return [{"name": "OBV确认上涨", "type": "bullish", "detail": f"OBV上升+股价涨{price_change_pct:.1f}%，资金流入", "weight": 8}]
    if pct_change < -5 and price_change_pct < 0:
        return [{"name": "OBV确认下跌", "type": "bearish", "detail": f"OBV下降+股价跌{price_change_pct:.1f}%，资金流出", "weight": -8}]
    if pct_change > 5 > price_change_pct:
        return [{"name": "OBV底背离", "type": "bullish", "detail": "OBV上升而股价下跌，潜伏吸筹", "weight": 10}]
    if pct_change < -5 < price_change_pct:
        return [{"name": "OBV顶背离", "type": "bearish", "detail": "OBV下降而股价上涨，隐蔽出货", "weight": -10}]
    return []


def compute_range_signals(price: float, high_52w: float | None, low_52w: float | None) -> list[dict]:
    if not (high_52w and low_52w and price):
        return []
    signals = []
    range_52w = high_52w - low_52w
    if range_52w <= 0:
        return []
    position = (price - low_52w) / range_52w * 100
    if position > 90:
        signals.append({"name": "近52周高点", "type": "bearish", "detail": f"股价在52周区间{position:.0f}%位置，上行空间有限", "weight": -10})
    elif position > 70:
        signals.append({"name": "52周中上区", "type": "bullish", "detail": f"股价在52周区间{position:.0f}%位置，动能强劲", "weight": 5})
    elif position < 20:
        signals.append({"name": "近52周低点", "type": "bullish", "detail": f"股价在52周区间{position:.0f}%位置，潜在价值", "weight": 10})
    elif position < 40:
        signals.append({"name": "52周中下区", "type": "bearish", "detail": f"股价在52周区间{position:.0f}%位置", "weight": -5})
    else:
        signals.append({"name": "52周中位区", "type": "neutral", "detail": f"股价在52周区间{position:.0f}%位置", "weight": 0})
    drawdown = (high_52w - price) / high_52w * 100
    if drawdown > 30:
        signals.append({"name": "深度回撤", "type": "bearish", "detail": f"距52周高点回撤{drawdown:.1f}%", "weight": -10})
    elif drawdown > 15:
        signals.append({"name": "中度回撤", "type": "bearish", "detail": f"距52周高点回撤{drawdown:.1f}%", "weight": -5})
    return signals


def compute_pe_signals(pe: float | None) -> list[dict]:
    if pe is None:
        return []
    if pe < 0:
        return [{"name": "PE为负", "type": "bearish", "detail": "公司亏损", "weight": -10}]
    if pe > 100:
        return [{"name": "PE极高", "type": "bearish", "detail": f"PE={pe:.1f}，极度高估", "weight": -10}]
    if pe > 40:
        return [{"name": "PE偏高", "type": "bearish", "detail": f"PE={pe:.1f}，需要成长溢价支撑", "weight": -5}]
    if pe < 10:
        return [{"name": "PE偏低", "type": "bullish", "detail": f"PE={pe:.1f}，潜在价值股", "weight": 10}]
    if pe < 20:
        return [{"name": "PE适中", "type": "bullish", "detail": f"PE={pe:.1f}，估值合理", "weight": 5}]
    return []


def run_analysis(
    symbol: str,
    price: float | None,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    volumes: list[float],
    pe_ratio: float | None = None,
    high_52w: float | None = None,
    low_52w: float | None = None,
) -> dict:
    """Run full quant analysis and return composite score + signals."""
    if not price or len(closes) == 0:
        return {"score": 0, "verdict": "数据不足", "signals": [], "summary": "无法分析：数据不足"}

    close_series = closes  # full list for Bollinger/OBV/ATR

    # Compute technical indicators needed for MA/RSI/MACD signals
    sma_20 = sum(close_series[-20:]) / 20 if len(close_series) >= 20 else None
    sma_50 = sum(close_series[-50:]) / 50 if len(close_series) >= 50 else None
    sma_200 = sum(close_series[-200:]) / 200 if len(close_series) >= 200 else None

    rsi = None
    if len(close_series) >= 15:
        deltas = [close_series[i] - close_series[i - 1] for i in range(1, len(close_series))]
        recent = deltas[-14:]
        gains = [d for d in recent if d > 0]
        losses = [-d for d in recent if d < 0]
        avg_gain = sum(gains) / 14 if gains else 0
        avg_loss = sum(losses) / 14 if losses else 0
        if avg_loss == 0:
            rsi = 100.0
        else:
            rsi = 100 - (100 / (1 + avg_gain / avg_loss))

    macd = macd_signal = None
    if len(close_series) >= 26:
        def _ema(data, period):
            result = [sum(data[:period]) / period]
            m = 2 / (period + 1)
            for p in data[period:]:
                result.append((p - result[-1]) * m + result[-1])
            return result
        ema12 = _ema(close_series, 12)
        ema26 = _ema(close_series, 26)
        offset = len(ema12) - len(ema26)
        macd_line = [f - s for f, s in zip(ema12[offset:], ema26)]
        if len(macd_line) >= 9:
            signal_line = _ema(macd_line, 9)
            macd = macd_line[-1]
            macd_signal = signal_line[-1]

    # Gather all signals
    signals = []
    signals.extend(compute_ma_signals(price, sma_20, sma_50, sma_200))
    signals.extend(compute_rsi_signals(rsi))
    signals.extend(compute_macd_signals(macd, macd_signal))
    signals.extend(compute_bollinger_signals(price, close_series))
    signals.extend(compute_atr_signals(highs, lows, close_series))
    signals.extend(compute_stochastic_signals(highs, lows, close_series))
    signals.extend(compute_obv_signals(close_series, volumes))
    signals.extend(compute_range_signals(price, high_52w, low_52w))
    signals.extend(compute_pe_signals(pe_ratio))

    score = sum(s["weight"] for s in signals)
    score = max(-100, min(100, score))

    if score >= 30:
        verdict = "强烈买入 STRONG BUY"
    elif score >= 10:
        verdict = "适度买入 MODERATE BUY"
    elif score > -10:
        verdict = "中性 NEUTRAL"
    elif score > -30:
        verdict = "适度卖出 MODERATE SELL"
    else:
        verdict = "强烈卖出 STRONG SELL"

    bullish = [s for s in signals if s["type"] == "bullish"]
    bearish = [s for s in signals if s["type"] == "bearish"]

    summary = (
        f"综合评分: {score}/100 ({verdict})。"
        f"{len(bullish)}个看多信号, {len(bearish)}个看空信号。"
        f"最强看多: {bullish[0]['name'] if bullish else '无'}"
        f"{' | 最强看空: ' + bearish[0]['name'] if bearish else ''}"
    )

    return {
        "symbol": symbol,
        "score": score,
        "verdict": verdict,
        "signals": signals,
        "bullish_count": len(bullish),
        "bearish_count": len(bearish),
        "rsi": round(rsi, 2) if rsi else None,
        "macd": round(macd, 4) if macd else None,
        "macd_signal": round(macd_signal, 4) if macd_signal else None,
        "sma_20": round(sma_20, 2) if sma_20 else None,
        "sma_50": round(sma_50, 2) if sma_50 else None,
        "sma_200": round(sma_200, 2) if sma_200 else None,
        "summary": summary,
    }
