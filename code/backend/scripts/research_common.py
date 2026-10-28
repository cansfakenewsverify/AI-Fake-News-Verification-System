"""
信心程度驗證與模型比較的共用工具（scripts/confidence_validation.py、scripts/model_benchmark.py）。

在 GitHub Actions 的 research workflow 上跑（AGENTS.md 第 2 節：雲端 session 沒有金鑰、連不到 CGU 與查核網站）：
- data/research/（gitignored；workflow 以 actions/cache 保存，不公開下載）：抓取的原始回應、語料（含訊息原文）、向量。
- 要 commit 的結果只放 docs/test/results/：查核網址、雜湊、判定與數字，**不放訊息原文**（Cofacts 訊息可能含個資）。
- 花錢的步驟一律經過 Budget：開始前與每 100 題讀 CGU /me/usage，保留 USD 3 給網站使用者；台灣時間週日不跑
  （週日 21:17 有每週評測）。

語料的收錄規則與正式站相同（app/services/factcheck_corpus.py）；這裡只多記一個欄位 verdict_date：
查核結論出現的日期（MyGoPen／台灣事實查核中心＝文章發布日；Cofacts＝最早一則獲認可回覆的日期），
做時間切分用——一則訊息只能比對在它之前就已經有結論的查核。
"""
import contextlib
import hashlib
import json
import math
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

os.environ.setdefault("STORAGE_BACKEND", "local")

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parents[1]
sys.path.insert(0, str(BACKEND))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import requests  # noqa: E402

from app.services import factcheck_corpus as fc  # noqa: E402

RESEARCH = BACKEND / "data" / "research"
RAW = RESEARCH / "raw"
CORPUS = RESEARCH / "corpus.parquet"
RESULTS = REPO / "docs" / "test" / "results"
WEEKLY = RESULTS / "weekly"
STATUS = RESULTS / "research_status.json"
PF2_SETS = [REPO / "docs/test/pf2_paraphrases.csv", RESULTS / "pf2_rerun_2026-09-21.csv"]

TZ_TAIPEI = timezone(timedelta(hours=8))
RESERVE_USD = 3.0              # AGENTS.md 第 4 節：保留給網站使用者
USAGE_CHECK_EVERY = 100        # 每幾題重讀一次 /me/usage
TRIAL_ITEMS = 50               # 先試跑幾題估花費
RISKY = frozenset({"SCAM", "MISINFO"})

# CGU 閘道的 embedding 模型：每百萬 tokens 的 USD（閘道實扣約牌價 2 倍；bge-m3 是本地模型，不花 OpenAI 額度）
EMBED_MODELS: Dict[str, Dict[str, Any]] = {
    "text-embedding-3-small": {"slug": "small", "usd_per_m": 0.04},
    "text-embedding-3-large": {"slug": "large", "usd_per_m": 0.26},
    "bge-m3:latest": {"slug": "bge-m3", "usd_per_m": 0.0},
}
DEFAULT_EMBED = "text-embedding-3-small"


def log(msg: str) -> None:
    """Windows 主控台是 cp950：中文照印，cp950 沒有的字元（≥、– 等）換成 ?，不讓腳本崩潰。"""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(msg.encode(enc, "replace").decode(enc, "replace"), flush=True)


def now_taipei() -> datetime:
    return datetime.now(TZ_TAIPEI)


def spending_block_reason(now: Optional[datetime] = None) -> Optional[str]:
    """花錢的步驟能不能現在跑；不能時回傳原因。"""
    now = now or now_taipei()
    if now.weekday() == 6:
        return "台灣時間週日有每週評測（21:17），花錢的批次不在週日跑"
    return None


def update_status(section: str, data: Dict[str, Any], path: Optional[Path] = None) -> None:
    """把一個步驟的摘要（數字、日期，不含原文）寫進 docs/test/results/research_status.json。"""
    path = path or STATUS
    status = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    status[section] = {**data, "updated_at": now_taipei().isoformat(timespec="seconds")}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def step_summary(text: str) -> None:
    """GitHub Actions 執行頁的摘要；本機執行時只印出來。"""
    log(text)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text.rstrip() + "\n\n")


# ── 額度護欄 ─────────────────────────────────────────────────

class BudgetError(RuntimeError):
    pass


class Budget:
    """
    CGU 額度護欄：可用額 = min(max_usd, 剩餘 − 保留額)。
    - price_known：每題花費以回應的 token 數估算；不知道單價時改以 /me/usage 的增加量計算（每批都重讀）。
    - free：不花 OpenAI 額度的模型（本地、算力池）；仍每 100 題確認剩餘額度沒有掉到保留額以下。
    """

    def __init__(self, max_usd: float, *, free: bool = False, price_known: bool = True,
                 reserve: float = RESERVE_USD, usage_fn: Optional[Callable[[], Dict[str, float]]] = None):
        self.usage_fn = usage_fn or fc.cgu_usage
        self.free, self.price_known, self.reserve = free, price_known, reserve
        self.before = self.usage_fn()
        remaining = self.before["remaining_usd"]
        if remaining < 0:
            raise BudgetError("讀不到 CGU /me/usage（金鑰沒設或閘道故障），不跑會花額度的步驟")
        self.allowed = math.inf if free else min(float(max_usd), remaining - reserve)
        if self.allowed <= 0:
            raise BudgetError(f"CGU 剩 USD {remaining:.2f}，扣掉保留額 USD {reserve:.0f} 後沒有可用額度")
        self.spent = 0.0
        self.done = 0
        self.checked_at = 0
        self.stop_reason: Optional[str] = None

    def guard(self, next_cost: float, next_items: int = 1) -> bool:
        """下一批（預估 next_cost 美元）能不能跑；不能時記下 stop_reason。"""
        if not self.free and self.spent + next_cost > self.allowed:
            self.stop_reason = "budget"
            return False
        due = self.done - self.checked_at >= USAGE_CHECK_EVERY or (not self.price_known and not self.free and self.done)
        if due and self.done:
            self.checked_at = self.done
            usage = self.usage_fn()
            left = usage["remaining_usd"]
            if left < 0:
                self.stop_reason = "usage_unreadable"
                return False
            if not self.price_known and not self.free:
                self.spent = max(self.spent, usage["cost_usd"] - self.before["cost_usd"])
                if self.spent + next_cost > self.allowed:
                    self.stop_reason = "budget"
                    return False
            if left - (0 if self.free else next_cost) < self.reserve:
                self.stop_reason = "reserve"
                return False
        return True

    def record(self, usd: float, items: int) -> None:
        self.spent += float(usd or 0)
        self.done += items

    def summary(self) -> Dict[str, Any]:
        after = self.usage_fn()
        actual = after["cost_usd"] - self.before["cost_usd"] if after["cost_usd"] >= 0 else None
        return {"usage_before": self.before, "usage_after": after, "allowed_usd": None if self.free else round(self.allowed, 4),
                "estimated_usd": round(self.spent, 4), "usage_delta_usd": None if actual is None else round(actual, 4),
                "items": self.done, "stop_reason": self.stop_reason}


# ── 語料（含查核結論出現的日期） ───────────────────────────────

COFACTS_QUERY_DATED = fc.COFACTS_QUERY.replace(
    "articleReplies(status: NORMAL) { positiveFeedbackCount", "articleReplies(status: NORMAL) { createdAt positiveFeedbackCount")
assert COFACTS_QUERY_DATED != fc.COFACTS_QUERY, "factcheck_corpus.COFACTS_QUERY changed; update COFACTS_QUERY_DATED"

COFACTS_ARTICLE_QUERY = """
query($id: String!) {
  GetArticle(id: $id) {
    id text createdAt replyRequestCount
    articleCategories(status: NORMAL) { categoryId }
    articleReplies(status: NORMAL) { createdAt positiveFeedbackCount negativeFeedbackCount reply { type text } }
  }
}
"""


def make_cache(raw_dir: Optional[Path] = None, refresh: bool = False):
    """factcheck_corpus 的 cache hook：原始回應存成 raw_dir/<name>，重跑直接讀檔。"""
    raw_dir = raw_dir or RAW

    def cache(name: str, fetch: Callable[[], Any]) -> Any:
        path = raw_dir / name
        if path.exists() and not refresh:
            return json.loads(path.read_text(encoding="utf-8"))
        data = fetch()
        raw_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        time.sleep(fc.DELAY_S)
        return data
    return cache


@contextlib.contextmanager
def dated_cofacts_query():
    """抓 Cofacts 時多要每則回覆的 createdAt（查核結論出現的日期）；結束後還原。"""
    original = fc.COFACTS_QUERY
    fc.COFACTS_QUERY = COFACTS_QUERY_DATED
    try:
        yield
    finally:
        fc.COFACTS_QUERY = original


def cofacts_verdict_dates(nodes: Iterable[dict], want: str) -> Dict[str, str]:
    """Cofacts 文章網址 → 最早一則獲認可、類型為 want 的回覆日期（沒有就用文章建立日）。"""
    out = {}
    for n in nodes:
        dates = [str(ar.get("createdAt") or "")[:10] for ar in n.get("articleReplies") or []
                 if (ar.get("reply") or {}).get("type") == want
                 and (ar.get("positiveFeedbackCount") or 0) > (ar.get("negativeFeedbackCount") or 0)
                 and ar.get("createdAt")]
        out[f"https://cofacts.tw/article/{n['id']}"] = min(dates) if dates else str(n.get("createdAt") or "")[:10]
    return out


def fetch_corpus(refresh: bool = False, cofacts_max: int = 9000, min_requests: int = fc.COFACTS_MIN_REQUESTS,
                 cache=None) -> Tuple[pd.DataFrame, dict]:
    """
    全部查核結論 → DataFrame（factcheck_corpus.COLUMNS＋verdict_date）。規則同批次入庫與每週日的 full 同步：
    MyGoPen 全站、台灣事實查核中心全部報告、Cofacts RUMOR／NOT_RUMOR（至少 min_requests 人回報，最多 cofacts_max 則）。
    """
    cache = cache or make_cache(refresh=refresh)
    skipped: dict = {}
    rows = fc.mygopen_rows(fc.mygopen_entries(cache), skipped)
    log(f"[corpus] MyGoPen rows: {len(rows)}")
    rows += fc.tfc_rows(cache, skipped=skipped)
    log(f"[corpus] + TFC rows: {len(rows)}")
    dates: Dict[str, str] = {}
    with dated_cofacts_query():
        for want in ("RUMOR", "NOT_RUMOR"):
            nodes = fc.cofacts_nodes(want, min_requests, cofacts_max, cache)
            rows += fc.cofacts_rows(nodes, want, skipped)
            dates.update(cofacts_verdict_dates(nodes, want))
            log(f"[corpus] Cofacts {want} articles: {len(nodes)}")
    df = pd.DataFrame(fc.dedupe_rows(rows, skipped), columns=fc.COLUMNS)
    df["published"] = df["published"].fillna("").astype(str).str.slice(0, 10)
    df["verdict_date"] = [dates.get(u) or p for u, p in zip(df["url"], df["published"])]
    return df, skipped


def fetch_cofacts_article(article_id: str, cache=None) -> Optional[dict]:
    """單一 Cofacts 文章（不在語料裡的題目，例如回報人數不到 3 的本週新查核）。"""
    cache = cache or make_cache()
    body = {"query": COFACTS_ARTICLE_QUERY, "variables": {"id": article_id}}
    data = cache(f"cofacts_article_{article_id}.json", lambda: fc.http_json("POST", fc.COFACTS_API, body=body)["_body"])
    return ((data or {}).get("data") or {}).get("GetArticle")


def load_corpus(path: Optional[Path] = None) -> pd.DataFrame:
    path = path or CORPUS
    if not path.exists():
        raise SystemExit(f"{path} is missing: run the corpus-fetch task first")
    return pd.read_parquet(path)


def pf2_texts() -> List[Tuple[str, str]]:
    """PF-2 改寫句題組（原句, 改寫句）；檔案本來就在 repo 裡。"""
    pairs = []
    for path in PF2_SETS:
        if not path.exists():
            continue
        df = pd.read_csv(path, encoding="utf-8-sig")
        orig = "original" if "original" in df.columns else "知識庫原文"
        para = "paraphrase" if "paraphrase" in df.columns else "改寫句"
        pairs += list(zip(df[orig].astype(str), df[para].astype(str)))
    return pairs


# ── 向量 ─────────────────────────────────────────────────────

def text_hash(text: str) -> str:
    return fc.content_hash(text)


def emb_path(model: str) -> Path:
    return RESEARCH / f"emb_{EMBED_MODELS[model]['slug']}.npz"


class EmbeddingStore:
    """content_hash → 單位向量（float16 存檔、float32 計算）。"""

    def __init__(self, model: str, path: Optional[Path] = None):
        self.model = model
        self.path = path or emb_path(model)
        self.vectors: Dict[str, np.ndarray] = {}
        if self.path.exists():
            with np.load(self.path, allow_pickle=False) as data:
                for h, v in zip(data["hashes"], data["vectors"]):
                    self.vectors[str(h)] = v

    def __contains__(self, h: str) -> bool:
        return h in self.vectors

    def __len__(self) -> int:
        return len(self.vectors)

    def add(self, h: str, vector: Iterable[float]) -> None:
        v = np.asarray(list(vector) if not isinstance(vector, np.ndarray) else vector, dtype=np.float32)
        norm = float(np.linalg.norm(v))
        self.vectors[h] = (v / norm if norm else v).astype(np.float16)

    def matrix(self, hashes: Sequence[str]) -> np.ndarray:
        return np.stack([self.vectors[h] for h in hashes]).astype(np.float32)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        hashes = list(self.vectors)
        tmp = self.path.with_suffix(".tmp.npz")
        np.savez(tmp, hashes=np.array(hashes, dtype="U64"),
                 vectors=np.stack([self.vectors[h] for h in hashes]) if hashes else np.zeros((0, 1), np.float16))
        os.replace(tmp, self.path)


def embed_call(model: str, texts: List[str], timeout: float = 180.0) -> Tuple[List[Optional[np.ndarray]], int]:
    """
    CGU /embeddings（OpenAI 相容）→ (向量, tokens)。整批被拒（400／422，例如本地模型不收多筆輸入）就逐筆送；
    單筆仍被拒的文字回傳 None（呼叫端略過並計數），不讓一則怪文字中斷整批。
    """
    from app.config import settings

    base = (settings.EMBED_RELAY_URL or settings.CGU_BASE_URL or "").rstrip("/")
    key = (settings.EMBED_API_KEY or settings.CGU_API_KEY or "").strip()
    if not base or not key:
        raise RuntimeError("embedding is not configured (CGU_API_KEY)")

    def post(batch: List[str]) -> dict:
        for attempt in range(4):
            try:
                r = requests.post(f"{base}/embeddings", headers={"Authorization": f"Bearer {key}"},
                                  json={"model": model, "input": [t[:fc.EMBED_MAX_CHARS] for t in batch]}, timeout=timeout)
                if r.status_code in (400, 422):
                    return {"_split": True} if len(batch) > 1 else {"_rejected": True}
                r.raise_for_status()
                return r.json()
            except Exception as exc:
                if attempt == 3:
                    raise
                log(f"  embedding retry {attempt + 1} after {type(exc).__name__}")
                time.sleep(5 * (attempt + 1))
        raise RuntimeError("unreachable")

    body = post(texts)
    if body.get("_rejected"):
        return [None], 0
    if body.get("_split"):
        vectors, tokens = [], 0
        for t in texts:
            got, used = embed_call(model, [t], timeout)
            vectors += got
            tokens += used
        return vectors, tokens
    vectors: List[Any] = [None] * len(texts)
    for item in body["data"]:
        vectors[item.get("index", 0)] = np.asarray(item["embedding"], dtype=np.float32)
    return vectors, int((body.get("usage") or {}).get("total_tokens") or 0)


# ── 時間切分的最近鄰 ─────────────────────────────────────────

def nearest_earlier(Q: np.ndarray, q_dates: Sequence[str], q_hashes: Sequence[str],
                    E: np.ndarray, e_dates: Sequence[str], e_hashes: Sequence[str],
                    k: int = 5, chunk: int = 512) -> Tuple[np.ndarray, np.ndarray]:
    """
    每一題只比對「查核結論日期早於該題日期」的證據（同一天或之後的、與題目一字不差的都排除）。
    Q、E 為單位向量；回傳 (相似度 [n, k]（不足補 -1）, 證據索引 [n, k]（不足補 -1）)。
    題目日期空白時不比對任何證據。
    """
    e_day = np.array([str(d or "9999-12-31")[:10] for d in e_dates])
    e_hash = np.array(list(e_hashes))
    n = len(q_dates)
    sims = np.full((n, k), -1.0, dtype=np.float32)
    idx = np.full((n, k), -1, dtype=np.int64)
    for start in range(0, n, chunk):
        stop = min(start + chunk, n)
        block = Q[start:stop] @ E.T
        for row, qi in enumerate(range(start, stop)):
            qd = str(q_dates[qi] or "")[:10]
            if not qd:
                continue
            allowed = (e_day < qd) & (e_hash != q_hashes[qi])
            s = np.where(allowed, block[row], -np.inf)
            take = min(k, int(allowed.sum()))
            if take == 0:
                continue
            top = np.argpartition(-s, take - 1)[:take]
            top = top[np.argsort(-s[top])]
            sims[qi, :take] = s[top]
            idx[qi, :take] = top
    return sims, idx


# ── 分群（同一則謠言的不同版本放同一群） ───────────────────────

class UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, a: int) -> int:
        while self.parent[a] != a:
            self.parent[a] = self.parent[self.parent[a]]
            a = self.parent[a]
        return a

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def group_ids(keys: Sequence[str], vectors: Optional[np.ndarray], threshold: float, chunk: int = 1024) -> List[int]:
    """同一個 key（查核網址）或相似度 ≥ threshold 的連成同一群；回傳每一列的群號（群內最小的列號）。"""
    n = len(keys)
    uf = UnionFind(n)
    first: Dict[str, int] = {}
    for i, key in enumerate(keys):
        if key:
            if key in first:
                uf.union(first[key], i)
            else:
                first[key] = i
    if vectors is not None and n:
        for start in range(0, n, chunk):
            block = vectors[start:start + chunk] @ vectors.T
            rows, cols = np.nonzero(block >= threshold)
            for r, c in zip(rows, cols):
                if start + r < c:
                    uf.union(start + r, int(c))
    return [uf.find(i) for i in range(n)]


def stable_key(value: str, seed: str) -> str:
    return hashlib.md5(f"{value}|{seed}".encode("utf-8")).hexdigest()


# ── 統計 ─────────────────────────────────────────────────────

def wilson(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    from app.services.weekly_eval import wilson as _wilson

    return _wilson(k, n, z)


def mcnemar_exact(b: int, c: int) -> float:
    """McNemar 精確檢定（雙尾）：b、c 為兩個模型只有一方答對的題數。"""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def auroc(scores: Sequence[float], positive: Sequence[bool]) -> Optional[float]:
    """Mann–Whitney 版 AUROC（同分取平均名次）；只有一類時回傳 None。"""
    s = np.asarray(scores, dtype=float)
    y = np.asarray(positive, dtype=bool)
    n_pos, n_neg = int(y.sum()), int((~y).sum())
    if n_pos == 0 or n_neg == 0:
        return None
    ranks = pd.Series(s).rank(method="average").to_numpy()
    return float((ranks[y].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def pct(x: Optional[float]) -> str:
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:.1f}%"


def rate_cell(k: int, n: int) -> str:
    """「比例（信賴區間）k／n」；n=0 → —。"""
    if not n:
        return "—（0）"
    lo, hi = wilson(k, n)
    return f"{pct(k / n)}（{pct(lo)}–{pct(hi)}）{k}／{n}"


def run_date() -> str:
    return now_taipei().date().isoformat()


def is_risky(label: Any) -> bool:
    return str(label or "").upper() in RISKY


def parse_day(value: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
