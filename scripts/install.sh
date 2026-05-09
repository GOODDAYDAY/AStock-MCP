#!/usr/bin/env bash
# AStock-MCP macOS 安装启动脚本
# 用法: chmod +x install.sh && ./install.sh

set -e

PROJECT_DIR="${1:-$(pwd)}"

echo "======================================="
echo "   AStock-MCP macOS 一键安装启动"
echo "======================================="
echo ""

# ── 1. 检测 Python ──
if ! command -v python3 &>/dev/null; then
    echo "[!] 请先安装 Python 3.10+"
    echo "    brew install python"
    exit 1
fi
echo "[OK] Python: $(python3 --version)"

# ── 2. 检测/安装 Claude Code CLI ──
if ! command -v claude &>/dev/null; then
    echo "[*] 未检测到 Claude Code CLI，正在安装..."
    if ! command -v npm &>/dev/null; then
        echo "[!] 请先安装 Node.js"
        echo "    brew install node"
        exit 1
    fi
    npm install -g @anthropic-ai/claude-code
fi
echo "[OK] Claude Code: $(claude --version 2>&1)"

# ── 3. 安装项目依赖 ──
echo "[*] 安装 Python 依赖..."
pip3 install -e "$PROJECT_DIR"
echo "[OK] 依赖安装完成"

# ── 4. 交互输入 ──
echo ""
echo "--- 配置 Claude Code ---"
read -r -p "请输入 Anthropic API Key: " api_key
while [ -z "$api_key" ]; do
    read -r -p "API Key 不能为空，请重新输入: " api_key
done

read -r -p "请输入模型名称 (直接回车默认 claude-sonnet-4-6): " model
if [ -z "$model" ]; then
    model="claude-sonnet-4-6"
fi

# ── 5. 创建启动脚本（不修改 ~/.claude.json，用 --mcp-config 传入）──
echo "[*] 创建启动脚本..."

MCP_CFG="$PROJECT_DIR/mcp-config.json"

cat > "$PROJECT_DIR/start.sh" <<SHEOF
#!/usr/bin/env bash
cd "$PROJECT_DIR"
echo "[AStock-MCP] 启动 Claude Code ..."
claude --model $model --mcp-config "$MCP_CFG" --project "$PROJECT_DIR"
SHEOF
chmod +x "$PROJECT_DIR/start.sh"

cat > "$PROJECT_DIR/start-with-key.sh" <<SHEOF
#!/usr/bin/env bash
export ANTHROPIC_API_KEY="$api_key"
cd "$PROJECT_DIR"
echo "[AStock-MCP] 启动 Claude Code ..."
claude --model $model --mcp-config "$MCP_CFG" --project "$PROJECT_DIR"
SHEOF
chmod +x "$PROJECT_DIR/start-with-key.sh"

echo ""
echo "======================================="
echo "   安装完成！"
echo "======================================="
echo ""
echo "启动方式："
echo "  1. ./start.sh（启动后手动输入 API Key）"
echo "  2. ./start-with-key.sh（直接启动，已含 Key）"
echo "  3. 或直接运行: claude --project \"$PROJECT_DIR\""
echo ""
echo "首次启动后，在 Claude Code 中即可使用 a-stock-mcp 的全部工具"
