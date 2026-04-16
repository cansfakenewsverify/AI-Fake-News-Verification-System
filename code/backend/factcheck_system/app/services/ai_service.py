"""
AI 分析服務 - 整合 Gemini 與 Embedding
"""
import json
from typing import Dict, List, Optional, Any
import os

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from google import genai
    USE_NEW_API = True
except ImportError:
    try:
        import google.generativeai as genai
        USE_NEW_API = False
    except ImportError:
        raise ImportError("請安裝 google-genai 或 google-generativeai 套件")

from app.config import settings

if not USE_NEW_API and settings.GOOGLE_API_KEY:
    genai.configure(api_key=settings.GOOGLE_API_KEY)


# V4.1 System Prompt（嚴格版本）
SYSTEM_PROMPT_V41 = """

# Task (任務說明)
請依序執行以下步驟進行分析，並嚴格遵守「網址權威性大於內容可信度」的原則。

# Critical Priority Logic (最高優先級判斷法則 - 必讀)
在分析任何文字內容之前，必須先對「網址 (URL)」執行**一票否決**判定：

1. **網址的一票否決權 (The URL Kill Switch)**：
   - **規則**：如果網址屬於 **免洗/高風險網域** (如 .cc, .top, .xyz, IP位址) 或 **低成本架站平台** (如 Google Sites, Wix)，但內容宣稱是「知名企業」或「官方機構」。
   - **判定**：**直接判定為高風險 (`is_risk: true`, `risk_type: "SCAM"`)，信心分數 0.95。**
   - **理由**：真實的名人與大企業絕不會使用這類網址。

# Analysis Steps (執行步驟)
1. **意圖與類型識別**：
   - 判斷內容意圖：是騙取金錢個資 (Scam)？還是製造恐慌/誤導大眾 (Misinformation)？

2. **雙重事實查核 (Google Search 必須執行)**：
   - **Phase A: 詐騙查核** (針對金錢/連結)：
     - 搜尋網域信譽、官方網址比對。
   - **Phase B: 假訊息查核** (針對健康/政治/舊聞)：
     - **務必優先參考**：台灣事實查核中心 (TFC)、MyGoPen、Cofacts、CNA中央社。
     - 檢查是否為「舊聞重炒」或「偽科學謠言」。

3. **短影音邏輯 (若來源為 TikTok/Reels)**：
   - 檢查語音是否誘導「點擊主頁連結 (Link in Bio)」(詐騙特徵)。
   - 檢查是否使用機器人語音傳播農場文 (假訊息特徵)。

4. **標準化摘要**：
   - 去除雜訊，保留人名、關鍵字、宣稱的後果 (如：帳戶凍結、會致癌)。

# Category List (分類清單 - 請嚴格遵守)
[詐騙類 - SCAM]
- `Investment`: 投資詐騙 (飆股、假老師)
- `Phishing`: 釣魚連結 (假銀行、假物流)
- `Impersonation`: 假冒親友/公務員/名人
- `E-Commerce`: 網購/解除分期
- `Job`: 求職詐騙
- `Romance`: 愛情詐騙

[假訊息類 - MISINFO]
- `Health_Rumor`: 健康/食安謠言 (偽科學、假養生)
- `Political_Rumor`: 政治/政策謠言 (陰謀論)
- `Content_Farm`: 內容農場/標題黨 (誇大不實)
- `Old_News`: 舊聞重炒 (過期資訊誤導)
- `Urban_Legend`: 都市傳說

[其他]
- `Safe`: 安全且正確的資訊 (官方公告)
- `Irrelevant`: 無關內容 (自拍、閒聊)

# Output Format (輸出格式)
你 **必須且只能** 回傳一個標準的 JSON 物件。不要使用 Markdown。

JSON 結構如下：
{
  "is_risk": (Boolean, 只要是詐騙 OR 假訊息，都填 true),
  "risk_type": (String, 若為詐騙填 "SCAM", 若為假訊息填 "MISINFO", 安全則填 "SAFE"),
  "category": (String, 必須從上面的分類清單中選擇),
  "confidence_score": (Float, 0.95-1.0 為網址直接命中的詐騙; 0.0-1.0 代表信心程度),
  "summary": (String, 用於向量資料庫的高品質摘要),
  "explanation": (String, 白話解釋。若是假訊息，請指出「正確事實」是什麼),
  "sources": [
    {
      "title": (String, 來源標題),
      "url": (String, 來源網址。⚠️ 重要規則：
        1. **必須是具體文章頁面** (Specific Article URL)，例如 `https://tfc-taiwan.org.tw/articles/12345`。
        2. **嚴禁回傳首頁/根域名** (Root Domain)。例如：`https://tfc-taiwan.org.tw/` 或 `https://www.cna.com.tw/` 是**無效的**。
        3. 若找不到具體文章連結，該來源請直接留空或不列出，**寧缺勿濫**。)
    }
  ]
}
"""


def _default_fallback_result(err_msg: str) -> Dict[str, Any]:
    """API 失敗時回傳的結構化結果（不拋錯，方便前端顯示）"""
    return {
        "is_risk": False,
        "risk_type": "SAFE",
        "category": "Irrelevant",
        "confidence_score": 0.0,
        "summary": "AI 分析暫時無法使用",
        "explanation": f"Gemini 呼叫失敗，請檢查 API Key 與網路。錯誤：{err_msg}",
        "sources": [],
    }


class AIService:
    """AI 分析服務類別（真實 Gemini 判定，失敗時回傳結構化 fallback）"""

    def __init__(self):
        """初始化 Gemini 客戶端；無 Key 或失敗時 _gemini_available=False"""
        self.use_new_api = USE_NEW_API
        self.model = None
        self.client = None
        self.model_name = settings.GEMINI_MODEL
        self._use_legacy_api = False
        self._gemini_available = False

        if not (settings.GOOGLE_API_KEY and settings.GOOGLE_API_KEY.strip()):
            print("⚠️ GOOGLE_API_KEY 未設定，AI 分析將回傳 fallback 結果")
            return

        if USE_NEW_API:
            try:
                self.client = genai.Client(api_key=settings.GOOGLE_API_KEY.strip())
                self._gemini_available = True
                print("✅ 使用新版 google-genai API")
            except Exception as e:
                print(f"⚠️ 新 API 初始化失敗: {e}，嘗試舊 API")
                try:
                    import google.generativeai as genai_old
                    genai_old.configure(api_key=settings.GOOGLE_API_KEY)
                    # 強制使用 gemini-2.5-flash，避免 .env 覆寫成 1.5 導致 404
                    self.model = genai_old.GenerativeModel(model_name="gemini-2.5-flash")
                    self.use_new_api = False
                    self._use_legacy_api = True
                    self._gemini_available = True
                    print("✅ 使用舊版 google-generativeai API")
                except Exception as e2:
                    print(f"⚠️ 舊 API 也失敗: {e2}")
        else:
            try:
                self.model = genai.GenerativeModel(
                    model_name="gemini-2.5-flash",
                    system_instruction=SYSTEM_PROMPT_V41,
                )
                self._gemini_available = True
            except TypeError:
                self.model = genai.GenerativeModel(model_name="gemini-2.5-flash")
                self._use_legacy_api = True
                self._gemini_available = True
    
    def analyze_content(
        self,
        content: str,
        url: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        真實 AI 判定：優先使用 REST API 直接呼叫 gemini-2.5-flash，繞過 SDK 預設。
        """
        if not self._gemini_available:
            return _default_fallback_result("未設定 GOOGLE_API_KEY 或 Gemini 初始化失敗")

        prompt = self._build_prompt(content, url, context)
        full_prompt = f"{SYSTEM_PROMPT_V41}\n\n---\n\n{prompt}"
        api_key = settings.GOOGLE_API_KEY.strip()

        # 僅使用 REST API（完全繞過 SDK，避免 gemini-1.5-flash 預設）
        last_err = ""
        if HAS_REQUESTS and api_key:
            for model in ["models/gemini-2.5-flash", "gemini-2.5-flash"]:
                result, err = self._call_gemini_rest(api_key, model, full_prompt)
                if result is not None:
                    return result
                last_err = err or ""

        return _default_fallback_result(last_err or "REST API 呼叫失敗，請檢查 API Key 與網路")

    def _call_gemini_rest(self, api_key: str, model: str, prompt: str) -> tuple:
        """直接呼叫 Gemini REST API。回傳 (result_dict, error_msg)，成功時 error_msg 為 None"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "topP": 0.95, "topK": 40, "maxOutputTokens": 2048},
        }
        try:
            r = requests.post(url, json=payload, timeout=60)
            r.raise_for_status()
            data = r.json()
            text = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )
            if not text or not text.strip():
                return None, f"{model}: 回傳無內容"
            text = text.replace("```json", "").replace("```", "").strip()
            result = json.loads(text)
            self._validate_result(result)
            return result, None
        except requests.exceptions.HTTPError as e:
            err_detail = (getattr(e.response, "text", None) or str(e))[:500]
            err_msg = f"{model} {e.response.status_code}: {err_detail}"
            print(f"⚠️ REST API: {err_msg}")
            return None, err_msg
        except Exception as e:
            err_msg = f"{model}: {str(e)}"
            print(f"⚠️ REST API 失敗: {err_msg}")
            return None, err_msg
    
    def _build_prompt(
        self,
        content: str,
        url: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        構建分析提示詞
        """
        prompt_parts = []
        
        if url:
            prompt_parts.append(f"【來源網址】\n{url}\n")
        
        prompt_parts.append(f"【待分析內容】\n{content}\n")
        
        if context:
            if 'similar_news' in context:
                prompt_parts.append("【相似新聞時間軸】\n")
                for news in context['similar_news']:
                    prompt_parts.append(f"- {news.get('title', '')} ({news.get('date', '')})")
                prompt_parts.append("")
        
        prompt_parts.append("請根據上述內容進行分析，並回傳標準 JSON 格式。")
        
        return "\n".join(prompt_parts)
    
    def _validate_result(self, result: Dict[str, Any]) -> None:
        """
        驗證 AI 結果格式
        """
        required_fields = ['is_risk', 'risk_type', 'category', 'confidence_score', 'summary', 'explanation', 'sources']
        
        for field in required_fields:
            if field not in result:
                raise ValueError(f"缺少必要欄位: {field}")
        
        # 驗證 risk_type（容許 UNKNOWN 等）
        allowed = ['SCAM', 'MISINFO', 'SAFE', 'UNKNOWN']
        if result['risk_type'] not in allowed:
            result['risk_type'] = 'SAFE'
    
    def generate_embedding(self, text: str) -> List[float]:
        try:
            if self.use_new_api and self.client:
                # 新版 SDK 語法
                res = self.client.models.embed_content(
                    model=settings.EMBEDDING_MODEL,
                    contents=text
                )
                return res.embeddings[0].values
            else:
                # 舊版 SDK 語法
                import google.generativeai as legacy_genai
                result = legacy_genai.embed_content(
                    model=settings.EMBEDDING_MODEL,
                    content=text,
                    task_type="retrieval_document"
                )
                return result['embedding']
        except Exception as e:
            print(f"⚠️ Embedding 生成失敗: {str(e)}")
            return [0.0] * settings.VECTOR_DIMENSION
    
    def analyze_image(self, image_path: str, url: Optional[str] = None) -> Dict[str, Any]:
        """
        分析圖片內容（OCR + 視覺分析）。
        優先使用 REST API 以支援 gemini-2.5-flash 多模態。
        """
        if not self._gemini_available:
            return _default_fallback_result("未啟用 Gemini，無法進行圖片分析")

        api_key = (settings.GOOGLE_API_KEY or "").strip()
        if not api_key or not HAS_REQUESTS:
            return _default_fallback_result("缺少 GOOGLE_API_KEY 或 requests")

        try:
            import base64
            with open(image_path, "rb") as f:
                img_b64 = base64.standard_b64encode(f.read()).decode()
            mime = "image/png"
            if image_path.lower().endswith((".jpg", ".jpeg")):
                mime = "image/jpeg"
            elif image_path.lower().endswith(".webp"):
                mime = "image/webp"
            elif image_path.lower().endswith(".gif"):
                mime = "image/gif"
        except Exception as e:
            return _default_fallback_result(f"無法讀取圖片: {e}")

        prompt = "請分析這張圖片中的內容。若圖片中有文字請 OCR。回傳標準 JSON（is_risk, risk_type, category, confidence_score, summary, explanation, sources）。"
        if url:
            prompt += f"\n來源網址: {url}"

        for model in ["models/gemini-2.5-flash", "gemini-2.5-flash"]:
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": mime, "data": img_b64}},
                    ]
                }],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048},
            }
            try:
                r = requests.post(api_url, json=payload, timeout=90)
                r.raise_for_status()
                data = r.json()
                text = (
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                )
                if not text or not text.strip():
                    continue
                text = text.replace("```json", "").replace("```", "").strip()
                result = json.loads(text)
                self._validate_result(result)
                return result
            except Exception:
                continue
        return _default_fallback_result("REST API 圖片分析失敗")

