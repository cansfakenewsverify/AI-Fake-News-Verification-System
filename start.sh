#!/bin/bash
# AI 假訊息驗證系統 - 一鍵啟動（Linux / macOS）

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/code/backend/factcheck_system"
FRONTEND_DIR="$SCRIPT_DIR/code/frontend"
VENV="$BACKEND_DIR/venv"

echo ""
echo " ========================================"
echo "  AI 假訊息驗證系統 - 一鍵啟動"
echo " ========================================"
echo ""

# ── 環境檢查 ──────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "[錯誤] 找不到 Python3，請先安裝 Python 3.11+"
    exit 1
fi
if ! command -v node &>/dev/null; then
    echo "[錯誤] 找不到 Node.js，請先安裝 Node.js 18+"
    exit 1
fi

# ── 建立 .env（若不存在）────────────────────────────────────
if [ ! -f "$BACKEND_DIR/.env" ]; then
    cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
    echo "[設定] 已建立 .env，請填入 GOOGLE_API_KEY"
fi

# ── 後端虛擬環境 ──────────────────────────────────────────
if [ ! -d "$VENV" ]; then
    echo "[後端] 建立 Python 虛擬環境..."
    python3 -m venv "$VENV"
fi

echo "[後端] 安裝/更新套件..."
"$VENV/bin/pip" install -r "$BACKEND_DIR/requirements.txt" -q --disable-pip-version-check

# ── 前端套件 ──────────────────────────────────────────────
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    echo "[前端] 安裝 npm 套件..."
    (cd "$FRONTEND_DIR" && npm install)
fi

# ── 啟動後端 ──────────────────────────────────────────────
echo "[後端] 啟動 FastAPI (http://localhost:8000)..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    osascript -e "tell app \"Terminal\" to do script \"cd '$BACKEND_DIR' && source venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload\""
else
    gnome-terminal -- bash -c "cd '$BACKEND_DIR' && source venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload; exec bash" 2>/dev/null \
    || xterm -title "後端 FastAPI" -e "cd '$BACKEND_DIR' && source venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload" &
fi

sleep 3

# ── 啟動前端 ──────────────────────────────────────────────
echo "[前端] 啟動 React 開發伺服器 (http://localhost:5173)..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    osascript -e "tell app \"Terminal\" to do script \"cd '$FRONTEND_DIR' && npm run dev\""
else
    gnome-terminal -- bash -c "cd '$FRONTEND_DIR' && npm run dev; exec bash" 2>/dev/null \
    || xterm -title "前端 React" -e "cd '$FRONTEND_DIR' && npm run dev" &
fi

sleep 4

# ── 開啟瀏覽器 ────────────────────────────────────────────
echo "[瀏覽器] 開啟應用程式..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    open "http://localhost:5173"
else
    xdg-open "http://localhost:5173" 2>/dev/null || true
fi

echo ""
echo " ========================================"
echo "  啟動完成！"
echo ""
echo "  前端介面：http://localhost:5173"
echo "  後端 API：http://localhost:8000"
echo "  API 文件：http://localhost:8000/docs"
echo " ========================================"
echo ""
