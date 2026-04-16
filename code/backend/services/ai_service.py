def analyze_content(text: str) -> dict:
    return {
        "is_risk": True,
        "risk_type": "MISINFO",
        "category": "Health_Rumor",
        "confidence_score": 0.85,
        "summary": "這是一則關於健康養生的常見假訊息...",
        "explanation": "缺乏科學根據...",
        "sources": [
            {
                "title": "TFC 查核報告",
                "url": "https://tfc-taiwan.org.tw/"
            }
        ]
    }
