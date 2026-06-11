#!/bin/bash
# AI 假訊息查核儀 - 一鍵啟動（Linux / macOS）：後端 + HTML 查核儀
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/code/backend"
VENV="$BACKEND_DIR/venv"
HTML_PORT=8090

echo ""
echo " ========================================"
echo "  AI 假訊息查核儀 - 一鍵啟動"
echo " ========================================"
echo ""

# ── 環境檢查（只需 Python3）─────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "[錯誤] 找不到 Python3，請先安裝 Python 3.11+"
    exit 1
fi

# ── 建立 .env（若不存在）────────────────────────────────────
if [ ! -f "$BACKEND_DIR/.env" ]; then
    cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
    echo "[設定] 已建立 .env，請填入 API 金鑰"
fi

# ── 後端虛擬環境 ──────────────────────────────────────────
if [ ! -d "$VENV" ]; then
    echo "[後端] 建立 Python 虛擬環境..."
    python3 -m venv "$VENV"
fi
echo "[後端] 安裝/更新套件..."
"$VENV/bin/pip" install -r "$BACKEND_DIR/requirements.txt" -q --disable-pip-version-check

# ── 啟動後端 ──────────────────────────────────────────────
echo "[後端] 啟動 FastAPI (http://localhost:8000)..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    osascript -e "tell app \"Terminal\" to do script \"cd '$BACKEND_DIR' && source venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload\""
else
    gnome-terminal -- bash -c "cd '$BACKEND_DIR' && source venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload; exec bash" 2>/dev/null \
    || xterm -title "後端 FastAPI" -e "cd '$BACKEND_DIR' && source venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload" &
fi
sleep 3

# ── 啟動查核儀前端（單檔 HTML 的靜態伺服器）──────────────────
echo "[前端] 啟動查核儀 (http://localhost:$HTML_PORT)..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    osascript -e "tell app \"Terminal\" to do script \"cd '$SCRIPT_DIR' && python3 -m http.server $HTML_PORT\""
else
    gnome-terminal -- bash -c "cd '$SCRIPT_DIR' && python3 -m http.server $HTML_PORT; exec bash" 2>/dev/null \
    || xterm -title "查核儀 前端" -e "cd '$SCRIPT_DIR' && python3 -m http.server $HTML_PORT" &
fi
sleep 2

# ── 開啟瀏覽器 ────────────────────────────────────────────
URL="http://localhost:$HTML_PORT/fake-news-detector.html"
echo "[瀏覽器] 開啟 $URL ..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    open "$URL"
else
    xdg-open "$URL" 2>/dev/null || true
fi

echo ""
echo " ========================================"
echo "  啟動完成！"
echo "  查核儀  ：$URL"
echo "  後端 API：http://localhost:8000/docs"
echo "  （React 前端仍可用：cd code/frontend && npm run dev）"
echo " ========================================"
echo ""
