"""
AI 分析服務 — 透過學校的 OpenAI 相容中繼 API（myai168 Responses API）。

端點：POST {OPENAI_BASE_URL}/responses
- 文字查證：input 帶提示詞，並啟用 web_search 工具做即時佐證
- 圖片查證：input 帶 input_image（base64 data URL），支援視覺/OCR
- 來源引用：從回應的 url_citation annotations 取出真實網址

Embedding：學校中繼無 /embeddings 端點，故向量層改為「可選」——
若 .env 有 GOOGLE_API_KEY 則用 Gemini 產生向量，否則回傳空陣列（停用 Layer 2，
URL/Hash 兩層快取仍正常運作，不會誤命中）。
"""
import base64
import json
from typing import Dict, List, Optional, Any

import requests

from app.config import settings


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

2. **雙重事實查核 (可使用 web_search 工具)**：
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
你 **必須且只能** 回傳一個標準的 JSON 物件。不要使用 Markdown，不要加任何說明文字。

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
      "url": (String, 來源網址。⚠️ 只能引用你實際查核到的真實 URL，嚴禁編造；
        若無可靠來源，sources 必須留空 [])
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
        "explanation": f"AI 服務呼叫失敗，請檢查 API Key 與網路。錯誤：{err_msg}",
        "sources": [],
    }


class AIService:
    """AI 分析服務（學校 OpenAI 相容 Responses API）。"""

    def __init__(self):
        self.base_url = (settings.OPENAI_BASE_URL or "").rstrip("/")
        self.api_key = (settings.OPENAI_API_KEY or "").strip()
        self.model = settings.OPENAI_MODEL or "gpt-5"
        self._available = bool(self.base_url and self.api_key)
        if not self._available:
            print("⚠️ 未設定 OPENAI_API_KEY / OPENAI_BASE_URL，AI 分析將回傳 fallback 結果")

    # ── 內部：HTTP 與解析 ────────────────────────────────────────
    @property
    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _call_responses(self, input_payload: Any, use_web_search: bool = True, timeout: int = 120) -> dict:
        """呼叫 /responses，回傳原始 JSON dict（失敗會 raise）。"""
        body: Dict[str, Any] = {"model": self.model, "input": input_payload}
        if use_web_search:
            body["tools"] = [{"type": "web_search"}]
        r = requests.post(f"{self.base_url}/responses", headers=self._headers, json=body, timeout=timeout)
        r.raise_for_status()
        return r.json()

    @staticmethod
    def _extract_output_text(data: dict) -> str:
        """從 Responses API 的 output 陣列串接 message 的 output_text。"""
        parts = []
        for item in data.get("output", []) or []:
            if item.get("type") == "message":
                for c in item.get("content", []) or []:
                    if c.get("type") == "output_text":
                        parts.append(c.get("text", "") or "")
        return "".join(parts)

    @staticmethod
    def _extract_citations(data: dict) -> List[Dict[str, str]]:
        """從 web_search 的 url_citation annotations 取出真實來源網址。"""
        sources, seen = [], set()
        for item in data.get("output", []) or []:
            if item.get("type") != "message":
                continue
            for c in item.get("content", []) or []:
                for ann in c.get("annotations", []) or []:
                    if ann.get("type") == "url_citation":
                        u = ann.get("url")
                        if u and u not in seen:
                            seen.add(u)
                            sources.append({"title": ann.get("title") or u, "url": u})
        return sources[:5]

    @staticmethod
    def _parse_json_loose(text: str) -> Dict[str, Any]:
        """穩健解析 JSON：去掉 code fence，必要時擷取第一個 { 到最後一個 }。"""
        text = text.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(text)
        except Exception:
            start, end = text.find("{"), text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start:end + 1])
            raise

    # ── 對外：文字/URL 分析 ──────────────────────────────────────
    def analyze_content(
        self,
        content: str,
        url: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self._available:
            return _default_fallback_result("未設定 OPENAI_API_KEY 或 OPENAI_BASE_URL")

        prompt = self._build_prompt(content, url, context)
        full_prompt = f"{SYSTEM_PROMPT_V41}\n\n---\n\n{prompt}"

        last_err = ""
        # 先帶 web_search 即時佐證；若失敗（不支援/逾時）退回無工具再試一次
        for use_ws in (True, False):
            try:
                data = self._call_responses(full_prompt, use_web_search=use_ws)
                text = self._extract_output_text(data)
                if not text.strip():
                    last_err = "回傳無內容"
                    continue
                result = self._parse_json_loose(text)
                self._validate_result(result)
                cites = self._extract_citations(data)
                if cites:
                    result["sources"] = cites  # 用 web_search 的真實來源覆蓋
                return result
            except requests.exceptions.HTTPError as e:
                detail = (getattr(e.response, "text", None) or str(e))[:300]
                last_err = f"{e.response.status_code}: {detail}"
                print(f"⚠️ Responses API HTTP: {last_err}")
            except Exception as e:
                last_err = str(e)
                print(f"⚠️ Responses API 失敗: {last_err}")

        return _default_fallback_result(last_err or "Responses API 呼叫失敗")

    def _build_prompt(
        self,
        content: str,
        url: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """構建分析提示詞。"""
        prompt_parts = []
        if url:
            prompt_parts.append(f"【來源網址】\n{url}\n")
        prompt_parts.append(f"【待分析內容】\n{content}\n")

        if context and context.get("similar_news"):
            prompt_parts.append("【網路事實查核與相關報導參考】")
            prompt_parts.append("以下為系統擷取的相關報導，如為假訊息請將查核文章的標題與網址放入 sources：\n")
            for news in context["similar_news"]:
                prompt_parts.append(f"- 標題：{news.get('title', '無標題')} ({news.get('date', '未知日期')})")
                prompt_parts.append(f"  網址：{news.get('url', '')}")
                if news.get("content"):
                    prompt_parts.append(f"  摘要：{news.get('content', '')[:150]}...")
            prompt_parts.append("")

        prompt_parts.append("請根據上述內容進行分析，並只回傳標準 JSON 格式。")
        return "\n".join(prompt_parts)

    def _validate_result(self, result: Dict[str, Any]) -> None:
        """驗證 AI 結果格式，補正 risk_type。"""
        required = ["is_risk", "risk_type", "category", "confidence_score", "summary", "explanation", "sources"]
        for field in required:
            if field not in result:
                raise ValueError(f"缺少必要欄位: {field}")
        if result["risk_type"] not in ["SCAM", "MISINFO", "SAFE", "UNKNOWN"]:
            result["risk_type"] = "SAFE"

    # ── 對外：圖片分析（視覺 / OCR）──────────────────────────────
    def analyze_image(self, image_path: str, url: Optional[str] = None) -> Dict[str, Any]:
        if not self._available:
            return _default_fallback_result("未啟用 AI 服務，無法進行圖片分析")

        try:
            with open(image_path, "rb") as f:
                img_b64 = base64.standard_b64encode(f.read()).decode()
            mime = "image/png"
            low = image_path.lower()
            if low.endswith((".jpg", ".jpeg")):
                mime = "image/jpeg"
            elif low.endswith(".webp"):
                mime = "image/webp"
            elif low.endswith(".gif"):
                mime = "image/gif"
        except Exception as e:
            return _default_fallback_result(f"無法讀取圖片: {e}")

        instr = (
            "請分析這張圖片的內容，若圖片中有文字請先 OCR 再判斷。"
            "只回傳標準 JSON（is_risk, risk_type, category, confidence_score, summary, explanation, sources）。"
        )
        if url:
            instr += f"\n來源網址: {url}"

        input_payload = [{
            "role": "user",
            "content": [
                {"type": "input_text", "text": f"{SYSTEM_PROMPT_V41}\n\n{instr}"},
                {"type": "input_image", "image_url": f"data:{mime};base64,{img_b64}"},
            ],
        }]

        try:
            data = self._call_responses(input_payload, use_web_search=False)
            text = self._extract_output_text(data)
            if not text.strip():
                return _default_fallback_result("圖片分析回傳無內容")
            result = self._parse_json_loose(text)
            self._validate_result(result)
            return result
        except Exception as e:
            return _default_fallback_result(f"圖片分析失敗: {e}")

    # ── 對外：Embedding（可選；學校 API 無此端點）────────────────
    def generate_embedding(self, text: str) -> List[float]:
        """
        學校中繼無 /embeddings 端點。
        若 .env 設了 GOOGLE_API_KEY，仍可用 Gemini 產生向量以啟用 Layer 2 語義快取；
        否則回傳空陣列（向量層自動停用，URL/Hash 快取不受影響）。
        """
        gkey = (settings.GOOGLE_API_KEY or "").strip()
        if not gkey:
            return []
        try:
            from google import genai
            client = genai.Client(api_key=gkey)
            res = client.models.embed_content(model=settings.EMBEDDING_MODEL, contents=text)
            return list(res.embeddings[0].values)
        except Exception:
            try:
                import google.generativeai as legacy_genai
                legacy_genai.configure(api_key=gkey)
                result = legacy_genai.embed_content(
                    model=settings.EMBEDDING_MODEL, content=text, task_type="retrieval_document"
                )
                return list(result["embedding"])
            except Exception as e:
                print(f"⚠️ Embedding 產生失敗（向量層停用）：{e}")
                return []
