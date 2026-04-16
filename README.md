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

### Setup

```bash
git clone [https://github.com/cansfakenewsverify/AI-Fake-News-Verification-System.git](https://github.com/cansfakenewsverify/AI-Fake-News-Verification-System.git)
cd AI-Fake-News-Verification-System

Backend

cd code/backend
python -m venv venv
# Windows: .\venv\Scripts\activate
pip install -r requirements.txt

Frontend

cd code/frontend
npm install

## Usage

啟動服務流程
Backend: 執行 uvicorn main:app --reload 啟動 API 伺服器於 8000 埠位。
Frontend: 執行 npm run dev 啟動 React 開發環境於 5173 埠位。

Project Structure
AI-Fake-News-Verification-System/
├── README.md                      # 專案主說明文件
├── docs/                          # 開發白皮書與需求規格書
├── presentations/                 # 投影片與行政表格
├── assets/                        # 系統架構圖與 Demo 截圖
└── code/                          # 核心程式碼
    ├── frontend/                  # React 前端專案原始碼
    └── backend/                   # FastAPI 後端專案原始碼

## Authors
廖晢勛 — 系統架構設計、API 整合、專案時程管理
石岱勳 — Prompt Engineering、Gemini API 邏輯實作
廖育翔 — 網頁資料擷取服務開發
張宇宏 — 互動介面與非同步數據串接
姚睿 — 測試案例規劃與環境建置
