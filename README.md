# A 股 MCP Server

基于 AKShare 的 A 股数据 MCP Server，为 AI 助手提供 A 股市场数据接口。

## 特性

- **13 个数据工具**：实时行情、历史K线、技术指标、基本面等
- **综合技术分析**：多指标加权评分系统（-100~+100）
  - MA均线系统（金叉/死叉、MA200 位置）
  - RSI 超买超卖、MACD 交叉、布林带、随机指标
  - OBV 量价背离、ATR 波动率、52周区间
- **持续监控**：将股票加入监控列表，定时获取最新数据并缓存到本地 SQLite 数据库
- **本地缓存**：行情和K线数据自动缓存，支持离线查询历史

## 安装

```bash
cd mcp-server
pip install -e .
```

## 配置到 Claude Code

```bash
claude mcp add a-stock-mcp -- pip install -e D:\git-project\stock\mcp-server && python -m a_stock_mcp
```

## 可用工具

| 工具 | 说明 |
|------|------|
| `get_stock_list` | 获取 A 股股票列表 |
| `get_realtime_quote` | 获取单只股票实时行情 |
| `get_realtime_quotes` | 批量获取多只股票实时行情 |
| `get_hist_kline` | 获取历史 K 线数据（日/周/月） |
| `get_intraday` | 获取当日分时数据 |
| `get_financial_indicators` | 获取财务指标 |
| `get_balance_sheet` | 获取资产负债表 |
| `get_income_statement` | 获取利润表 |
| `get_dragon_tiger` | 获取龙虎榜数据 |
| `get_north_flow` | 获取北向资金数据 |
| `get_margin_detail` | 获取融资融券数据 |
| `get_technical_indicators` | 计算技术指标（MACD/RSI/KDJ/BOLL等） |
| `get_stock_info` | 获取股票基本信息 |
| `analyze_stock` | 综合技术分析（多指标加权评分-100~+100） |
| `start_monitoring` | 开始持续监控一只股票（定时缓存到本地SQLite） |
| `stop_monitoring` | 停止监控 |
| `monitoring_status` | 查看所有监控中的股票 |

## HTTP 模式

```bash
python -m a_stock_mcp --http --host 0.0.0.0 --port 8080
```
