"""
AI 分析服務 — 支援 myai168 與 CGU AIR Gateway。

多引擎設計（最優效率 + 韌性）：
- myai168 Claude（/anthropic/v1/messages）：擅長細緻的假訊息/詐騙判斷
- myai168 OpenAI（/openai/v1/responses）：快、省點數
- CGU AIR Gateway（/cgullmapi/v1/responses）：OpenAI 相容新增選項，不取代原方案

其他能力：
- 圖片查證：Claude / OpenAI-compatible 視覺（OCR + 判讀，依模型支援度）
- 影片語音轉文字：/audio/transcriptions，無字幕時的後備
- Embedding：CGU AIR /embeddings 主，Gemini 備援
"""
import base64
import json
import os
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
   - **Phase A: 詐騙查核** (針對金錢/連結)：搜尋網域信譽、官方網址比對。
   - **Phase B: 假訊息查核** (針對健康/政治/舊聞)：
     - **務必優先參考**：台灣事實查核中心 (TFC)、MyGoPen、Cofacts、CNA中央社。
     - 檢查是否為「舊聞重炒」或「偽科學謠言」。

3. **短影音邏輯 (若來源為 TikTok/Reels)**：
   - 檢查語音是否誘導「點擊主頁連結 (Link in Bio)」(詐騙特徵)。
   - 檢查是否使用機器人語音傳播農場文 (假訊息特徵)。

4. **標準化摘要**：去除雜訊，保留人名、關鍵字、宣稱的後果 (如：帳戶凍結、會致癌)。

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
  "risk_type": (String, 詐騙填 "SCAM", 假訊息填 "MISINFO", 安全填 "SAFE"),
  "category": (String, 必須從上面的分類清單中選擇),
  "confidence_score": (Float, 0.0-1.0 代表信心程度),
  "summary": (String, 用於向量資料庫的高品質摘要),
  "explanation": (String, 白話解釋。若是假訊息，請指出「正確事實」是什麼),
  "sources": [
    {"title": (String, 來源標題), "url": (String, 只能引用實際查核到的真實 URL，嚴禁編造；無可靠來源則留空 [])}
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
    """多引擎 AI 分析服務（myai168 OpenAI/Claude + CGU AIR Gateway）。"""

    def __init__(self):
        self.myai_key = (settings.MYAI_API_KEY or "").strip()   # myai168 共用金鑰
        self.cgu_key = (settings.CGU_API_KEY or "").strip()     # CGU AIR Gateway 金鑰
        self.claude_base = (settings.CLAUDE_RELAY_URL or "").rstrip("/")
        self.openai_base = (settings.OPENAI_RELAY_URL or "").rstrip("/")
        self.cgu_base = (settings.CGU_BASE_URL or "").rstrip("/")
        self.claude_model = settings.CLAUDE_MODEL or "claude-opus-4-8"
        self.openai_model = settings.OPENAI_MODEL or "gpt-5"
        self.cgu_model = settings.CGU_MODEL or "gpt-5.4-mini"

        self.provider_available = {
            "openai": bool(self.myai_key and self.openai_base),
            "claude": bool(self.myai_key and self.claude_base),
            "cgu": bool(self.cgu_key and self.cgu_base),
        }
        self._available = any(self.provider_available.values())

        primary = (settings.AI_PROVIDER or "openai").lower()
        if primary not in ("openai", "claude", "cgu"):
            primary = "openai"
        # 主引擎優先，其他可用 provider 自動備援；不移除原本 myai168 方案。
        fallback_order = {
            "cgu": ["cgu", "openai", "claude"],
            "openai": ["openai", "claude", "cgu"],
            "claude": ["claude", "openai", "cgu"],
        }
        self.providers = [p for p in fallback_order[primary] if self.provider_available.get(p)]

        if not self._available:
            print("[AI] 未設定可用 AI provider 金鑰 / BASE_URL，AI 分析將回傳 fallback 結果")

    # ── 共用解析工具 ─────────────────────────────────────────────
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

    def _validate_result(self, result: Dict[str, Any]) -> None:
        for field in ["is_risk", "risk_type", "category", "confidence_score", "summary", "explanation", "sources"]:
            if field not in result:
                raise ValueError(f"缺少必要欄位: {field}")
        if result["risk_type"] not in ["SCAM", "MISINFO", "SAFE", "UNKNOWN"]:
            result["risk_type"] = "SAFE"

    # ── Claude 引擎 ──────────────────────────────────────────────
    def _claude_analyze(self, prompt_text: str, image: Optional[dict], use_web_search: bool) -> Dict[str, Any]:
        content: List[dict] = [{"type": "text", "text": prompt_text}]
        if image:
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": image["mime"], "data": image["b64"]},
            })
        body: Dict[str, Any] = {
            "model": self.claude_model,
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": content}],
        }
        # myai168 的 anthropic 中繼不支援 hosted 工具：web_search 帶了會 HTTP 400
        # (unsupported_tool)，故 claude 引擎一律不帶 web_search。
        # openai 引擎的 web_search 仍照常（見 _responses_analyze）。use_web_search 參數保留以維持簽名。
        _ = use_web_search
        headers = {"x-api-key": self.myai_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        r = requests.post(f"{self.claude_base}/messages", headers=headers, json=body, timeout=150)
        r.raise_for_status()
        data = r.json()
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        if not text.strip():
            raise ValueError("Claude 回傳無內容")
        result = self._parse_json_loose(text)
        self._validate_result(result)
        cites = self._claude_citations(data)
        if cites:
            result["sources"] = cites
        return result

    @staticmethod
    def _claude_citations(data: dict) -> List[Dict[str, str]]:
        sources, seen = [], set()
        for b in data.get("content", []) or []:
            if b.get("type") != "text":
                continue
            for c in b.get("citations", []) or []:
                u = c.get("url")
                if u and u not in seen:
                    seen.add(u)
                    sources.append({"title": c.get("title") or u, "url": u})
        return sources[:5]

    # ── OpenAI-compatible Responses 引擎 ─────────────────────────
    def _responses_analyze(
        self,
        provider_name: str,
        base_url: str,
        api_key: str,
        model: str,
        reasoning_effort: str,
        prompt_text: str,
        image: Optional[dict],
        use_web_search: bool,
    ) -> Dict[str, Any]:
        if image:
            input_payload: Any = [{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt_text},
                    {"type": "input_image", "image_url": f"data:{image['mime']};base64,{image['b64']}"},
                ],
            }]
        else:
            input_payload = prompt_text
        body: Dict[str, Any] = {
            "model": model,
            "input": input_payload,
            "max_output_tokens": 2000,
        }
        # gpt-5 推理強度：low/minimal 大幅加速並省點數（分類任務足夠）
        effort = (reasoning_effort or "").strip()
        if effort:
            body["reasoning"] = {"effort": effort}
        # gpt-5 的 minimal 推理模式不支援 web_search 工具(帶了會 HTTP 400)。
        # minimal 本就是省點數模式，跳過搜尋讓此 provider 維持可用，
        # 不必 fallback 到貴 10 倍的 claude。
        if use_web_search and effort != "minimal":
            body["tools"] = [{"type": "web_search"}]
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        r = requests.post(f"{base_url}/responses", headers=headers, json=body, timeout=150)
        r.raise_for_status()
        data = r.json()
        text = self._openai_output_text(data)
        if not text.strip():
            raise ValueError(f"{provider_name} 回傳無內容")
        result = self._parse_json_loose(text)
        self._validate_result(result)
        cites = self._openai_citations(data)
        if cites:
            result["sources"] = cites
        return result

    # ── myai168 OpenAI 引擎 ─────────────────────────────────────
    def _openai_analyze(self, prompt_text: str, image: Optional[dict], use_web_search: bool) -> Dict[str, Any]:
        return self._responses_analyze(
            provider_name="OpenAI",
            base_url=self.openai_base,
            api_key=self.myai_key,
            model=self.openai_model,
            reasoning_effort=settings.OPENAI_REASONING_EFFORT,
            prompt_text=prompt_text,
            image=image,
            use_web_search=use_web_search,
        )

    # ── CGU AIR Gateway 引擎（OpenAI 相容 Responses API）────────
    def _cgu_analyze(self, prompt_text: str, image: Optional[dict], use_web_search: bool) -> Dict[str, Any]:
        return self._responses_analyze(
            provider_name="CGU",
            base_url=self.cgu_base,
            api_key=self.cgu_key,
            model=self.cgu_model,
            reasoning_effort=settings.CGU_REASONING_EFFORT,
            prompt_text=prompt_text,
            image=image,
            use_web_search=use_web_search,
        )

    @staticmethod
    def _openai_output_text(data: dict) -> str:
        parts = []
        for item in data.get("output", []) or []:
            if item.get("type") == "message":
                for c in item.get("content", []) or []:
                    if c.get("type") == "output_text":
                        parts.append(c.get("text", "") or "")
        return "".join(parts)

    @staticmethod
    def _openai_citations(data: dict) -> List[Dict[str, str]]:
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

    # ── 引擎排程：主→備援，最後無工具再試一次 ───────────────────
    def _run_analysis(self, prompt_text: str, image: Optional[dict] = None, use_web_search: bool = True) -> Dict[str, Any]:
        last_err = ""
        for prov in self.providers:
            try:
                fn = {
                    "claude": self._claude_analyze,
                    "openai": self._openai_analyze,
                    "cgu": self._cgu_analyze,
                }[prov]
                return fn(prompt_text, image, use_web_search)
            except requests.exceptions.HTTPError as e:
                last_err = f"{prov} HTTP {getattr(e.response,'status_code','?')}: {(getattr(e.response,'text','') or '')[:160]}"
                print(f"[AI] {last_err}")
            except Exception as e:
                last_err = f"{prov}: {e}"
                print(f"[AI] {last_err}")
        # 最後手段：主引擎關閉 web_search 再試（避免搜尋雜訊導致 JSON 解析失敗）
        if use_web_search and self.providers:
            prov = self.providers[0]
            try:
                fn = {
                    "claude": self._claude_analyze,
                    "openai": self._openai_analyze,
                    "cgu": self._cgu_analyze,
                }[prov]
                return fn(prompt_text, image, False)
            except Exception as e:
                last_err = f"{prov}(no-search): {e}"
        return _default_fallback_result(last_err or "所有 AI 供應商皆失敗")

    # ── 對外：文字 / URL 分析 ────────────────────────────────────
    def analyze_content(self, content: str, url: Optional[str] = None,
                        context: Optional[Dict[str, Any]] = None,
                        use_web_search: Optional[bool] = None) -> Dict[str, Any]:
        if not self._available:
            return _default_fallback_result("未設定可用 AI provider 金鑰或中繼網址")
        # use_web_search=None → 依設定（USE_WEB_SEARCH）。web_search 每次貴 3~7 倍。
        if use_web_search is None:
            use_web_search = settings.USE_WEB_SEARCH
        prompt = self._build_prompt(content, url, context)
        full_prompt = f"{SYSTEM_PROMPT_V41}\n\n---\n\n{prompt}"
        return self._run_analysis(full_prompt, image=None, use_web_search=use_web_search)

    def _build_prompt(self, content: str, url: Optional[str] = None, context: Optional[Dict[str, Any]] = None) -> str:
        parts = []
        if url:
            parts.append(f"【來源網址】\n{url}\n")
        parts.append(f"【待分析內容】\n{content}\n")
        if context and context.get("similar_news"):
            parts.append("【網路事實查核與相關報導參考】")
            parts.append("以下為系統擷取的相關報導，如為假訊息請將查核文章的標題與網址放入 sources：\n")
            for news in context["similar_news"]:
                parts.append(f"- 標題：{news.get('title', '無標題')} ({news.get('date', '未知日期')})")
                parts.append(f"  網址：{news.get('url', '')}")
                if news.get("content"):
                    parts.append(f"  摘要：{news.get('content', '')[:150]}...")
            parts.append("")
        parts.append("請根據上述內容進行分析，並只回傳標準 JSON 格式。")
        return "\n".join(parts)

    # ── 對外：圖片分析（視覺 / OCR）──────────────────────────────
    def analyze_image(self, image_path: str, url: Optional[str] = None) -> Dict[str, Any]:
        if not self._available:
            return _default_fallback_result("未啟用 AI 服務，無法進行圖片分析")
        try:
            with open(image_path, "rb") as f:
                b64 = base64.standard_b64encode(f.read()).decode()
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
        full_prompt = f"{SYSTEM_PROMPT_V41}\n\n{instr}"
        # 圖片分析不開 web_search（穩定優先）
        return self._run_analysis(full_prompt, image={"b64": b64, "mime": mime}, use_web_search=False)

    # ── 對外：影片語音轉文字（whisper STT）──────────────────────
    def transcribe_audio(self, file_path: str) -> str:
        """把音訊檔轉成逐字稿（影片無字幕時的後備）。失敗回空字串。"""
        if not self._available or not os.path.isfile(file_path):
            return ""
        if self.provider_available.get("cgu") and (settings.AI_PROVIDER or "").lower() == "cgu":
            base = self.cgu_base
            key = self.cgu_key
            model = settings.CGU_STT_MODEL or settings.STT_MODEL
        else:
            base = self.openai_base if self.provider_available.get("openai") else self.cgu_base
            key = self.myai_key if self.provider_available.get("openai") else self.cgu_key
            model = settings.STT_MODEL if self.provider_available.get("openai") else settings.CGU_STT_MODEL
        try:
            with open(file_path, "rb") as f:
                r = requests.post(
                    f"{base}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {key}"},
                    files={"file": (os.path.basename(file_path), f, "audio/mpeg")},
                    data={"model": model, "language": "zh", "response_format": "json"},
                    timeout=180,
                )
            r.raise_for_status()
            return (r.json().get("text", "") or "").strip()
        except Exception as e:
            print(f"[AI] 語音轉文字失敗: {e}")
            return ""

    # ── 對外：Embedding（CGU LLM Gateway 主、Gemini 備援）────────
    def generate_embedding(self, text: str) -> List[float]:
        """
        產生文字向量供 Layer 2 語義快取使用。
        主：CGU LLM Gateway（OpenAI 相容 /embeddings）。
        備援：Gemini（若有 GOOGLE_API_KEY）。皆無則回傳空陣列（向量層自動停用）。
        """
        base = (settings.EMBED_RELAY_URL or "").rstrip("/")
        key = (settings.EMBED_API_KEY or settings.CGU_API_KEY or "").strip()
        if base and key:
            try:
                r = requests.post(
                    f"{base}/embeddings",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"model": settings.EMBED_MODEL, "input": text},
                    timeout=60,
                )
                r.raise_for_status()
                return list(r.json()["data"][0]["embedding"])
            except Exception as e:
                print(f"[AI] CGU embedding 失敗，改用後備：{e}")

        gkey = (settings.GOOGLE_API_KEY or "").strip()
        if gkey:
            try:
                from google import genai
                client = genai.Client(api_key=gkey)
                res = client.models.embed_content(model=settings.EMBEDDING_MODEL, contents=text)
                return list(res.embeddings[0].values)
            except Exception as e:
                print(f"[AI] Gemini embedding 失敗（向量層停用）：{e}")
        return []
