"""
評測腳本 — 量化判定引擎的效能（FP/FN、混淆矩陣、accuracy、precision/recall/F1）。

這是論文「系統有效性」的核心數據來源。

用法：
    # 先確認 .env 內 GOOGLE_API_KEY 已設定（評測一定要呼叫真實 AI）
    python scripts/evaluate.py                       # 跑完整 data/eval_set.csv
    python scripts/evaluate.py --limit 10            # 只跑前 10 筆（測試用）
    python scripts/evaluate.py --delay 3             # 每筆間隔 3 秒（避開 API 限流）
    python scripts/evaluate.py --resume              # 從上次中斷處續跑

產出：
    data/eval_predictions.csv   每筆的 gold / pred / confidence / 是否正確
    data/eval_report.csv        每類 precision / recall / f1 + 整體 accuracy
    assets/confusion_matrix.png 混淆矩陣熱力圖（沒有 matplotlib 時改印文字版）
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from app.services.ai_service import AIService

LABELS = ["SCAM", "MISINFO", "SAFE"]

# 路徑（相對 factcheck_system 根目錄）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
ASSETS_DIR = os.path.normpath(os.path.join(ROOT, "..", "..", "..", "assets"))
DEFAULT_INPUT = os.path.join(DATA_DIR, "eval_set.csv")
PRED_PATH = os.path.join(DATA_DIR, "eval_predictions.csv")
REPORT_PATH = os.path.join(DATA_DIR, "eval_report.csv")
CM_PATH = os.path.join(ASSETS_DIR, "confusion_matrix.png")


def _is_fallback(res: dict) -> bool:
    """API 失敗（額度/網路）時回傳的 fallback，不能當成有效預測。"""
    s = (res or {}).get("summary", "")
    return s.startswith("AI 分析暫時無法使用") or "服務異常" in s


def predict_one(ai: AIService, content: str, url: str | None):
    """回傳 (predicted_label 或 None, confidence)。None 代表本筆分析失敗。"""
    res = ai.analyze_content(content, url=url or None)
    if _is_fallback(res):
        return None, 0.0
    label = (res.get("risk_type") or "UNKNOWN").upper()
    conf = float(res.get("confidence_score") or 0.0)
    return label, conf


def run_predictions(df: pd.DataFrame, delay: float, resume: bool) -> pd.DataFrame:
    ai = AIService()
    done = {}
    if resume and os.path.exists(PRED_PATH):
        prev = pd.read_csv(PRED_PATH)
        done = {int(r.id): r for _, r in prev.iterrows()}
        print(f"[resume] 已載入 {len(done)} 筆先前結果")

    rows = []
    total = len(df)
    for i, row in df.iterrows():
        rid = int(row["id"])
        if rid in done:
            rows.append(done[rid].to_dict())
            continue

        content = str(row["content"])
        url = str(row["url"]) if "url" in df.columns and pd.notna(row.get("url")) else None
        pred, conf = predict_one(ai, content, url)

        gold = str(row["gold_label"]).upper()
        ok = (pred == gold)
        status = "OK" if pred else "ERROR(API)"
        print(f"[{i + 1}/{total}] id={rid} gold={gold:7} pred={str(pred):7} "
              f"conf={conf:.2f} {'[v]' if ok else '[x]'} {status}")

        rows.append({
            "id": rid, "gold": gold, "pred": pred if pred else "",
            "confidence": conf, "correct": ok,
            "errored": pred is None, "content": content[:80],
        })
        # 邊跑邊存，跑壞也不會全部重來
        pd.DataFrame(rows).to_csv(PRED_PATH, index=False, encoding="utf-8-sig")
        if delay and i + 1 < total:
            time.sleep(delay)

    return pd.DataFrame(rows)


def compute_metrics(preds: pd.DataFrame):
    try:
        from sklearn.metrics import (
            confusion_matrix, classification_report, accuracy_score,
        )
    except ImportError:
        print("\n[!] 未安裝 scikit-learn，無法計算指標。請先：pip install scikit-learn")
        return

    valid = preds[~preds["errored"]].copy()
    errored = int(preds["errored"].sum())
    if valid.empty:
        print(f"\n[!] 全部 {errored} 筆都分析失敗（多半是 API 額度/金鑰問題），無法評測。")
        return

    y_true = valid["gold"].tolist()
    y_pred = valid["pred"].tolist()

    acc = accuracy_score(y_true, y_pred)
    report = classification_report(
        y_true, y_pred, labels=LABELS, digits=3, zero_division=0, output_dict=True
    )
    cm = confusion_matrix(y_true, y_pred, labels=LABELS)

    # ── 主控台輸出 ──
    print("\n" + "=" * 56)
    print(f"  評測結果（有效 {len(valid)} 筆，分析失敗 {errored} 筆）")
    print("=" * 56)
    print(f"  整體準確率 Accuracy : {acc:.3f}")
    print(f"  Macro-F1           : {report['macro avg']['f1-score']:.3f}")
    print("\n  各類別 Precision / Recall / F1：")
    for lab in LABELS:
        r = report[lab]
        print(f"    {lab:8}  P={r['precision']:.3f}  R={r['recall']:.3f}  "
              f"F1={r['f1-score']:.3f}  (n={int(r['support'])})")

    print("\n  混淆矩陣（列=真實，欄=預測）：")
    header = "          " + "".join(f"{l:>9}" for l in LABELS)
    print(header)
    for i, lab in enumerate(LABELS):
        print(f"    {lab:8}" + "".join(f"{cm[i][j]:>9}" for j in range(len(LABELS))))

    # ── 二分類視角（風險 vs 安全）：給論文算 FP/FN ──
    def to_bin(x):
        return "SAFE" if x == "SAFE" else "RISK"
    yb_true = [to_bin(x) for x in y_true]
    yb_pred = [to_bin(x) for x in y_pred]
    bcm = confusion_matrix(yb_true, yb_pred, labels=["RISK", "SAFE"])
    tp, fn = bcm[0][0], bcm[0][1]      # 真實有風險
    fp, tn = bcm[1][0], bcm[1][1]      # 真實安全
    print("\n  二分類（風險 vs 安全）：")
    print(f"    TP={tp}  FP={fp}  FN={fn}  TN={tn}")
    if tp + fp:
        print(f"    Precision={tp / (tp + fp):.3f}  ", end="")
    if tp + fn:
        print(f"Recall={tp / (tp + fn):.3f}  ", end="")
    if tn + fp:
        print(f"Specificity={tn / (tn + fp):.3f}")

    # ── 存報告 CSV ──
    rep_rows = []
    for lab in LABELS:
        r = report[lab]
        rep_rows.append({
            "label": lab, "precision": round(r["precision"], 3),
            "recall": round(r["recall"], 3), "f1": round(r["f1-score"], 3),
            "support": int(r["support"]),
        })
    rep_rows.append({"label": "accuracy", "precision": "", "recall": "",
                     "f1": round(acc, 3), "support": len(valid)})
    rep_rows.append({"label": "macro_avg", "precision": round(report["macro avg"]["precision"], 3),
                     "recall": round(report["macro avg"]["recall"], 3),
                     "f1": round(report["macro avg"]["f1-score"], 3), "support": len(valid)})
    pd.DataFrame(rep_rows).to_csv(REPORT_PATH, index=False, encoding="utf-8-sig")
    print(f"\n  [v] 報告已存：{REPORT_PATH}")

    _save_confusion_png(cm)


def _save_confusion_png(cm):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        try:
            import seaborn as sns
            HAS_SNS = True
        except ImportError:
            HAS_SNS = False
    except ImportError:
        print("  [!] 未安裝 matplotlib，略過產生混淆矩陣圖")
        return

    # 中文字型（Windows 微軟正黑體；找不到就用預設）
    for font in ["Microsoft JhengHei", "Microsoft YaHei", "PingFang TC", "SimHei"]:
        try:
            matplotlib.rcParams["font.sans-serif"] = [font]
            matplotlib.rcParams["axes.unicode_minus"] = False
            break
        except Exception:
            continue

    os.makedirs(ASSETS_DIR, exist_ok=True)
    fig, ax = plt.subplots(figsize=(5.5, 4.5))
    if HAS_SNS:
        sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
                    xticklabels=LABELS, yticklabels=LABELS, ax=ax, cbar=True)
    else:
        im = ax.imshow(cm, cmap="Blues")
        ax.set_xticks(range(len(LABELS))); ax.set_xticklabels(LABELS)
        ax.set_yticks(range(len(LABELS))); ax.set_yticklabels(LABELS)
        for i in range(len(LABELS)):
            for j in range(len(LABELS)):
                ax.text(j, i, cm[i][j], ha="center", va="center")
        fig.colorbar(im)
    ax.set_xlabel("預測 Predicted")
    ax.set_ylabel("真實 Actual")
    ax.set_title("混淆矩陣 Confusion Matrix")
    fig.tight_layout()
    fig.savefig(CM_PATH, dpi=150)
    print(f"  [v] 混淆矩陣圖已存：{CM_PATH}")


def main():
    ap = argparse.ArgumentParser(description="判定引擎評測")
    ap.add_argument("--input", default=DEFAULT_INPUT, help="標註資料 CSV")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 筆（0=全部）")
    ap.add_argument("--delay", type=float, default=2.0, help="每筆間隔秒數（避免限流）")
    ap.add_argument("--resume", action="store_true", help="從上次中斷處續跑")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"[ERR] 找不到標註資料：{args.input}")
        sys.exit(1)

    df = pd.read_csv(args.input)
    if args.limit:
        df = df.head(args.limit)
    print(f"載入 {len(df)} 筆標註資料：{args.input}")
    print(f"（提醒：評測會呼叫真實 Gemini，請確認 .env 的 GOOGLE_API_KEY 已設定且有額度）\n")

    preds = run_predictions(df, delay=args.delay, resume=args.resume)
    compute_metrics(preds)
    print("\n 評測完成。")


if __name__ == "__main__":
    main()
