#!/bin/bash
# AI 假訊息查核系統 - 一鍵啟動（Linux / macOS）：後端 + 查核儀 + React
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/code/backend"
FRONTEND_DIR="$SCRIPT_DIR/code/frontend"
VENV="$BACKEND_DIR/venv"
HTML_PORT=8090

echo ""
echo " ========================================"
echo "  AI 假訊息查核系統 - 一鍵啟動"
echo " ========================================"
echo ""

# ── 環境檢查 ──────────────────────────────────────────────
command -v python3 &>/dev/null || { echo "[錯誤] 需要 Python 3.11+"; exit 1; }
command -v node    &>/dev/null || { echo "[錯誤] 需要 Node.js 18+"; exit 1; }

# ── 建立 .env（若不存在）────────────────────────────────────
if [ ! -f "$BACKEND_DIR/.env" ]; then
    cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
    echo "[設定] 已建立 .env，請填入 API 金鑰"
fi

# ── 後端虛擬環境 + 套件 ────────────────────────────────────
if [ ! -d "$VENV" ]; then
    echo "[後端] 建立 Python 虛擬環境..."
    python3 -m venv "$VENV"
fi
echo "[後端] 安裝/更新套件..."
"$VENV/bin/pip" install -r "$BACKEND_DIR/requirements.txt" -q --disable-pip-version-check

# ── 前端套件（首次）──────────────────────────────────────
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    echo "[前端] 安裝 npm 套件..."
    (cd "$FRONTEND_DIR" && npm install)
fi

run_term() {  # $1=title  $2=command
    if [[ "$OSTYPE" == "darwin"* ]]; then
        osascript -e "tell app \"Terminal\" to do script \"$2\""
    else
        gnome-terminal --title "$1" -- bash -c "$2; exec bash" 2>/dev/null \
        || xterm -title "$1" -e "$2" &
    fi
}

# ── 啟動後端 ──────────────────────────────────────────────
echo "[後端] 啟動 FastAPI (http://localhost:8000)..."
run_term "後端 FastAPI" "cd '$BACKEND_DIR' && source venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
sleep 3

# ── 啟動查核儀（單檔 HTML 靜態伺服器）──────────────────────
echo "[前端] 啟動查核儀 (http://localhost:$HTML_PORT)..."
run_term "查核儀 前端" "cd '$SCRIPT_DIR' && python3 -m http.server $HTML_PORT"
sleep 1

# ── 啟動 React ────────────────────────────────────────────
echo "[前端] 啟動 React (http://localhost:5173)..."
run_term "React 前端" "cd '$FRONTEND_DIR' && npm run dev"
sleep 3

# ── 開啟瀏覽器 ────────────────────────────────────────────
DETECTOR="http://localhost:$HTML_PORT/fake-news-detector.html"
REACT="http://localhost:5173"
if [[ "$OSTYPE" == "darwin"* ]]; then
    open "$DETECTOR"; open "$REACT"
else
    xdg-open "$DETECTOR" 2>/dev/null || true
    xdg-open "$REACT" 2>/dev/null || true
fi

echo ""
echo " ========================================"
echo "  啟動完成！"
echo "  查核儀  ：$DETECTOR"
echo "  React   ：$REACT"
echo "  後端 API：http://localhost:8000/docs"
echo " ========================================"
echo ""
