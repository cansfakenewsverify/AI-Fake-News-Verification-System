"""
Threads 查核機器人低成本測試。

用法：
    venv\\Scripts\\python scripts\\test_threads_bot.py            # 乾跑：檢查設定 + 產生範例回覆
    venv\\Scripts\\python scripts\\test_threads_bot.py --live     # 有 token 時：驗證憑證 + 列出 mentions
    venv\\Scripts\\python scripts\\test_threads_bot.py --poll     # 真的跑一輪輪詢（會回覆貼文、花 AI 點數！）

注意：主控台是 cp950，範例回覆文字會寫進 data/threads_reply_sample.txt（UTF-8）。
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.services.threads_service import ThreadsService, format_verdict_reply


SAMPLE_RESULT = {
    "risk_type": "SCAM",
    "confidence_level": "高",
    "summary": "假冒銀行的釣魚簡訊，誘導點擊連結輸入帳號密碼。",
    "explanation": "此訊息宣稱帳戶異常要求立即點擊連結驗證，符合釣魚詐騙典型話術；"
                   "銀行不會以簡訊要求輸入帳密。",
    "sources": [{"title": "165 反詐騙", "url": "https://165.npa.gov.tw/"}],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="用真 token 驗證憑證與 mentions 讀取")
    ap.add_argument("--poll", action="store_true", help="真的跑一輪輪詢（會發文、花點數）")
    args = ap.parse_args()

    svc = ThreadsService()
    print(f"[test] ENABLE_THREADS_BOT = {settings.ENABLE_THREADS_BOT}")
    print(f"[test] token 已設定      = {bool(svc.token)}")
    print(f"[test] user_id 已設定    = {bool(svc.user_id)}")
    print(f"[test] poll 間隔         = {settings.THREADS_POLL_MINUTES} 分鐘")

    # 乾跑：驗證回覆格式（寫檔避免 cp950 印不出）
    reply = format_verdict_reply(SAMPLE_RESULT)
    out = os.path.join("data", "threads_reply_sample.txt")
    os.makedirs("data", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(reply)
    print(f"[test] 範例回覆已寫入 {out}（長度 {len(reply)} 字，上限 500）")
    assert len(reply) <= 500

    if args.live or args.poll:
        if not svc.available:
            print("[test] 未設定 THREADS_ACCESS_TOKEN / THREADS_USER_ID，無法 live 測試")
            sys.exit(1)
        try:
            me = svc.get_profile()
            print(f"[test] 憑證 OK：id={me.get('id')} username={me.get('username')}")
            mentions = svc.get_mentions(limit=5)
            print(f"[test] 最近 mentions：{len(mentions)} 筆")
        except Exception as e:
            print(f"[test] Threads API 呼叫失敗：{e}")
            sys.exit(1)

    if args.poll:
        from app.workers.threads_bot import run_threads_poll
        stats = asyncio.run(run_threads_poll())
        print(f"[test] 輪詢結果：{stats}")


if __name__ == "__main__":
    main()
