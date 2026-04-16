# AI-Driven Fake News and Scam Verification System

![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)
![React](https://img.shields.io/badge/Frontend-React-61DAFB?logo=react&logoColor=white)
![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi&logoColor=white)

一個整合大型語言模型 (LLM) 與網頁擷取技術的自動化認知防護與假訊息查核平台。

## Overview

本系統旨在解決日益嚴重的網路詐騙與假訊息問題。透過建立一個前後端分離的現代化 Web 應用程式，系統能夠接收使用者輸入的可疑網址，自動擷取網頁純文字內容，並透過 Google Gemini API 進行多維度的語意分析與真實性交叉比對，最終以風險等級即時回饋給使用者。

## Features

- **Decoupled Architecture** — 前端 React 互動介面與後端 FastAPI RESTful 服務完全分離。
- **Dynamic Content Scraping** — 具備網頁內容精準提取與雜訊過濾功能。
- **AI Decision Engine** — 採用 V4.1 System Prompt 驅動 Gemini 模型提供具解釋性的判定。
- **Mock-Up for Phase 1** — 已實作符合白皮書規範的 Mock API 供前端介面先行測試。

## Installation

### 1. 初次設定與下載專案
```bash
git clone https://github.com/cansfakenewsverify/AI-Fake-News-Verification-System.git
cd AI-Fake-News-Verification-System
```

### 2. 環境變數設定 (.env)
在啟動後端系統前，您必須建立一個 `.env` 檔案以存放您的 Google Gemini API Key。
請在 `code/backend/` 目錄下建立 `.env` 檔案，並寫入以下內容：
```ini
# (必填) Google Gemini API Key
GOOGLE_API_KEY=您的_API_KEY

# 關閉成果展示模式以啟用真實 AI 判定
DEMO_MODE=False
```

### 3. Backend (後端)
後端由 FastAPI 所驅動，包含了爬蟲模組與 AI 分析引擎。請務必在**虛擬環境**中安裝依賴。
```bash
cd code/backend

# 建立虛擬環境
python -m venv venv

# 啟動虛擬環境 (依據您的作業系統)
# Windows: 
.\venv\Scripts\activate
# macOS/Linux: 
source venv/bin/activate

# 安裝所有必要套件
pip install -r requirements.txt
```

### 4. Frontend (前端)
前端使用 React 與 Vite 打造，需透過 npm 或 yarn 安裝依賴。
```bash
cd code/frontend
npm install
```

## Usage

### 啟動服務流程
每次開發或測試時，請開啟**兩個獨立的終端機**分別啟動前後端：

- **啟動 Backend** (在 Terminal 1):
  ```bash
  cd code/backend
  .\venv\Scripts\activate
  uvicorn main:app
  ```
  *(伺服器將執行於 http://localhost:8000)*

- **啟動 Frontend** (在 Terminal 2):
  ```bash
  cd code/frontend
  npm run dev
  ```
  *(前端將執行於 http://localhost:5173)*


## Project Structure

```text
AI-Fake-News-Verification-System/
├── README.md                      # 專案主說明文件
├── docs/                          # 開發白皮書與需求規格書
├── presentations/                 # 投影片與行政表格
├── assets/                        # 系統架構圖與 Demo 截圖
└── code/                          # 核心程式碼
    ├── frontend/                  # React 前端專案原始碼
    └── backend/                   # FastAPI 後端專案原始碼
```

## Authors
- **廖晢勛** — 系統架構設計、API 整合、專案時程管理
- **石岱勳** — Prompt Engineering、Gemini API 邏輯實作
- **廖育翔** — 網頁資料擷取服務開發
- **張宇宏** — 互動介面與非同步數據串接
- **姚睿** — 測試案例規劃與環境建置