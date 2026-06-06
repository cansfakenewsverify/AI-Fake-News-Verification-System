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
BINARY_PATH = os.path.join(DATA_DIR, "eval_binary.csv")     # 二分類 FP/FN
ERRORS_PATH = os.path.join(DATA_DIR, "eval_errors.csv")     # 判錯案例(錯誤分析)
CM_PATH = os.path.join(ASSETS_DIR, "confusion_matrix.png")


def _is_fallback(res: dict) -> bool:
    """API 失敗（額度/網路）時回傳的 fallback，不能當成有效預測。"""
    s = (res or {}).get("summary", "")
    return s.startswith("AI 分析暫時無法使用") or "服務異常" in s


def predict_one(ai: AIService, content: str, url: str | None):
    """回傳 (predicted_label 或 None, confidence, full_result)。None 代表本筆分析失敗。
    評測刻意關閉 web_search：省點數（便宜 3~7 倍）且結果更可重現。"""
    res = ai.analyze_content(content, url=url or None, use_web_search=False)
    if _is_fallback(res):
        return None, 0.0, res
    label = (res.get("risk_type") or "UNKNOWN").upper()
    conf = float(res.get("confidence_score") or 0.0)
    return label, conf, res


def _seed_to_db(store, ai, content: str, gold: str, res: dict):
    """把一筆「已驗證正確」的查證寫進 knowledge_base，建立可重用的事實查核快取。
    risk_type 一律用 gold（正確標籤），explanation 沿用 AI 產出的文字。"""
    from app.services.cache_service import CacheService
    cs = CacheService()
    h = cs.generate_hash(content)
    if store.find_by_hash(h):
        return False
    vec = ai.generate_embedding(content)          # CGU 向量（與分析點數不同池）
    record = dict(res)
    record["risk_type"] = gold                    # 以 gold 為準，確保快取標籤正確
    record["is_risk"] = (gold != "SAFE")
    store.save_record(
        data_type="TEXT", raw_content=content, content_hash=h,
        content_vector=vec or None, ai_result=record, source_url=None,
    )
    return True


def run_predictions(df: pd.DataFrame, delay: float, resume: bool, seed_db: bool = False) -> pd.DataFrame:
    ai = AIService()
    store = None
    if seed_db:
        from app.services.pandas_store import PandasStore
        store = PandasStore()
        print("[seed-db] 將把判對的案例寫入 knowledge_base 建立查證快取")

    done = {}
    if resume and os.path.exists(PRED_PATH):
        prev = pd.read_csv(PRED_PATH)
        done = {int(r.id): r for _, r in prev.iterrows()}
        print(f"[resume] 已載入 {len(done)} 筆先前結果")

    rows = []
    seeded = 0
    total = len(df)
    for i, row in df.iterrows():
        rid = int(row["id"])
        if rid in done:
            rows.append(done[rid].to_dict())
            continue

        content = str(row["content"])
        url = str(row["url"]) if "url" in df.columns and pd.notna(row.get("url")) else None
        pred, conf, res = predict_one(ai, content, url)

        gold = str(row["gold_label"]).upper()
        ok = (pred == gold)
        status = "OK" if pred else "ERROR(API)"

        # 只把「判對」的案例寫進資料庫，確保快取一致（標籤用 gold）
        if store is not None and ok:
            try:
                if _seed_to_db(store, ai, content, gold, res):
                    seeded += 1
            except Exception as e:
                print(f"   [seed-db] 寫入失敗: {e}")

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

    if store is not None:
        print(f"[seed-db] 已寫入知識庫 {seeded} 筆")

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

    # ── 二分類視角（風險 vs 安全）：給論文算偽陽性/偽陰性 ──
    def to_bin(x):
        return "SAFE" if x == "SAFE" else "RISK"
    yb_true = [to_bin(x) for x in y_true]
    yb_pred = [to_bin(x) for x in y_pred]
    bcm = confusion_matrix(yb_true, yb_pred, labels=["RISK", "SAFE"])
    tp, fn = int(bcm[0][0]), int(bcm[0][1])   # 真實有風險：判對 / 漏判(偽陰性)
    fp, tn = int(bcm[1][0]), int(bcm[1][1])   # 真實安全：誤判風險(偽陽性) / 判對
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0          # 偵測率(抓到多少真風險)
    spec = tn / (tn + fp) if (tn + fp) else 0.0         # 特異度
    fpr = fp / (fp + tn) if (fp + tn) else 0.0          # 偽陽性率(誤報)
    fnr = fn / (fn + tp) if (fn + tp) else 0.0          # 偽陰性率(漏報)
    print("\n  二分類（風險 vs 安全）— 偽陽性/偽陰性：")
    print(f"    TP={tp}  FP(偽陽性/誤報)={fp}  FN(偽陰性/漏報)={fn}  TN={tn}")
    print(f"    Precision={prec:.3f}  Recall={rec:.3f}  Specificity={spec:.3f}")
    print(f"    偽陽性率 FPR={fpr:.3f}  偽陰性率 FNR={fnr:.3f}")

    # 存二分類指標（論文用）
    pd.DataFrame([{
        "TP": tp, "FP_偽陽性": fp, "FN_偽陰性": fn, "TN": tn,
        "precision": round(prec, 3), "recall": round(rec, 3),
        "specificity": round(spec, 3), "FPR_偽陽性率": round(fpr, 3),
        "FNR_偽陰性率": round(fnr, 3),
    }]).to_csv(BINARY_PATH, index=False, encoding="utf-8-sig")
    print(f"  [v] 偽陽性/偽陰性指標已存：{BINARY_PATH}")

    # ── 判錯案例輸出（錯誤分析）──
    _save_error_cases(valid)

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


def _save_error_cases(valid: pd.DataFrame):
    """把判錯案例輸出成 CSV，標註偽陽性/偽陰性，供論文錯誤分析。"""
    wrong = valid[valid["gold"] != valid["pred"]].copy()
    if wrong.empty:
        print("  (無判錯案例)")
        return
    # 用 id 補回完整內容與備註
    try:
        src = pd.read_csv(DEFAULT_INPUT)[["id", "content", "note"]]
        wrong = wrong.drop(columns=[c for c in ["content"] if c in wrong.columns])
        wrong = wrong.merge(src, on="id", how="left")
    except Exception:
        pass

    def etype(r):
        if r["gold"] == "SAFE" and r["pred"] != "SAFE":
            return "偽陽性FP(安全被誤判為風險)"
        if r["gold"] != "SAFE" and r["pred"] == "SAFE":
            return "偽陰性FN(風險被誤判為安全)"
        return "類別混淆(風險類型判錯)"

    wrong["error_type"] = wrong.apply(etype, axis=1)
    cols = [c for c in ["id", "gold", "pred", "error_type", "confidence", "note", "content"] if c in wrong.columns]
    wrong[cols].to_csv(ERRORS_PATH, index=False, encoding="utf-8-sig")
    print(f"  [v] 判錯案例已存：{ERRORS_PATH}（{len(wrong)} 筆）")


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
    ap.add_argument("--seed-db", action="store_true",
                    help="把判對的案例寫入 knowledge_base，建立可重用的查證快取")
    ap.add_argument("--report-only", action="store_true",
                    help="只用現有 eval_predictions.csv 重算指標（不呼叫 AI、不花點數）")
    args = ap.parse_args()

    # 只重算報告：不呼叫任何 AI，零點數
    if args.report_only:
        if not os.path.exists(PRED_PATH):
            print(f"[ERR] 找不到 {PRED_PATH}，請先跑過一次評測")
            sys.exit(1)
        preds = pd.read_csv(PRED_PATH)
        preds["errored"] = preds["errored"].astype(bool)
        print(f"重算報告：{len(preds)} 筆（未呼叫 AI、零點數）\n")
        compute_metrics(preds)
        print("\n 報告重算完成。")
        return

    if not os.path.exists(args.input):
        print(f"[ERR] 找不到標註資料：{args.input}")
        sys.exit(1)

    df = pd.read_csv(args.input)
    if args.limit:
        df = df.head(args.limit)
    print(f"載入 {len(df)} 筆標註資料：{args.input}")
    print(f"（提醒：評測會呼叫真實 AI，請確認 .env 金鑰已設定且有額度/點數）\n")

    preds = run_predictions(df, delay=args.delay, resume=args.resume, seed_db=args.seed_db)
    compute_metrics(preds)
    print("\n 評測完成。")


if __name__ == "__main__":
    main()
