#!/bin/bash
# AI 假訊息查核系統 - 本機開發用啟動腳本（Linux / macOS）：後端 + React 開發伺服器
# 要「使用」系統請直接開正式網站：https://fakenewsverify.vercel.app
# （前端 Vercel、後端 Render、資料 Supabase；見 docs/rebuild/runbook_cloud_deploy.md）
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/code/backend"
FRONTEND_DIR="$SCRIPT_DIR/code/frontend"
VENV="$BACKEND_DIR/venv"

echo ""
echo " ========================================"
echo "  AI 假訊息查核系統 - 本機開發模式"
echo "  正式網站：https://fakenewsverify.vercel.app"
echo " ========================================"
echo ""

# ── 環境檢查 ──────────────────────────────────────────────
command -v python3 &>/dev/null || { echo "[錯誤] 需要 Python 3.11+"; exit 1; }
command -v node    &>/dev/null || { echo "[錯誤] 需要 Node.js 18+"; exit 1; }

# ── 建立 .env（若不存在）────────────────────────────────────
# spec §5.6：首次建立的 .env 若 ADMIN_TOKEN 為空，自動寫入 32 字亂數（不印出 token 本體）
if [ ! -f "$BACKEND_DIR/.env" ]; then
    cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
    echo "[設定] 已建立 .env，請填入 API 金鑰"
fi
# 每次啟動都確保 ADMIN_TOKEN 有值（空行或缺行就補上 32 字亂數，不印出 token）
python3 "$BACKEND_DIR/scripts/ensure_admin_token.py" "$BACKEND_DIR/.env"

# ── 後端虛擬環境 + 套件 ────────────────────────────────────
if [ ! -d "$VENV" ]; then
    echo "[後端] 建立 Python 虛擬環境..."
    python3 -m venv "$VENV"
fi
echo "[後端] 安裝/更新套件..."
# python -m pip（不用 bin/pip）：venv 裡的啟動器寫死了建立時的路徑，專案資料夾搬家後會失效
"$VENV/bin/python" -m pip install -r "$BACKEND_DIR/requirements.txt" -q --disable-pip-version-check

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
run_term "後端 FastAPI" "cd '$BACKEND_DIR' && venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
sleep 3

# ── 啟動 React ────────────────────────────────────────────
echo "[前端] 啟動 React (http://localhost:5173)..."
run_term "React 前端" "cd '$FRONTEND_DIR' && npm run dev"
sleep 3

# ── 開啟瀏覽器 ────────────────────────────────────────────
REACT="http://localhost:5173"
if [[ "$OSTYPE" == "darwin"* ]]; then
    open "$REACT"
else
    xdg-open "$REACT" 2>/dev/null || true
fi

echo ""
echo " ========================================"
echo "  啟動完成！（本機開發用，資料是本機檔案）"
echo "  主介面  ：$REACT"
echo "  後端 API：http://localhost:8000/docs"
echo " ========================================"
echo ""
