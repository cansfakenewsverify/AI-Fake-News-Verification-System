"""
Seed script: populate knowledge_base.parquet with sample records.

Usage:
    cd codeackend
    venv\\Scripts\\python scripts/seed_data.py
"""
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# Allow running from project root or scripts/
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app.services.pandas_store import PandasStore


# ─────────────────────────────────────────────────────────────
# 範本資料 - 涵蓋所有 risk_type 與多數 category
# ─────────────────────────────────────────────────────────────
SAMPLES = [
    # ═══ SCAM 類 ═══
    {
        "data_type": "TEXT",
        "source_url": None,
        "raw_content": "恭喜您獲得 LINE 投資股票群 VIP 名額！老師帶單穩賺不賠，加我 LINE: stock_master_99 立即進場",
        "ai_result": {
            "is_risk": True,
            "risk_type": "SCAM",
            "category": "Investment",
            "confidence_score": 0.97,
            "summary": "典型投資詐騙話術：以「穩賺不賠」誘導加入 LINE 群組。",
            "explanation": "金管會多次警告，合法券商不會透過 LINE 群組「帶單」。詐騙集團常用「飆股」「老師」等詞。",
            "sources": [
                {"title": "金管會投資詐騙警示", "url": "https://www.fsc.gov.tw/ch/home.jsp?id=2"},
                {"title": "165 反詐騙專線", "url": "https://165.npa.gov.tw/"},
            ],
        },
    },
    {
        "data_type": "URL",
        "source_url": "https://chunghwa-post-tw.cc/parcel/track123",
        "raw_content": "您的包裹已抵達中華郵政集散中心，請點擊連結繳交關稅 NT$58 完成領取。",
        "ai_result": {
            "is_risk": True,
            "risk_type": "SCAM",
            "category": "Phishing",
            "confidence_score": 0.99,
            "summary": "假冒中華郵政的釣魚網站（網域為 .cc 非官方 .gov.tw）。",
            "explanation": "中華郵政官方網域為 post.gov.tw，.cc 為高風險免洗網域，常被詐騙集團使用。",
            "sources": [
                {"title": "中華郵政官網", "url": "https://www.post.gov.tw/"},
            ],
        },
    },
    {
        "data_type": "TEXT",
        "source_url": None,
        "raw_content": "兒子，我手機壞了用同事的傳訊息，現在急需 5 萬塊匯款請幫我先處理",
        "ai_result": {
            "is_risk": True,
            "risk_type": "SCAM",
            "category": "Impersonation",
            "confidence_score": 0.93,
            "summary": "假冒親友的緊急匯款詐騙手法。",
            "explanation": "詐騙集團常以「手機壞了」「換號碼」掩蓋身份，誘導被害者匯款。請務必透過原本電話確認。",
            "sources": [],
        },
    },
    {
        "data_type": "TEXT",
        "source_url": None,
        "raw_content": "蝦皮客服通知：您的訂單因刷卡誤設為分期付款，請立即至 ATM 操作取消，否則每月扣款 12 期",
        "ai_result": {
            "is_risk": True,
            "risk_type": "SCAM",
            "category": "E-Commerce",
            "confidence_score": 0.96,
            "summary": "解除分期付款詐騙：誘導被害者至 ATM 操作。",
            "explanation": "ATM 無法「解除」任何設定，這是經典話術。蝦皮客服不會要求你去 ATM 操作。",
            "sources": [
                {"title": "165 解除分期詐騙說明", "url": "https://165.npa.gov.tw/"},
            ],
        },
    },

    # ═══ MISINFO 類 ═══
    {
        "data_type": "TEXT",
        "source_url": None,
        "raw_content": "微波爐加熱的食物會產生致癌物！醫師警告長期食用會得癌症，請大家分享給家人",
        "ai_result": {
            "is_risk": True,
            "risk_type": "MISINFO",
            "category": "Health_Rumor",
            "confidence_score": 0.92,
            "summary": "微波爐致癌的偽科學謠言，已被多家事實查核機構闢謠。",
            "explanation": "微波加熱原理為水分子震盪生熱，不會改變食物的化學結構或產生致癌物。FDA 與台灣食藥署均無此警告。",
            "sources": [
                {"title": "台灣事實查核中心", "url": "https://tfc-taiwan.org.tw/"},
                {"title": "MyGoPen 闢謠", "url": "https://www.mygopen.com/"},
            ],
        },
    },
    {
        "data_type": "URL",
        "source_url": "https://example-content-farm.com/article/12345",
        "raw_content": "震驚！科學家發現喝水加 X 物質可逆轉老化，醫界全瘋了！明星都在用",
        "ai_result": {
            "is_risk": True,
            "risk_type": "MISINFO",
            "category": "Content_Farm",
            "confidence_score": 0.88,
            "summary": "標題黨內容農場文章，誇大不實宣稱。",
            "explanation": "「逆轉老化」屬未經科學證實的健康宣稱，違反食安法第 28 條。",
            "sources": [],
        },
    },

    # ═══ SAFE 類 ═══
    {
        "data_type": "URL",
        "source_url": "https://www.cdc.gov.tw/Bulletin/Detail/example-real-news",
        "raw_content": "衛福部疾管署公告：本年度公費流感疫苗自 10 月 1 日起開放接種，符合資格民眾可至合約院所施打。",
        "ai_result": {
            "is_risk": False,
            "risk_type": "SAFE",
            "category": "Safe",
            "confidence_score": 0.99,
            "summary": "衛福部疾管署官方公告，內容屬實。",
            "explanation": "網域為 cdc.gov.tw，為官方政府網站。流感疫苗接種計畫每年 10 月公費開放屬常規政策。",
            "sources": [
                {"title": "疾管署官網", "url": "https://www.cdc.gov.tw/"},
            ],
        },
    },
    {
        "data_type": "URL",
        "source_url": "https://www.cna.com.tw/news/aipl/example-news.aspx",
        "raw_content": "中央社報導：立法院三讀通過某法案修正案，將於明年 1 月 1 日施行。",
        "ai_result": {
            "is_risk": False,
            "risk_type": "SAFE",
            "category": "Safe",
            "confidence_score": 0.95,
            "summary": "中央社新聞報導，來源為公信力媒體。",
            "explanation": "中央社（CNA）為國家通訊社，新聞內容經編輯審核。",
            "sources": [],
        },
    },
]


def main():
    print("─" * 60)
    print("  Seeding knowledge_base.parquet with sample data")
    print("─" * 60)

    # 切到 backend 根目錄，確保 data/ 路徑正確
    import os
    os.chdir(ROOT)

    store = PandasStore()
    existing = store.get_all_records()
    print(f"  Existing records: {len(existing)}")

    base_time = datetime.now() - timedelta(days=7)
    added = 0

    for i, sample in enumerate(SAMPLES):
        # 模擬不同的建立時間
        fake_vector = [0.0] * 768  # 真實使用時由 Embedding API 生成
        content_hash = f"seed_{i}_{uuid.uuid4().hex[:16]}"

        store.save_record(
            data_type=sample["data_type"],
            raw_content=sample["raw_content"],
            content_hash=content_hash,
            content_vector=fake_vector,
            ai_result=sample["ai_result"],
            source_url=sample.get("source_url"),
        )
        added += 1
        risk = sample["ai_result"]["risk_type"]
        cat = sample["ai_result"]["category"]
        print(f"  [{i+1:2d}] {risk:7s} / {cat:15s} - {sample['raw_content'][:30]}...")

    final = store.get_all_records()
    print("─" * 60)
    print(f"  Done! Added {added} records. Total now: {len(final)}")
    print(f"  File: {store.knowledge_base_path}")
    print("─" * 60)


if __name__ == "__main__":
    main()
