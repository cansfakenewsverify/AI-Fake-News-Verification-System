from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List

from services.scraper_service import get_text_from_url
from services.ai_service import analyze_content

app = FastAPI(title="Anti-Scam API", version="1.0")

# CORS 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic Models 定義
class AnalyzeRequest(BaseModel):
    content: str

class SourceItem(BaseModel):
    title: str
    url: str

class AnalyzeResponse(BaseModel):
    is_risk: bool
    risk_type: str
    category: str
    confidence_score: float
    summary: str
    explanation: str
    sources: List[SourceItem]

# Health Check 路由
@app.get("/")
def health_check():
    return {"status": "ok", "message": "Anti-Scam API Phase 1 is running"}

# Mock API 路由
@app.post("/api/analyze/text", response_model=AnalyzeResponse)
def analyze_text(request: AnalyzeRequest):
    # 1. 呼叫 get_text_from_url 傳入前端給的網址
    scraped_text = get_text_from_url(request.content)
    
    # 2. 將爬蟲結果傳給 analyze_content 進行分析
    analysis_result = analyze_content(scraped_text)
    
    # 3. 將分析結果回傳
    return AnalyzeResponse(**analysis_result)
