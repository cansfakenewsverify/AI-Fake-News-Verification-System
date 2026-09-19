"""B-23：evaluate.py 的 --timing、報告的執行條件欄位、--seed-db 的 gold 標記（QA-2／PF-1 前置）。

全離線、零點數：AIService 換成假物件，時鐘換成假時鐘（不真的 sleep），所有輸出路徑導到 tmp_path，
requests 被封鎖。data/eval_*.csv 與 assets/confusion_matrix.png 不會被動到（模組結束時會核對）。
"""
import hashlib
import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

from app.services.ai_service import _default_fallback_result
from app.services.pandas_store import PandasStore

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "evaluate.py"
_spec = importlib.util.spec_from_file_location("evaluate_script", _SCRIPT)
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)

RUN_DATE = "2026-09-21"
LEGACY_COLUMNS = ["id", "gold", "pred", "confidence", "correct", "errored", "content"]
REAL_OUTPUTS = [ev.PRED_PATH, ev.REPORT_PATH, ev.BINARY_PATH, ev.ERRORS_PATH, ev.CM_PATH]


def _sha256(path) -> str:
    p = Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else "missing"


@pytest.fixture(scope="module", autouse=True)
def _real_result_files_untouched():
    """已提交的評測結果檔是論文數據：這個測試模組跑完後必須一個位元都沒變。"""
    before = {path: _sha256(path) for path in REAL_OUTPUTS}
    yield
    assert {path: _sha256(path) for path in REAL_OUTPUTS} == before


class FakeClock:
    """取代 evaluate 模組裡的 time：perf_counter 由假 AI 推進；sleep 不真的等，但同樣推進時鐘，
    這樣才驗得出 --delay 的等待沒有被算進 elapsed_ms。"""

    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def perf_counter(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class FakeAI:
    """照劇本逐次回應；每次呼叫把假時鐘往前推 latency 秒（＝固定延遲）。"""
    providers = ["cgu"]
    cgu_model = "gpt-5.4-mini"

    def __init__(self, clock, script):
        self.clock = clock
        self.script = list(script)
        self.calls = []
        self.embedded = []

    def analyze_content(self, content, url=None, context=None, use_web_search=None):
        step = self.script[len(self.calls)]
        self.calls.append({"content": content, "url": url, "use_web_search": use_web_search})
        self.clock.now += step["latency"]
        if step.get("fallback"):
            return _default_fallback_result("cgu HTTP 503: mock upstream down")
        risk = step["risk"]
        return {
            "is_risk": risk != "SAFE", "risk_type": risk, "category": "Test",
            "confidence_score": step.get("conf", 0.9), "summary": "mock", "explanation": "mock",
            "sources": [],
            "provider": step.get("provider", "cgu"), "model": step.get("model", "gpt-5.4-mini"),
        }

    def generate_embedding(self, text):
        self.embedded.append(text)
        return [0.1, 0.2, 0.3]


def ok(risk, latency, **extra):
    return {"risk": risk, "latency": latency, **extra}


def down(latency):
    return {"fallback": True, "latency": latency}


class Sandbox:
    def __init__(self, tmp_path, monkeypatch, clock):
        self.monkeypatch = monkeypatch
        self.clock = clock
        self.data = tmp_path / "data"
        self.data.mkdir()
        self.paths = {
            "DATA_DIR": self.data,
            "ASSETS_DIR": tmp_path / "assets",
            "DEFAULT_INPUT": self.data / "eval_set.csv",
            "PRED_PATH": self.data / "eval_predictions.csv",
            "REPORT_PATH": self.data / "eval_report.csv",
            "BINARY_PATH": self.data / "eval_binary.csv",
            "ERRORS_PATH": self.data / "eval_errors.csv",
            "CM_PATH": tmp_path / "assets" / "confusion_matrix.png",
        }
        for name, path in self.paths.items():
            monkeypatch.setattr(ev, name, str(path))

    def __getitem__(self, name) -> Path:
        return self.paths[name]

    def eval_set(self, golds) -> pd.DataFrame:
        """寫一份小題庫到 tmp（欄位同 data/eval_set.csv），回傳讀進來的 DataFrame。"""
        df = pd.DataFrame([
            {"id": i, "gold_label": gold, "content": f"第 {i} 則測試訊息：請勿轉傳", "note": f"note-{i}"}
            for i, gold in enumerate(golds, start=1)
        ])
        df.to_csv(self["DEFAULT_INPUT"], index=False)
        return pd.read_csv(self["DEFAULT_INPUT"])

    def use_ai(self, script) -> FakeAI:
        fake = FakeAI(self.clock, script)
        self.monkeypatch.setattr(ev, "AIService", lambda: fake)
        return fake

    def forbid_ai_and_clock(self):
        """--report-only 的條件：不得建立 AIService、不得取現在的日期。"""
        def _no_ai():
            raise AssertionError("--report-only 不得建立 AIService")

        def _no_today():
            raise AssertionError("--report-only 不得取現在的日期")

        self.monkeypatch.setattr(ev, "AIService", _no_ai)
        self.monkeypatch.setattr(ev, "_today", _no_today)

    def main(self, *argv):
        self.monkeypatch.setattr(sys, "argv", ["evaluate.py", *argv])
        ev.main()

    def result_bytes(self) -> dict:
        return {name: self[name].read_bytes() for name in ("REPORT_PATH", "BINARY_PATH", "ERRORS_PATH")}


@pytest.fixture
def box(tmp_path, monkeypatch):
    def _no_network(*args, **kwargs):
        raise AssertionError("network access in offline test")

    monkeypatch.setattr("requests.sessions.Session.request", _no_network)
    clock = FakeClock()
    monkeypatch.setattr(ev, "time", clock)
    monkeypatch.setattr(ev, "_today", lambda: RUN_DATE)
    # 混淆矩陣圖（matplotlib）不在本票範圍，單元測試不產圖
    monkeypatch.setattr(ev, "_save_confusion_png", lambda cm: None)
    return Sandbox(tmp_path, monkeypatch, clock)


# ── --timing：逐筆 elapsed_ms 與 p50 / p90 ────────────────────────────

def test_timing_column_and_percentiles(box, capsys):
    df = box.eval_set(["SCAM", "SCAM", "MISINFO", "MISINFO", "SAFE", "SAFE"])
    fake = box.use_ai([
        ok("SCAM", 0.1), ok("SCAM", 0.2), down(60.0),
        ok("MISINFO", 0.3), ok("SAFE", 0.4), ok("SAFE", 0.5),
    ])

    preds = ev.run_predictions(df, delay=3, resume=False, timing=True)

    assert len(fake.calls) == 6
    saved = pd.read_csv(box["PRED_PATH"])
    assert list(saved.columns) == ev.PRED_COLUMNS
    # 整數毫秒；每筆之間 --delay 的 3 秒等待沒有被算進去
    assert saved["elapsed_ms"].tolist() == [100, 200, 60000, 300, 400, 500]
    assert box.clock.sleeps == [3, 3, 3, 3, 3]
    assert saved["errored"].tolist() == [False, False, True, False, False, False]

    # fallback 那筆（60 秒）有留紀錄，但不進統計：numpy 線性內插 [100..500] → p50 300、p90 460
    assert ev.timing_summary(preds[~preds["errored"]]) == {
        "elapsed_ms_p50": 300.0, "elapsed_ms_p90": 460.0, "elapsed_ms_n": 5,
    }

    capsys.readouterr()
    ev.compute_metrics(preds, timing=True)
    out = capsys.readouterr().out
    assert "只計非 fallback 的 5 筆" in out
    assert "p50 = 300.0 ms (0.30 s)" in out
    assert "p90 = 460.0 ms (0.46 s)" in out

    report = pd.read_csv(box["REPORT_PATH"])
    assert len(report) == 5
    assert report["elapsed_ms_p50"].tolist() == [300.0] * 5
    assert report["elapsed_ms_p90"].tolist() == [460.0] * 5
    assert report["elapsed_ms_n"].tolist() == [5] * 5


def test_without_timing_flag_elapsed_ms_stays_empty(box, capsys):
    df = box.eval_set(["SCAM", "SAFE"])
    box.use_ai([ok("SCAM", 0.1), ok("SAFE", 0.2)])

    preds = ev.run_predictions(df, delay=0, resume=False)

    saved = pd.read_csv(box["PRED_PATH"])
    assert list(saved.columns) == ev.PRED_COLUMNS      # 欄位固定存在，只是沒有值
    assert saved["elapsed_ms"].isna().all()
    assert ev.timing_summary(preds) == {"elapsed_ms_p50": "", "elapsed_ms_p90": "", "elapsed_ms_n": 0}

    capsys.readouterr()
    ev.compute_metrics(preds)
    assert "p50" not in capsys.readouterr().out
    ev.compute_metrics(preds, timing=True)             # 要求了計時卻沒有紀錄 → 明講，不印假數字
    out = capsys.readouterr().out
    assert "p50" not in out
    assert "請以 --timing 重跑評測" in out

    report = pd.read_csv(box["REPORT_PATH"])
    assert report["elapsed_ms_n"].tolist() == [0] * 5
    assert report["elapsed_ms_p50"].isna().all() and report["elapsed_ms_p90"].isna().all()


# ── 報告的執行條件欄位 ───────────────────────────────────────────────

def test_report_metadata_columns(box):
    df = box.eval_set(["SCAM", "MISINFO", "SAFE", "SAFE"])
    fake = box.use_ai([ok("SCAM", 0.1), ok("MISINFO", 0.1), ok("SAFE", 0.1), down(0.1)])

    preds = ev.run_predictions(df, delay=0, resume=False, timing=True)
    ev.compute_metrics(preds)

    # 報告寫的 use_web_search 就是實際傳給 AI 的值（評測固定關閉）
    assert [c["use_web_search"] for c in fake.calls] == [False] * 4

    saved = pd.read_csv(box["PRED_PATH"])
    # fallback 結果沒有 provider／model，退回設定的主引擎
    assert saved["provider"].tolist() == ["cgu"] * 4
    assert saved["model"].tolist() == ["gpt-5.4-mini"] * 4
    assert saved["date"].tolist() == [RUN_DATE] * 4
    assert saved["use_web_search"].tolist() == [False] * 4

    report = pd.read_csv(box["REPORT_PATH"], dtype=str, keep_default_na=False)
    # 原有五欄的位置與名稱不變，新欄位加在後面
    assert list(report.columns) == [
        "label", "precision", "recall", "f1", "support",
        "provider", "model", "date", "use_web_search",
        "elapsed_ms_p50", "elapsed_ms_p90", "elapsed_ms_n",
    ]
    assert report["label"].tolist() == ["SCAM", "MISINFO", "SAFE", "accuracy", "macro_avg"]
    for col, expected in [("provider", "cgu"), ("model", "gpt-5.4-mini"),
                          ("date", RUN_DATE), ("use_web_search", "False")]:
        assert report[col].tolist() == [expected] * 5


def test_report_metadata_shows_every_engine_that_answered(box):
    """備援引擎接手過幾筆時，報告要照實列出，不能只寫主引擎。"""
    df = box.eval_set(["SCAM", "SAFE", "SAFE"])
    box.use_ai([
        ok("SCAM", 0.1), ok("SAFE", 0.1, provider="openai", model="gpt-5-mini"), ok("SAFE", 0.1),
    ])

    meta = ev.run_metadata(ev.run_predictions(df, delay=0, resume=False))

    assert meta == {"provider": "cgu|openai", "model": "gpt-5-mini|gpt-5.4-mini",
                    "date": RUN_DATE, "use_web_search": "False"}


# ── --report-only：不呼叫 AI、不取現在時間，重算結果與原檔逐位元相同 ──────

def test_report_only_consistent(box):
    box.eval_set(["SCAM", "SCAM", "MISINFO", "MISINFO", "SAFE", "SAFE", "SAFE"])
    box.use_ai([
        ok("SCAM", 0.11, conf=0.95), ok("SAFE", 0.23, conf=0.61),      # id 2：偽陰性
        ok("MISINFO", 0.37, conf=0.9), ok("SCAM", 0.41, conf=0.72),    # id 4：類別混淆
        ok("SAFE", 0.53, conf=0.88), ok("SCAM", 0.67, conf=0.97),      # id 6：偽陽性
        down(1.5),
    ])
    box.main("--timing", "--delay", "0")

    predictions = box["PRED_PATH"].read_bytes()
    original = box.result_bytes()
    report = pd.read_csv(box["REPORT_PATH"])
    assert report["date"].tolist() == [RUN_DATE] * 5
    assert report["elapsed_ms_n"].tolist() == [6] * 5
    errors = pd.read_csv(box["ERRORS_PATH"])
    assert errors["id"].tolist() == [2, 4, 6]
    assert errors["error_type"].notna().all()                          # QA-2：逐筆有 error_type
    assert errors["note"].tolist() == ["note-2", "note-4", "note-6"]

    box.forbid_ai_and_clock()
    box.main("--report-only")
    assert box.result_bytes() == original
    box.main("--report-only", "--timing")                              # 旗標只影響主控台，不影響檔案
    assert box.result_bytes() == original
    assert box["PRED_PATH"].read_bytes() == predictions                # 重算不改寫預測檔


# ── 舊預測檔（沒有 elapsed_ms 與執行條件欄位）仍可續跑、可重算 ──────────

def _write_legacy_predictions(path, rows):
    legacy = pd.DataFrame([
        {"id": rid, "gold": gold, "pred": pred, "confidence": 0.9, "correct": gold == pred,
         "errored": False, "content": f"第 {rid} 則測試訊息：請勿轉傳"}
        for rid, gold, pred in rows
    ], columns=LEGACY_COLUMNS)
    legacy.to_csv(path, index=False, encoding="utf-8-sig")             # 與 B-23 之前的寫法相同


def test_resume_with_legacy_predictions_without_elapsed_ms(box, capsys):
    df = box.eval_set(["SCAM", "MISINFO", "SAFE", "SAFE"])
    _write_legacy_predictions(box["PRED_PATH"], [(1, "SCAM", "SCAM"), (2, "MISINFO", "MISINFO")])
    fake = box.use_ai([ok("SAFE", 0.25), ok("SAFE", 0.75)])

    preds = ev.run_predictions(df, delay=0, resume=True, timing=True)

    assert [c["content"] for c in fake.calls] == ["第 3 則測試訊息：請勿轉傳", "第 4 則測試訊息：請勿轉傳"]
    saved = pd.read_csv(box["PRED_PATH"])
    assert list(saved.columns) == ev.PRED_COLUMNS
    assert saved["id"].tolist() == [1, 2, 3, 4]
    assert saved["pred"].tolist() == ["SCAM", "MISINFO", "SAFE", "SAFE"]
    assert saved["elapsed_ms"].isna().tolist() == [True, True, False, False]
    assert saved["elapsed_ms"].dropna().tolist() == [250, 750]
    assert saved["provider"].isna().tolist() == [True, True, False, False]
    raw = box["PRED_PATH"].read_text(encoding="utf-8-sig")
    assert ",250,cgu,gpt-5.4-mini," in raw                             # 有缺值的欄仍寫整數，不是 250.0

    # 統計只算有紀錄的列；舊列的執行條件不明 → 報告照實標 unknown
    assert ev.timing_summary(preds)["elapsed_ms_n"] == 2
    assert ev.run_metadata(preds)["provider"] == "cgu|unknown"
    capsys.readouterr()
    ev.compute_metrics(preds, timing=True)
    assert "只計非 fallback 的 2 筆" in capsys.readouterr().out


def test_report_only_on_legacy_predictions_file(box, capsys):
    box.eval_set(["SCAM", "MISINFO", "SAFE"])
    _write_legacy_predictions(
        box["PRED_PATH"], [(1, "SCAM", "SCAM"), (2, "MISINFO", "SAFE"), (3, "SAFE", "SAFE")])
    box.forbid_ai_and_clock()

    box.main("--report-only", "--timing")

    out = capsys.readouterr().out
    assert "provider=-  model=-  date=-  use_web_search=-" in out
    assert "請以 --timing 重跑評測" in out
    report = pd.read_csv(box["REPORT_PATH"], dtype=str, keep_default_na=False)
    assert report.loc[report["label"] == "accuracy", "f1"].tolist() == ["0.667"]
    for col in ("provider", "model", "date", "use_web_search", "elapsed_ms_p50", "elapsed_ms_p90"):
        assert report[col].tolist() == [""] * 5                        # 不明就留空，不用現在的設定去填
    assert report["elapsed_ms_n"].tolist() == ["0"] * 5

    first = box.result_bytes()
    box.main("--report-only")
    assert box.result_bytes() == first


# ── --seed-db：gold 標記 ─────────────────────────────────────────────

def test_seed_db_writes_gold_verified(box, tmp_path, monkeypatch):
    df = box.eval_set(["SCAM", "MISINFO", "SAFE"])
    eval_set_before = box["DEFAULT_INPUT"].read_bytes()
    fake = box.use_ai([ok("SCAM", 0.1), ok("SAFE", 0.1), ok("SAFE", 0.1)])   # id 2 判錯 → 不入庫
    store = PandasStore(data_dir=str(tmp_path / "kb"))
    monkeypatch.setattr("app.services.store_factory.get_knowledge_store", lambda: store)

    ev.run_predictions(df, delay=0, resume=False, seed_db=True, timing=True)

    kb = store.get_all_records()
    assert sorted(kb["raw_content"].tolist()) == sorted(
        ["第 1 則測試訊息：請勿轉傳", "第 3 則測試訊息：請勿轉傳"])
    assert kb["label_source"].tolist() == ["gold", "gold"]
    assert kb["verified"].tolist() == [True, True]                     # 沒有任何來源也一律已證實
    assert sorted(kb["risk_type"].tolist()) == ["SAFE", "SCAM"]        # 標籤用 gold
    assert len(fake.embedded) == 2
    assert box["DEFAULT_INPUT"].read_bytes() == eval_set_before        # 不修改題庫


# ── Windows 主控台（cp950）印得出來 ──────────────────────────────────

def test_console_output_is_cp950_safe(box, capsys):
    box.eval_set(["SCAM", "MISINFO", "SAFE"])
    box.use_ai([ok("SCAM", 0.1), ok("SAFE", 0.2), down(0.3)])
    box.main("--timing", "--delay", "0")
    box.forbid_ai_and_clock()
    box.main("--report-only", "--timing")
    with pytest.raises(SystemExit):
        box.main("--help")

    out = capsys.readouterr().out
    assert "--timing" in out and "p50 = " in out
    out.encode("cp950")                                                # 有 emoji 或 Big5 以外的符號會在這裡炸
