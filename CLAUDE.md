# AStock-MCP

A 股数据 MCP Server。基于 AKShare，提供实时行情、技术分析、持续监控。

## 会话引导

每次会话开始时，先询问用户是否要输入/更新持仓信息（set_portfolio）。如果用户跳过，直接用现有数据。
