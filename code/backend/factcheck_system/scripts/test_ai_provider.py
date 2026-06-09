"""
低成本測試目前 AI_PROVIDER 是否能正常呼叫。

用法：
    python scripts/test_ai_provider.py
    python scripts/test_ai_provider.py --provider cgu
    python scripts/test_ai_provider.py --skip-embedding
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.services.ai_service import AIService


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["openai", "claude", "cgu"], default="")
    parser.add_argument("--skip-embedding", action="store_true")
    args = parser.parse_args()

    if args.provider:
        os.environ["AI_PROVIDER"] = args.provider
        settings.AI_PROVIDER = args.provider

    provider = (settings.AI_PROVIDER or "openai").lower()
    print(f"[test] AI_PROVIDER={provider}")

    ai = AIService()
    print(f"[test] provider order={ai.providers}")
    if not ai.providers:
        raise SystemExit("[x] 沒有可用 provider，請檢查 .env 的 API key / BASE_URL")

    result = ai.analyze_content(
        "這是一則 API 測試訊息：請判斷它是安全的系統測試，不是詐騙或假訊息。",
        use_web_search=False,
    )
    print("[test] analyze result:")
    print(result)
    if result.get("summary", "").startswith("AI 分析暫時無法使用"):
        raise SystemExit("[x] AI 分析失敗")
    if result.get("risk_type") not in {"SCAM", "MISINFO", "SAFE", "UNKNOWN"}:
        raise SystemExit("[x] 回傳 JSON 格式不符合預期")

    if not args.skip_embedding:
        vec = ai.generate_embedding("CGU embedding smoke test")
        print(f"[test] embedding dim={len(vec)}")
        if not vec:
            raise SystemExit("[x] embedding 失敗或未設定 EMBED_API_KEY / CGU_API_KEY")

    print("[v] AI provider 測試完成")


if __name__ == "__main__":
    main()
