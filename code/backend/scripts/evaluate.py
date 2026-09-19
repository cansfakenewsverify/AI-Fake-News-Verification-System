"""
評測腳本 — 量化判定引擎的效能（FP/FN、混淆矩陣、accuracy、precision/recall/F1）。

這是論文「系統有效性」的核心數據來源。

用法：
    # 先確認 .env 內 AI provider 金鑰（如 CGU_API_KEY）已設定（評測一定要呼叫真實 AI）
    python scripts/evaluate.py                       # 跑完整 data/eval_set.csv
    python scripts/evaluate.py --limit 10            # 只跑前 10 筆（測試用）
    python scripts/evaluate.py --delay 3             # 每筆間隔 3 秒（避開 API 限流）
    python scripts/evaluate.py --resume              # 從上次中斷處續跑
    python scripts/evaluate.py --timing --delay 0    # 量測每筆 AI 呼叫耗時（PF-1 未命中 p50/p90）
    python scripts/evaluate.py --report-only         # 只用現有預測檔重算報告（不呼叫 AI、零點數）

產出：
    data/eval_predictions.csv   每筆的 gold / pred / confidence / 是否正確，
                                另記 elapsed_ms（加 --timing 才有值）/ provider / model / date / use_web_search
    data/eval_report.csv        每類 precision / recall / f1 + 整體 accuracy，
                                每列附 provider / model / date / use_web_search / elapsed_ms_p50 / _p90 / _n
    assets/confusion_matrix.png 混淆矩陣熱力圖（沒有 matplotlib 時改印文字版）

報告的執行條件與延遲統計一律取自 eval_predictions.csv 的逐筆欄位（不讀現在的設定、不取現在的時間），
所以 --report-only 重算出來的檔案與原檔逐位元相同。
"""
import argparse
import os
import sys
import time
from datetime import date as _date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

from app.services.ai_service import AIService
from app.utils.verdict import is_fallback

LABELS = ["SCAM", "MISINFO", "SAFE"]

# 評測一律關閉 web_search：省點數（便宜 3~7 倍）且結果更可重現。
# predict_one 傳給 AI 的值與報告的 use_web_search 欄讀同一個常數，兩者不會各說各話。
EVAL_USE_WEB_SEARCH = False

# eval_predictions.csv 的欄位順序。後五欄為 B-23 新增；舊預測檔沒有這些欄，讀進來一律當缺值。
PRED_COLUMNS = [
    "id", "gold", "pred", "confidence", "correct", "errored", "content",
    "elapsed_ms", "provider", "model", "date", "use_web_search",
]
META_COLUMNS = ["provider", "model", "date", "use_web_search"]

# 路徑（相對 backend 根目錄）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
ASSETS_DIR = os.path.normpath(os.path.join(ROOT, "..", "..", "assets"))
DEFAULT_INPUT = os.path.join(DATA_DIR, "eval_set.csv")
PRED_PATH = os.path.join(DATA_DIR, "eval_predictions.csv")
REPORT_PATH = os.path.join(DATA_DIR, "eval_report.csv")
BINARY_PATH = os.path.join(DATA_DIR, "eval_binary.csv")     # 二分類 FP/FN
ERRORS_PATH = os.path.join(DATA_DIR, "eval_errors.csv")     # 判錯案例(錯誤分析)
CM_PATH = os.path.join(ASSETS_DIR, "confusion_matrix.png")


def _today() -> str:
    """評測執行日（本機日期）。只有真的呼叫 AI 的那次執行會取；--report-only 不取現在時間。"""
    return _date.today().isoformat()


def predict_one(ai: AIService, content: str, url: str | None, timing: bool = False):
    """回傳 (predicted_label 或 None, confidence, full_result, elapsed_ms 或 None)。
    label 為 None 代表本筆分析失敗。評測刻意關閉 web_search（見 EVAL_USE_WEB_SEARCH）。
    timing=True 時以 time.perf_counter 只包住 analyze_content（不含 --delay 的等待與 --seed-db 的寫入），
    取整數毫秒，與後端結構化 log 的 elapsed_ms 同單位。"""
    started = time.perf_counter() if timing else None
    res = ai.analyze_content(content, url=url or None, use_web_search=EVAL_USE_WEB_SEARCH)
    elapsed_ms = int(round((time.perf_counter() - started) * 1000)) if timing else None
    if is_fallback(res):  # API 失敗（額度/網路）的 fallback 不能當成有效預測
        return None, 0.0, res, elapsed_ms
    label = (res.get("risk_type") or "UNKNOWN").upper()
    conf = float(res.get("confidence_score") or 0.0)
    return label, conf, res, elapsed_ms


def _engine_of(ai, res) -> tuple[str, str]:
    """本筆實際回應的 (provider, model)：AIService 會寫進結果（備援接手時不是主引擎）。
    fallback 結果沒有這兩個鍵，退回 AIService 設定的主引擎。"""
    res = res if isinstance(res, dict) else {}
    provider = str(res.get("provider") or "").strip()
    model = str(res.get("model") or "").strip()
    if not provider:
        chain = list(getattr(ai, "providers", None) or [])
        provider = str(chain[0]) if chain else ""
    if not model and provider:
        model = str(getattr(ai, f"{provider}_model", "") or "")
    return provider, model


def _predictions_frame(rows: list) -> pd.DataFrame:
    """預測列 → 固定欄位順序的 DataFrame（舊檔續跑缺的欄補空值）。
    elapsed_ms 以可為空的整數存檔：沒量到的列（未加 --timing、或舊檔的列）留空，不寫 0。"""
    out = pd.DataFrame(rows, columns=PRED_COLUMNS)
    out["elapsed_ms"] = pd.to_numeric(out["elapsed_ms"], errors="coerce").round().astype("Int64")
    return out


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
        label_source="gold",                      # 評測標註＝確定性標記 → 寫入即 verified（FR-17）
    )
    return True


def run_predictions(df: pd.DataFrame, delay: float, resume: bool, seed_db: bool = False,
                    timing: bool = False) -> pd.DataFrame:
    ai = AIService()
    run_date = _today()                           # 整次執行只取一次：跨午夜也只記開跑那天
    store = None
    if seed_db:
        # 本機 PandasStore；STORAGE_BACKEND=supabase 時寫進雲端知識庫（介面相同）
        from app.services.store_factory import get_knowledge_store
        store = get_knowledge_store()
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
        pred, conf, res, elapsed_ms = predict_one(ai, content, url, timing=timing)
        provider, model = _engine_of(ai, res)

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

        took = f" {elapsed_ms}ms" if elapsed_ms is not None else ""
        print(f"[{i + 1}/{total}] id={rid} gold={gold:7} pred={str(pred):7} "
              f"conf={conf:.2f} {'[v]' if ok else '[x]'} {status}{took}")

        rows.append({
            "id": rid, "gold": gold, "pred": pred if pred else "",
            "confidence": conf, "correct": ok,
            "errored": pred is None, "content": content[:80],
            "elapsed_ms": elapsed_ms,
            "provider": provider, "model": model,
            "date": run_date, "use_web_search": EVAL_USE_WEB_SEARCH,
        })
        # 邊跑邊存，跑壞也不會全部重來
        _predictions_frame(rows).to_csv(PRED_PATH, index=False, encoding="utf-8-sig")
        if delay and i + 1 < total:
            time.sleep(delay)

    if store is not None:
        print(f"[seed-db] 已寫入知識庫 {seeded} 筆")

    return _predictions_frame(rows)


def _is_blank(value) -> bool:
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip() == ""


def run_metadata(valid: pd.DataFrame) -> dict:
    """報告用的執行條件（provider / model / date / use_web_search），只看有效預測列。
    全部取自預測檔 → --report-only 重算與原檔一致。同一欄有多個值（備援接手、分兩天續跑）以 | 連接；
    部分列沒有紀錄（舊預測檔續跑）時另加 unknown，不假裝整批同一條件；全部沒有紀錄則留空。"""
    meta = {}
    for col in META_COLUMNS:
        seen = set()
        if col in valid.columns:
            seen = {"" if _is_blank(v) else str(v).strip() for v in valid[col].tolist()}
        known = sorted(v for v in seen if v)
        if known and "" in seen:
            known.append("unknown")
        meta[col] = "|".join(known)
    return meta


def timing_summary(valid: pd.DataFrame) -> dict:
    """有效預測列（非 fallback）的 elapsed_ms 統計。百分位用 numpy.percentile（線性內插），
    與 docs/test 其他績效數字同一算法。沒有任何計時紀錄時 n=0、p50/p90 留空。"""
    ms = np.array([], dtype=float)
    if "elapsed_ms" in valid.columns:
        ms = pd.to_numeric(valid["elapsed_ms"], errors="coerce").dropna().astype(float).to_numpy()
    if ms.size == 0:
        return {"elapsed_ms_p50": "", "elapsed_ms_p90": "", "elapsed_ms_n": 0}
    p50, p90 = np.percentile(ms, [50, 90])
    return {
        "elapsed_ms_p50": round(float(p50), 1),
        "elapsed_ms_p90": round(float(p90), 1),
        "elapsed_ms_n": int(ms.size),
    }


def compute_metrics(preds: pd.DataFrame, timing: bool = False):
    """timing 只影響主控台提示（要求了計時卻沒有紀錄時提醒）；寫出的檔案內容只由 preds 決定。"""
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
    # 每列附上執行條件與延遲統計（新舊模型的報告並列時，每一列都認得出是哪一次評測）
    meta = run_metadata(valid)
    stats = timing_summary(valid)
    for rep_row in rep_rows:
        rep_row.update(meta)
        rep_row.update(stats)
    pd.DataFrame(rep_rows).to_csv(REPORT_PATH, index=False, encoding="utf-8-sig")
    print(f"\n  [v] 報告已存：{REPORT_PATH}")

    _save_confusion_png(cm)

    # ── 報告尾端：執行條件 + 逐筆延遲 p50 / p90（PF-1 未命中）──
    print("\n  執行條件（取自預測檔）：")
    print("    " + "  ".join(f"{col}={meta[col] or '-'}" for col in META_COLUMNS))
    if stats["elapsed_ms_n"]:
        p50, p90 = stats["elapsed_ms_p50"], stats["elapsed_ms_p90"]
        print(f"  逐筆延遲 elapsed_ms（只計非 fallback 的 {stats['elapsed_ms_n']} 筆）：")
        print(f"    p50 = {p50:.1f} ms ({p50 / 1000:.2f} s)   p90 = {p90:.1f} ms ({p90 / 1000:.2f} s)")
    elif timing:
        print("  [!] 預測檔沒有可統計的 elapsed_ms：請以 --timing 重跑評測（會呼叫 AI、花點數）")


def _save_error_cases(valid: pd.DataFrame):
    """把判錯案例輸出成 CSV，標註偽陽性/偽陰性，供論文錯誤分析。"""
    wrong = valid[valid["gold"] != valid["pred"]].copy()
    if wrong.empty:
        # 仍要覆寫成只有表頭的空檔，否則會留下上一次評測的舊錯誤案例
        pd.DataFrame(columns=["id", "gold", "pred", "error_type", "confidence", "note", "content"]).to_csv(
            ERRORS_PATH, index=False, encoding="utf-8-sig")
        print(f"  (無判錯案例，已清空 {ERRORS_PATH})")
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
    ap.add_argument("--timing", action="store_true",
                    help="量測每筆 AI 呼叫的 elapsed_ms（毫秒）寫入 eval_predictions.csv，"
                         "報告尾端印出 p50/p90（只計非 fallback 的列）")
    args = ap.parse_args()

    # 只重算報告：不呼叫任何 AI，零點數（執行條件與 elapsed_ms 沿用預測檔內的紀錄）
    if args.report_only:
        if not os.path.exists(PRED_PATH):
            print(f"[ERR] 找不到 {PRED_PATH}，請先跑過一次評測")
            sys.exit(1)
        preds = pd.read_csv(PRED_PATH)
        preds["errored"] = preds["errored"].astype(bool)
        print(f"重算報告：{len(preds)} 筆（未呼叫 AI、零點數）\n")
        compute_metrics(preds, timing=args.timing)
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

    preds = run_predictions(df, delay=args.delay, resume=args.resume, seed_db=args.seed_db,
                            timing=args.timing)
    compute_metrics(preds, timing=args.timing)
    print("\n 評測完成。")


if __name__ == "__main__":
    main()
