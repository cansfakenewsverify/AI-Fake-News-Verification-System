from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.services.ai_service import AIService


@dataclass(frozen=True)
class AnalysisResult:
    frame_type: Optional[str]
    frame_label: Optional[str]
    is_risk: bool
    risk_type: str
    category: str
    confidence_score: float
    summary: str
    explanation: str
    sources: list
    raw: Dict[str, Any]


class AIClient:
    """
    給其他系統使用的 AI 分析封裝介面。
    """

    def __init__(self) -> None:
        self._svc = AIService()

    def analyze_text(self, content: str, url: Optional[str] = None, context: Optional[Dict[str, Any]] = None) -> AnalysisResult:
        d = self._svc.analyze_content(content, url=url, context=context)
        return self._to_result(d)

    def analyze_image(self, image_path: str, url: Optional[str] = None) -> AnalysisResult:
        d = self._svc.analyze_image(image_path, url=url)
        return self._to_result(d)

    @staticmethod
    def _to_result(d: Dict[str, Any]) -> AnalysisResult:
        return AnalysisResult(
            frame_type=d.get("frame_type"),
            frame_label=d.get("frame_label"),
            is_risk=bool(d.get("is_risk", False)),
            risk_type=str(d.get("risk_type", "SAFE")),
            category=str(d.get("category", "Irrelevant")),
            confidence_score=float(d.get("confidence_score", 0.0) or 0.0),
            summary=str(d.get("summary", "") or ""),
            explanation=str(d.get("explanation", "") or ""),
            sources=d.get("sources", []) or [],
            raw=d,
        )

