"""
FR-18 one-off data cleanup (2026-09 source audit). Idempotent, --dry-run by default.

Knowledge base (D-03):
  rule 1  sources empty but source_url is Tier 1/2 -> backfill sources
          ({title: raw_content[:40], url}); grade every source item (Cofacts via
          GraphQL, results cached in data/clean_sources_cache.json so reruns do
          zero network); every kept item carries tier / tier_label; Tier 3 items
          move to related_discussions (JSON str); write source_tier; verified =
          label_source in (rule, gold, admin) or source_tier in (1, 2).
  rule 2  raw_content fails news_fetcher._is_real_claim, or source_url is a
          Cofacts article with no RUMOR/NOT_RUMOR reply -> verified=false,
          content_vector=None. Deterministic labels (rule/gold/admin) are never
          downgraded.
Trending fact_check_records (D-04):
  rule 3  source_url on news.google.com -> resolve the final URL through
          app.utils.safe_url.safe_get (HEAD, GET on failure, 10 s timeout).
          Resolved to a non-Google host -> overwrite source_url, then dedupe on
          (normalised title, domain) / identical URL keeping the earliest
          created_at; unresolved or still Google -> delete the row. Only
          resolutions to a non-Google host are cached under "_google_news" in
          clean_sources_cache.json ("still Google" is retried every run). The
          report counts deleted rows by label_source / risk_type so a deleted
          rule/gold/admin row is never hidden behind the downgrade line.
  rule 4  backfill verified + source_tier for every remaining row:
          label_source in (rule, gold, admin) -> true; ai with a Tier 1/2
          source_url -> true (Cofacts looked up via the shared cache); else false.

--apply backs up knowledge_base.parquet.bak-YYYYMMDD / factcheck.db.bak-YYYYMMDD
(an existing same-day backup is kept, never overwritten) before writing. A second
--apply reports 0 affected rows for every rule.

Usage (from code/backend):
    venv\\Scripts\\python scripts\\clean_sources_2026_09.py                 # dry-run, kb + trending
    venv\\Scripts\\python scripts\\clean_sources_2026_09.py --only=kb
    venv\\Scripts\\python scripts\\clean_sources_2026_09.py --only=kb --retry-cofacts
    venv\\Scripts\\python scripts\\clean_sources_2026_09.py --apply          # needs owner sign-off (D-05)

--dry-run writes only data/clean_sources_report.txt (and the Cofacts lookup
cache); knowledge_base.parquet / factcheck.db are untouched. Console output is
cp950 safe (no emoji); the report is UTF-8.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sqlite3
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.utils.source_tier import (  # noqa: E402
    ALWAYS_TIER3_DOMAINS,
    COFACTS_DOMAINS,
    COFACTS_GRAPHQL_URL,
    TIER_LABELS,
    _host_matches,
    _host_of,
    cofacts_article_id,
    tier_of,
)
from app.utils.safe_url import SafeFetchError, safe_get  # noqa: E402

KB_FILE = "knowledge_base.parquet"
DB_FILE = "factcheck.db"
CACHE_FILE = "clean_sources_cache.json"
REPORT_FILE = "clean_sources_report.txt"

DETERMINISTIC_LABELS = ("rule", "gold", "admin")
VERDICT_TYPES = {"RUMOR", "NOT_RUMOR"}
COFACTS_QUERY_TIMEOUT = 10.0

STATUS_HAS_REPLY = "has_reply"
STATUS_NO_REPLY = "no_reply"
STATUS_TIMEOUT = "timeout"
STATUS_ERROR = "error"
FAILED_STATUSES = (STATUS_TIMEOUT, STATUS_ERROR)
STATUS_TEXT = {
    STATUS_HAS_REPLY: "有回覆",
    STATUS_NO_REPLY: "無回覆",
    STATUS_TIMEOUT: "查詢失敗(timeout)",
    STATUS_ERROR: "查詢失敗(error)",
}

_ARTICLE_QUERY = """
query GetArticle($id: String!) {
  GetArticle(id: $id) {
    id
    articleReplies(status: NORMAL) { reply { type } }
  }
}
"""


# ──────────────────────────────────────────
# Cofacts lookup with a persistent JSON cache
# ──────────────────────────────────────────
def query_cofacts(article_id: str) -> Tuple[str, List[str]]:
    """One GraphQL lookup -> (status, reply types). Never raises."""
    try:
        resp = requests.post(
            COFACTS_GRAPHQL_URL,
            json={"query": _ARTICLE_QUERY, "variables": {"id": article_id}},
            timeout=COFACTS_QUERY_TIMEOUT,
        )
        resp.raise_for_status()
        data = (resp.json() or {}).get("data") or {}
        article = data.get("GetArticle") or {}
        types = sorted({
            t for t in (
                ((r or {}).get("reply") or {}).get("type")
                for r in (article.get("articleReplies") or [])
            ) if t
        })
    except requests.Timeout:
        return STATUS_TIMEOUT, []
    except Exception:
        return STATUS_ERROR, []
    return (STATUS_HAS_REPLY if set(types) & VERDICT_TYPES else STATUS_NO_REPLY), types


class CofactsChecker:
    """
    Resolves Cofacts article verdict status. Cached entries are reused with zero
    network; --retry-cofacts re-queries only entries whose status is timeout/error
    and overwrites them only when the new lookup succeeds.
    """

    def __init__(self, cache_path: Path, retry_failed: bool = False,
                 query: Optional[Callable[[str], Tuple[str, List[str]]]] = None):
        self.cache_path = cache_path
        self.retry_failed = retry_failed
        self._query = query or query_cofacts
        self.cache: Dict[str, Dict[str, Any]] = self._load()
        self.seen: Dict[str, Dict[str, Any]] = {}  # article_id -> {status, url, origin}
        self.network_calls = 0
        self.dirty = False

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if not self.cache_path.exists():
            return {}
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def save(self) -> None:
        if not self.dirty:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(self.cache, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        self.dirty = False

    def status(self, article_id: str, url: str = "") -> str:
        if article_id in self.seen:
            return self.seen[article_id]["status"]
        entry = self.cache.get(article_id)
        origin = "cache"
        if entry is None or (self.retry_failed and entry.get("status") in FAILED_STATUSES):
            self.network_calls += 1
            status, types = self._query(article_id)
            origin = "query"
            if entry is None or status not in FAILED_STATUSES:
                entry = {
                    "status": status,
                    "types": list(types),
                    "url": url,
                    "checked_at": datetime.now().isoformat(timespec="seconds"),
                }
                self.cache[article_id] = entry
                self.dirty = True
        self.seen[article_id] = {"status": entry["status"], "url": url or entry.get("url", ""),
                                 "origin": origin}
        return entry["status"]


# ──────────────────────────────────────────
# Value normalisation (parquet round-trips lists as ndarray, structs pad None)
# ──────────────────────────────────────────
def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(value != value)  # NaN
    except Exception:
        return False


def _clean_item(item: Any) -> Dict[str, Any]:
    if isinstance(item, dict):
        return {k: v for k, v in item.items() if not _is_missing(v)}
    return {"title": "", "url": str(item or "")}


def _as_items(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            return []
    if value is None or isinstance(value, (float, int)):
        return []
    try:
        return [_clean_item(v) for v in list(value)]
    except TypeError:
        return []


def _label_of(value: Any) -> str:
    return "ai" if _is_missing(value) or not str(value).strip() else str(value)


def _tier_value(value: Any) -> Optional[int]:
    if _is_missing(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool_value(value: Any) -> Optional[bool]:
    return None if _is_missing(value) else bool(value)


def _has_vector(value: Any) -> bool:
    if value is None or isinstance(value, (float, int, str)):
        return False
    try:
        return len(value) > 0
    except TypeError:
        return False


def _canon(items: List[Dict[str, Any]]) -> str:
    return json.dumps(items, ensure_ascii=False, sort_keys=True, default=str)


# ──────────────────────────────────────────
# Grading
# ──────────────────────────────────────────
def _is_cofacts(url: str) -> bool:
    host = _host_of(url)
    return _host_matches(host, COFACTS_DOMAINS) and not _host_matches(host, ALWAYS_TIER3_DOMAINS)


def cofacts_status_of(url: str, checker: CofactsChecker) -> Optional[str]:
    """Status for a Cofacts article URL; None when the URL is not a Cofacts article."""
    if not _is_cofacts(url):
        return None
    aid = cofacts_article_id(url)
    if not aid:
        return STATUS_NO_REPLY
    return checker.status(aid, url)


def grade_url(url: str, title: str, checker: CofactsChecker,
              verdict: Any = None, prior_tier: Optional[int] = None) -> int:
    if _is_cofacts(url):
        if verdict in VERDICT_TYPES:
            return 1
        status = cofacts_status_of(url, checker)
        if status == STATUS_HAS_REPLY:
            return 1
        if status in FAILED_STATUSES and prior_tier in (1, 2):
            return prior_tier  # a transient lookup failure never downgrades an earlier online grade
        return 3
    return tier_of(url, title, offline=True)  # non-Cofacts grading has no network I/O


def _with_tier(item: Dict[str, Any], tier: int) -> Dict[str, Any]:
    out = dict(item)
    out["tier"] = tier
    out["tier_label"] = TIER_LABELS[tier]
    return out


def clean_kb_row(row: Dict[str, Any], checker: CofactsChecker, is_real_claim: Callable[[str], bool]
                 ) -> Tuple[Dict[str, Any], List[str]]:
    """
    Apply rules 1 and 2 to one knowledge-base row.
    Returns (updated field values, triggered rule names).
    """
    label = _label_of(row.get("label_source"))
    raw = row.get("raw_content") or ""
    source_url = row.get("source_url") if not _is_missing(row.get("source_url")) else None
    sources = _as_items(row.get("sources"))
    related_before = _as_items(row.get("related_discussions"))

    # rule 1: backfill + grade
    if not sources and source_url:
        backfill_title = raw[:40]
        if grade_url(source_url, backfill_title, checker) in (1, 2):
            sources = [{"title": backfill_title, "url": source_url}]

    kept: List[Dict[str, Any]] = []
    related: List[Dict[str, Any]] = list(related_before)
    def _key(it: Dict[str, Any]) -> str:
        return it.get("url") or _canon([{k: v for k, v in it.items() if k not in ("tier", "tier_label")}])

    related_keys = {_key(r) for r in related}
    for item in sources:
        url = item.get("url") or ""
        tier = grade_url(url, item.get("title") or "", checker,
                         verdict=item.get("verdict"), prior_tier=_tier_value(item.get("tier")))
        graded = _with_tier(item, tier)
        if tier in (1, 2):
            kept.append(graded)
        elif _key(graded) not in related_keys:
            related.append(graded)
            related_keys.add(_key(graded))

    best = min((s["tier"] for s in kept), default=None)
    source_tier = best if best in (1, 2) else None
    verified = label in DETERMINISTIC_LABELS or source_tier in (1, 2)

    # rule 2: chat fragments / unanswered Cofacts articles are never indexed.
    # Decided BEFORE change detection so the final field values (not rule 1's
    # intermediate verified) are what gets compared with the stored row;
    # otherwise a Tier 1 row with non-claim raw_content re-flags rule 1 forever.
    rule2_applies = False
    if label not in DETERMINISTIC_LABELS:
        not_claim = not is_real_claim(raw)
        unanswered = bool(source_url) and cofacts_status_of(source_url, checker) == STATUS_NO_REPLY
        rule2_applies = not_claim or unanswered

    new = {
        "sources": kept,
        "related_discussions": json.dumps(related, ensure_ascii=False) if related else None,
        "source_tier": source_tier,
        "verified": False if rule2_applies else verified,
        "content_vector": None if rule2_applies else row.get("content_vector"),
    }

    structural_diff = (_canon(kept) != _canon(_as_items(row.get("sources")))
                       or _canon(related) != _canon(related_before)
                       or source_tier != _tier_value(row.get("source_tier")))
    verified_diff = new["verified"] != _bool_value(row.get("verified"))
    vector_diff = _has_vector(row.get("content_vector")) and new["content_vector"] is None

    rules: List[str] = []
    if structural_diff or (verified_diff and not rule2_applies):
        rules.append("rule1")
    if rule2_applies and (verified_diff or vector_diff):
        rules.append("rule2")
    return new, rules


def _row_title(row: Dict[str, Any], limit: int = 30) -> str:
    text = str(row.get("raw_content") or "").replace("\r", " ").replace("\n", " ").strip()
    return text[:limit] + ("..." if len(text) > limit else "")


def _describe_change(row: Dict[str, Any], new: Dict[str, Any]) -> str:
    parts = []
    before_ver = _bool_value(row.get("verified"))
    if before_ver != new["verified"]:
        parts.append(f"verified: {before_ver} -> {new['verified']}")
    before_tier = _tier_value(row.get("source_tier"))
    if before_tier != new["source_tier"]:
        parts.append(f"source_tier: {before_tier} -> {new['source_tier']}")
    before_src = _as_items(row.get("sources"))
    if _canon(before_src) != _canon(new["sources"]):
        parts.append(f"sources: {len(before_src)} -> {len(new['sources'])} (tier tagged)")
    before_rel = _as_items(row.get("related_discussions"))
    after_rel = _as_items(new["related_discussions"])
    if _canon(before_rel) != _canon(after_rel):
        parts.append(f"related_discussions: {len(before_rel)} -> {len(after_rel)}")
    if _has_vector(row.get("content_vector")) and new["content_vector"] is None:
        parts.append("content_vector: set -> None")
    return "; ".join(parts) or "(no change)"


# ──────────────────────────────────────────
# Knowledge-base pass
# ──────────────────────────────────────────
def run_kb(data_dir: Path, checker: CofactsChecker, apply: bool) -> Dict[str, Any]:
    import pandas as pd

    from app.services.news_fetcher import _is_real_claim

    path = data_dir / KB_FILE
    result: Dict[str, Any] = {"lines": [], "counts": {}, "backup": None}
    lines = result["lines"]
    lines.append("=== 知識庫 knowledge_base.parquet（規則 1、2） ===")
    if not path.exists():
        lines.append(f"檔案不存在：{path}")
        lines.append("知識庫總筆數：0")
        lines.append("label_source=rule 被降級：0 筆")
        return result

    df = pd.read_parquet(path)
    for col, default in (("label_source", "ai"), ("source_tier", None),
                         ("verified", None), ("related_discussions", None)):
        if col not in df.columns:
            df[col] = default

    rule1_rows, rule2_rows = [], []
    affected: set = set()
    updates: Dict[Any, Dict[str, Any]] = {}
    for idx, rec in df.iterrows():
        row = rec.to_dict()
        new, rules = clean_kb_row(row, checker, _is_real_claim)
        updates[idx] = new
        entry = (row, new)
        if "rule1" in rules:
            rule1_rows.append(entry)
        if "rule2" in rules:
            rule2_rows.append(entry)
        if rules:
            affected.add(idx)

    after_verified = [u["verified"] for u in updates.values()]
    rule_downgraded = sum(
        1 for idx, u in updates.items()
        if _label_of(df.at[idx, "label_source"]) == "rule" and u["verified"] is False
    )
    det_downgraded = sum(
        1 for idx, u in updates.items()
        if _label_of(df.at[idx, "label_source"]) in DETERMINISTIC_LABELS and u["verified"] is False
    )

    counts = result["counts"]
    counts.update({
        "total": len(df),
        "rule1": len(rule1_rows),
        "rule2": len(rule2_rows),
        "affected": len(affected),
        "verified_true": sum(1 for v in after_verified if v),
        "verified_false": sum(1 for v in after_verified if not v),
        "rule_downgraded": rule_downgraded,
    })

    lines.append(f"知識庫總筆數：{len(df)}")
    lines.append(f"規則 1（來源補齊／分級／Tier 3 移至 related_discussions）影響：{len(rule1_rows)} 筆")
    lines.append(f"規則 2（非真實主張或 Cofacts 無回覆 → verified=false、不索引）影響：{len(rule2_rows)} 筆")
    lines.append(f"清洗後 verified：true={counts['verified_true']} false={counts['verified_false']}")
    lines.append(f"label_source=rule 被降級：{rule_downgraded} 筆")
    lines.append(f"label_source in (rule, gold, admin) 被降級：{det_downgraded} 筆")

    # QA-5 evidence: how many deterministic rows the check actually examined, and
    # where the verified=false rows come from (so a vacuous 0 is visible as such).
    label_counts: Dict[str, int] = {}
    for idx in df.index:
        lab = _label_of(df.at[idx, "label_source"])
        label_counts[lab] = label_counts.get(lab, 0) + 1
    det_examined = sum(label_counts.get(l, 0) for l in DETERMINISTIC_LABELS)
    counts["label_counts"] = dict(label_counts)
    counts["deterministic_examined"] = det_examined
    lines.append(
        "QA-5 檢核範圍：label_source "
        + ", ".join(f"{l}={label_counts.get(l, 0)}" for l in DETERMINISTIC_LABELS)
        + f"（共 {det_examined} 筆受保護）；其餘 "
        + ", ".join(f"{k}={v}" for k, v in sorted(label_counts.items()) if k not in DETERMINISTIC_LABELS)
    )
    if det_examined == 0:
        lines.append("QA-5 注意：本知識庫沒有任何 rule/gold/admin 列（缺 label_source 欄位時一律視為 ai），"
                     "上面的「被降級：0 筆」為空集合檢核，不能證明規則索引的主張未被降級；"
                     "D-05 前請負責人決定舊的規則索引列如何處理（TIER1_DOMAINS 或 label_source 回填）")

    # Every row that ends verified=false, grouped by source_url domain (the stored
    # value is often a schema default, so "changed to false" alone can hide them).
    false_by_domain: Dict[str, List[int]] = {}  # domain -> [total, was not false before]
    for idx, u in updates.items():
        if u["verified"] is False:
            url = df.at[idx, "source_url"]
            dom = _domain_of(url) if not _is_missing(url) and url else "(無 source_url)"
            slot = false_by_domain.setdefault(dom, [0, 0])
            slot[0] += 1
            if _bool_value(df.at[idx, "verified"]) is not False:
                slot[1] += 1
    counts["downgraded_by_domain"] = {d: v[0] for d, v in false_by_domain.items()}
    lines.append(f"清洗後 verified=false 依 source_url 網域分組（總數／其中原本非 false）：共 "
                 f"{sum(v[0] for v in false_by_domain.values())} 筆")
    for dom, (n, changed) in sorted(false_by_domain.items(), key=lambda kv: (-kv[1][0], kv[0])):
        lines.append(f"  {dom}: {n} / {changed}")
    if not false_by_domain:
        lines.append("  (無)")
    lines.append("")

    for name, rows in (("規則 1", rule1_rows), ("規則 2", rule2_rows)):
        lines.append(f"--- {name} 逐筆（id | title | before -> after） ---")
        if not rows:
            lines.append("(無)")
        for row, new in rows:
            lines.append(f"{row.get('id')} | {_row_title(row)} | {_describe_change(row, new)}")
        lines.append("")

    if apply:
        backup = path.with_name(f"{KB_FILE}.bak-{datetime.now():%Y%m%d}")
        if not backup.exists():
            shutil.copy2(path, backup)
        result["backup"] = str(backup)
        for col in ("sources", "related_discussions", "source_tier", "verified", "content_vector"):
            df[col] = pd.Series([updates[idx][col] for idx in df.index], index=df.index, dtype=object)
        df["verified"] = df["verified"].astype(bool)
        if "ai_analysis" in df.columns:
            df["ai_analysis"] = [
                ({**a, "sources": updates[idx]["sources"]} if isinstance(a, dict) else a)
                for idx, a in zip(df.index, df["ai_analysis"])
            ]
        df.to_parquet(path, index=False)
        lines.append(f"[apply] 已寫入 {path}（備份 {backup.name}）")
    return result


# ──────────────────────────────────────────
# Trending pass (rules 3, 4)
# ──────────────────────────────────────────
GOOGLE_CACHE_KEY = "_google_news"
RESOLVE_TIMEOUT = 10
TRENDING_NEW_COLUMNS = (
    ("platform", "VARCHAR(20)"), ("post_id", "VARCHAR(64)"), ("label_source", "VARCHAR(10)"),
    ("result_id", "VARCHAR(36)"), ("verified", "BOOLEAN"), ("source_tier", "INTEGER"),
)
_GOOGLE_HOST_RE = re.compile(r"(^|\.)google\.[a-z]{2,3}(\.[a-z]{2})?$")


def is_google_url(url: str) -> bool:
    host = _host_of(url or "")
    return bool(host) and bool(_GOOGLE_HOST_RE.search(host))


def is_google_news_url(url: str) -> bool:
    return _host_matches(_host_of(url or ""), ("news.google.com",))


def normalize_title(title: Any) -> str:
    """Dedupe key: unescape entities, NFKC, drop a trailing ' - publisher', keep letters/digits only."""
    text = unicodedata.normalize("NFKC", html.unescape(str(title or ""))).strip().lower()
    text = re.sub(r"\s+-\s+[^-]{1,40}$", "", text)
    return "".join(ch for ch in text if ch.isalnum())


def _domain_of(url: str) -> str:
    host = _host_of(url or "")
    return host[4:] if host.startswith("www.") else host


class GoogleNewsResolver:
    """
    Resolves news.google.com redirect links through safe_url (SSRF-safe, <=3 hops).
    Resolutions to a non-Google host are cached (shared JSON cache, key
    "_google_news") so the owner-reviewed dry-run and the later --apply agree;
    failures (timeout, network error, HTTP >= 400) and "still Google" outcomes are
    retried next run.
    """

    def __init__(self, checker: CofactsChecker):
        self.checker = checker
        self.network_calls = 0

    @property
    def _cache(self) -> Dict[str, Any]:
        entry = self.checker.cache.get(GOOGLE_CACHE_KEY)
        if not isinstance(entry, dict):
            entry = {}
            self.checker.cache[GOOGLE_CACHE_KEY] = entry
        return entry

    def _fetch(self, url: str) -> Tuple[Optional[str], str]:
        from app.config import settings

        old_timeout = settings.CRAWLER_TIMEOUT
        settings.CRAWLER_TIMEOUT = RESOLVE_TIMEOUT
        last_reason = "unknown"
        try:
            for method in ("HEAD", "GET"):
                self.network_calls += 1
                try:
                    resp = safe_get(url, method=method, read_body=False)
                except SafeFetchError as e:
                    last_reason = f"{method} {type(e).__name__}"
                    continue
                if resp.status_code < 400:
                    return resp.url, f"{method} {resp.status_code}"
                last_reason = f"{method} HTTP {resp.status_code}"
        finally:
            settings.CRAWLER_TIMEOUT = old_timeout
        return None, last_reason

    def resolve(self, url: str) -> Tuple[Optional[str], str, str]:
        """-> (final_url or None, reason, origin 'cache'|'query').

        Only a resolution to a non-Google host is cached as definitive. news.google.com
        /rss/articles links answer 200 on Google itself (the hop to the publisher is
        done in JavaScript), so "still Google" is a limitation of this resolver, not a
        final answer: it is retried on every run (and legacy cache entries holding a
        Google final_url are ignored) so a later, better resolver can still succeed.
        """
        cached = self._cache.get(url)
        if (isinstance(cached, dict) and cached.get("final_url")
                and not is_google_url(cached["final_url"])):
            return cached["final_url"], cached.get("reason", ""), "cache"
        if cached is not None:
            self._cache.pop(url, None)  # drop a legacy non-definitive entry
            self.checker.dirty = True
        final, reason = self._fetch(url)
        if final and not is_google_url(final):
            self._cache[url] = {"final_url": final, "reason": reason,
                                "checked_at": datetime.now().isoformat(timespec="seconds")}
            self.checker.dirty = True
        return final, reason, "query"


def _trending_label(value: Any) -> Optional[str]:
    return None if _is_missing(value) or not str(value).strip() else str(value)


def _created_key(row: Dict[str, Any]) -> Tuple[str, str]:
    return (str(row.get("created_at") or "9999"), str(row.get("id")))


def trending_verified(label: Optional[str], tier: int) -> bool:
    if label in DETERMINISTIC_LABELS:
        return True
    return label == "ai" and tier in (1, 2)


def plan_trending(rows: List[Dict[str, Any]], checker: CofactsChecker,
                  resolver: GoogleNewsResolver) -> Dict[str, Any]:
    """Pure planning step (no writes): rule 3 deletions/rewrites, rule 4 field backfill."""
    rows = sorted(rows, key=_created_key)
    new_url: Dict[str, str] = {}
    delete: Dict[str, str] = {}  # id -> reason
    google_lines: List[str] = []
    resolved_ids = set()

    for row in rows:
        url = row.get("source_url") or ""
        if not is_google_news_url(url):
            continue
        final, reason, origin = resolver.resolve(url)
        title = str(row.get("news_title") or "")[:40]
        src = "快取" if origin == "cache" else "查詢"
        src += f", label_source={_trending_label(row.get('label_source'))}, risk_type={row.get('risk_type')}"
        if final and not is_google_url(final):
            new_url[row["id"]] = final
            resolved_ids.add(row["id"])
            google_lines.append(f"{row['id']} | {title} | 解析成功→{final} ({reason}, {src})")
        else:
            why = f"仍為 Google：{final}" if final else f"解析失敗：{reason}"
            delete[row["id"]] = why
            google_lines.append(f"{row['id']} | {title} | 失敗→刪除 ({why}, {src})")

    # dedupe (only groups that involve a rewritten row), earliest created_at wins
    seen_key: Dict[Tuple[str, str], str] = {}
    seen_url: Dict[str, str] = {}
    dedupe_lines: List[str] = []
    for row in rows:
        rid = row["id"]
        if rid in delete:
            continue
        url = new_url.get(rid, row.get("source_url") or "")
        norm = normalize_title(row.get("news_title"))
        key = (norm, _domain_of(url)) if norm else None
        keeper = seen_url.get(url) if url else None
        if keeper is None and key is not None:
            keeper = seen_key.get(key)
        if keeper is not None and (rid in resolved_ids or keeper in resolved_ids):
            delete[rid] = f"與 {keeper} 重複（標題＋網域或網址相同，保留較早者）"
            dedupe_lines.append(f"{rid} | {str(row.get('news_title') or '')[:40]} | 去重→刪除（保留 {keeper}）")
            continue
        if url:
            seen_url.setdefault(url, rid)
        if key is not None:
            seen_key.setdefault(key, rid)

    rule3_ids = set(delete) | set(new_url)

    updates: Dict[str, Dict[str, Any]] = {}
    rule4_lines: List[str] = []
    for row in rows:
        rid = row["id"]
        if rid in delete:
            continue
        url = new_url.get(rid, row.get("source_url") or "")
        title = str(row.get("news_title") or "")
        tier = grade_url(url, title, checker, prior_tier=_tier_value(row.get("source_tier")))
        verified = trending_verified(_trending_label(row.get("label_source")), tier)
        before_v, before_t = _bool_value(row.get("verified")), _tier_value(row.get("source_tier"))
        if before_v != verified or before_t != tier:
            updates[rid] = {"verified": verified, "source_tier": tier}
            rule4_lines.append(
                f"{rid} | {title[:30]} | label_source={_trending_label(row.get('label_source'))}; "
                f"verified: {before_v} -> {verified}; source_tier: {before_t} -> {tier}"
            )

    return {
        "rows": rows, "new_url": new_url, "delete": delete, "updates": updates,
        "rule3_ids": rule3_ids, "google_lines": google_lines,
        "dedupe_lines": dedupe_lines, "rule4_lines": rule4_lines,
    }


def _ensure_trending_columns(con: sqlite3.Connection) -> None:
    have = {r[1] for r in con.execute("PRAGMA table_info(fact_check_records)")}
    for name, ddl in TRENDING_NEW_COLUMNS:
        if name not in have:
            con.execute(f"ALTER TABLE fact_check_records ADD COLUMN {name} {ddl}")


def run_trending(data_dir: Path, checker: CofactsChecker, apply: bool,
                 resolver: Optional[GoogleNewsResolver] = None) -> Dict[str, Any]:
    path = data_dir / DB_FILE
    result: Dict[str, Any] = {"lines": [], "counts": {}, "backup": None}
    lines = result["lines"]
    lines.append("=== 熱門 fact_check_records（規則 3、4） ===")
    if not path.exists():
        lines.append(f"檔案不存在：{path}")
        lines.append("熱門總筆數：0")
        return result

    resolver = resolver or GoogleNewsResolver(checker)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(fact_check_records)")}
        wanted = ["id", "source_url", "news_title", "risk_type", "created_at",
                  "label_source", "verified", "source_tier"]
        select = ", ".join(c if c in cols else f"NULL AS {c}" for c in wanted)
        rows = [dict(r) for r in con.execute(f"SELECT {select} FROM fact_check_records")]
    finally:
        con.close()

    plan = plan_trending(rows, checker, resolver)
    google_total = len(plan["google_lines"])
    resolved = len(plan["new_url"])
    deleted = len(plan["delete"])
    remaining = len(rows) - deleted
    after_true = sum(
        1 for r in plan["rows"] if r["id"] not in plan["delete"]
        and plan["updates"].get(r["id"], {"verified": bool(_bool_value(r.get("verified")))})["verified"]
    )
    rule_downgraded = sum(1 for r in plan["rows"]
                          if _trending_label(r.get("label_source")) == "rule"
                          and plan["updates"].get(r["id"], {}).get("verified") is False)

    # Deletions are not "downgrades", so count them separately: a deleted
    # deterministic row must be visible next to the QA-5 downgrade line.
    deleted_by_label: Dict[str, Dict[str, int]] = {}
    for r in plan["rows"]:
        if r["id"] in plan["delete"]:
            lab = _trending_label(r.get("label_source")) or "(無)"
            slot = deleted_by_label.setdefault(lab, {})
            risk = str(r.get("risk_type") or "(無)")
            slot[risk] = slot.get(risk, 0) + 1
    rule_deleted = sum(deleted_by_label.get("rule", {}).values())
    det_deleted = sum(sum(deleted_by_label.get(l, {}).values()) for l in DETERMINISTIC_LABELS)

    counts = result["counts"]
    counts.update({
        "total": len(rows), "google_news": google_total, "resolved": resolved,
        "deleted": deleted, "remaining": remaining,
        "rule3": len(plan["rule3_ids"]), "rule4": len(plan["updates"]),
        "verified_true": after_true, "rule_downgraded": rule_downgraded,
        "rule_deleted": rule_deleted, "deterministic_deleted": det_deleted,
        "deleted_by_label": {k: dict(v) for k, v in deleted_by_label.items()},
    })
    lines.append(f"熱門總筆數：{len(rows)}")
    lines.append(f"規則 3（news.google.com 轉址解析／去重／刪除）影響：{counts['rule3']} 筆"
                 f"（Google News {google_total} 筆：解析成功 {resolved}；刪除合計 {deleted}，含去重）")
    lines.append(f"規則 4（verified／source_tier 回填）影響：{counts['rule4']} 筆")
    lines.append(f"清洗後熱門筆數：{remaining}；verified=true {after_true}")
    lines.append(f"熱門 label_source=rule 被降級：{rule_downgraded} 筆")
    lines.append(f"熱門 label_source=rule 被刪除：{rule_deleted} 筆")
    lines.append(f"熱門 label_source in (rule, gold, admin) 被刪除：{det_deleted} 筆")
    lines.append(f"熱門刪除依 label_source／risk_type 分組：共 {deleted} 筆")
    for lab, risks in sorted(deleted_by_label.items(), key=lambda kv: (-sum(kv[1].values()), kv[0])):
        detail = ", ".join(f"{k}={v}" for k, v in sorted(risks.items()))
        lines.append(f"  {lab}: {sum(risks.values())}（{detail}）")
    if not deleted_by_label:
        lines.append("  (無)")
    if det_deleted:
        lines.append("注意（D-05 前需負責人決定）：規則 3 會刪除 label_source=rule/gold/admin 的列。"
                     "news.google.com/rss/articles 連結在 Google 端回 200、轉址靠 JavaScript，"
                     "HEAD/GET 無法解析出原始網址，所以這些列一律落入「仍為 Google→刪除」。"
                     "選項：(a) 接受熱門筆數減少；(b) 先加入能解碼 Google News article id 的解析器再跑。"
                     "「仍為 Google」的結果不寫入快取，改用新解析器後重跑會重新嘗試。")
    lines.append("")
    lines.append("--- 規則 3 Google News 逐筆結論（id | title | 結論） ---")
    lines += plan["google_lines"] or ["(無)"]
    lines.append("--- 規則 3 去重逐筆 ---")
    lines += plan["dedupe_lines"] or ["(無)"]
    lines.append("")
    lines.append("--- 規則 4 逐筆（id | title | before -> after） ---")
    lines += plan["rule4_lines"] or ["(無)"]
    lines.append("")

    if apply:
        backup = path.with_name(f"{DB_FILE}.bak-{datetime.now():%Y%m%d}")
        if not backup.exists():
            shutil.copy2(path, backup)
        result["backup"] = str(backup)
        con = sqlite3.connect(path)
        try:
            with con:
                _ensure_trending_columns(con)
                for rid in plan["delete"]:
                    con.execute("DELETE FROM fact_check_records WHERE id = ?", (rid,))
                for rid, url in plan["new_url"].items():
                    if rid not in plan["delete"]:
                        con.execute("UPDATE fact_check_records SET source_url = ? WHERE id = ?", (url, rid))
                for rid, u in plan["updates"].items():
                    con.execute(
                        "UPDATE fact_check_records SET verified = ?, source_tier = ? WHERE id = ?",
                        (1 if u["verified"] else 0, u["source_tier"], rid),
                    )
        finally:
            con.close()
        lines.append(f"[apply] 已寫入 {path}（備份 {backup.name}）")
    return result


def cofacts_lines(checker: CofactsChecker) -> List[str]:
    lines = ["=== Cofacts 文章查詢結論 ==="]
    seen = checker.seen
    tally: Dict[str, int] = {}
    for aid in sorted(seen):
        info = seen[aid]
        text = STATUS_TEXT.get(info["status"], info["status"])
        tally[text] = tally.get(text, 0) + 1
        lines.append(f"{aid} | {text} | {info['url']} | {'快取' if info['origin'] == 'cache' else '查詢'}")
    if not seen:
        lines.append("(無 Cofacts 來源)")
    lines.append("合計：" + (", ".join(f"{k}={v}" for k, v in sorted(tally.items())) or "0")
                 + f"；本次網路查詢 {checker.network_calls} 次")
    return lines


def _safe_print(text: str) -> None:
    enc = sys.stdout.encoding or "utf-8"
    sys.stdout.write(text.encode(enc, errors="replace").decode(enc, errors="replace") + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FR-18 source cleanup (dry-run by default).")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", dest="apply", action="store_false", default=False,
                      help="report only (default)")
    mode.add_argument("--apply", dest="apply", action="store_true",
                      help="back up then write changes (owner sign-off required)")
    parser.add_argument("--only", choices=("kb", "trending"), default=None)
    parser.add_argument("--retry-cofacts", action="store_true",
                        help="re-query cached Cofacts lookups that timed out or errored")
    parser.add_argument("--data-dir", default=str(ROOT / "data"))
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    data_dir = Path(args.data_dir).resolve()
    checker = CofactsChecker(data_dir / CACHE_FILE, retry_failed=args.retry_cofacts)

    mode = "APPLY" if args.apply else "DRY-RUN"
    lines = [
        f"FR-18 clean_sources_2026_09 report ({mode})",
        f"generated: {datetime.now().isoformat(timespec='seconds')}",
        f"data dir: {data_dir}",
        "",
    ]
    impact: Dict[str, int] = {}
    if args.only in (None, "kb"):
        kb = run_kb(data_dir, checker, apply=args.apply)
        lines += kb["lines"]
        impact.update({k: kb["counts"].get(k, 0) for k in ("rule1", "rule2")})
    if args.only in (None, "trending"):
        tr = run_trending(data_dir, checker, apply=args.apply)
        lines += tr["lines"]
        impact.update({k: tr["counts"].get(k, 0) for k in ("rule3", "rule4")})
    lines += cofacts_lines(checker)
    lines.append("")
    lines.append("各規則影響筆數：" + ", ".join(f"{k}={v}" for k, v in sorted(impact.items())))
    checker.save()

    report = "\n".join(lines) + "\n"
    report_path = data_dir / REPORT_FILE
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    summary = [l for l in lines if not l.startswith(("---",)) and " | " not in l]
    _safe_print("\n".join(summary))
    _safe_print(f"[report] {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
