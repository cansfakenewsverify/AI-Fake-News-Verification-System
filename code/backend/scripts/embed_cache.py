"""
本機的 embedding 快取（票 B-52）：重算知識庫、校準門檻、重產話術原型共用，同一段文字只算一次。

- 鍵是「送出去的文字」的 SHA-256（送出前和 factcheck_corpus.embed_batch 一樣截到 EMBED_MAX_CHARS），
  **不存文字本身**（Cofacts 訊息可能含個資）；向量存 float32。
- 每個模型一個檔：data/embed_cache/<模型>.parquet（gitignored）。換模型不會混到別的向量。
- 每算完幾批就存檔：中途中斷（Ctrl+C、網路斷）重跑會從沒算過的接著算。
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

BACKEND = Path(__file__).resolve().parents[1]
CACHE_DIR = BACKEND / "data" / "embed_cache"

EmbedFn = Callable[[List[str]], Tuple[list, int]]


def _say(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(msg.encode(enc, "replace").decode(enc, "replace"), flush=True)


def cache_path(model: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", model.strip()) or "model"
    return CACHE_DIR / f"{safe}.parquet"


class EmbedCache:
    def __init__(self, model: str, path: Optional[Path] = None, embed: Optional[EmbedFn] = None,
                 batch: Optional[int] = None, max_chars: Optional[int] = None, dim: Optional[int] = None) -> None:
        from app.services import factcheck_corpus as fc

        self.model = model
        self.path = Path(path) if path else cache_path(model)
        self._embed = embed or fc.embed_batch
        self.batch = int(batch or fc.EMBED_BATCH)
        self.max_chars = int(max_chars or fc.EMBED_MAX_CHARS)
        self.dim = dim
        self._vectors: Dict[str, np.ndarray] = {}
        self._dirty = 0
        if self.path.exists():
            df = pd.read_parquet(self.path)
            self._vectors = {str(k): np.asarray(v, dtype=np.float32) for k, v in zip(df["key"], df["vector"])}

    def __len__(self) -> int:
        return len(self._vectors)

    def key(self, text: str) -> str:
        return hashlib.sha256(str(text)[: self.max_chars].encode("utf-8")).hexdigest()

    def _usable(self, vector: Optional[np.ndarray]) -> bool:
        if vector is None or vector.ndim != 1 or not len(vector):
            return False
        if self.dim is not None and vector.shape[0] != self.dim:
            return False
        return bool(np.isfinite(vector).all() and np.any(vector))

    def known(self, text: str) -> Optional[np.ndarray]:
        vector = self._vectors.get(self.key(text))
        return vector if self._usable(vector) else None

    def missing(self, texts: Iterable[str]) -> List[str]:
        """還沒算過的文字（去重、保留順序；空白文字不算）。"""
        seen, out = set(), []
        for text in texts:
            if not str(text or "").strip():
                continue
            k = self.key(text)
            if k in seen or self._usable(self._vectors.get(k)):
                continue
            seen.add(k)
            out.append(str(text))
        return out

    def save(self) -> None:
        if not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp.parquet")
        pd.DataFrame({"key": list(self._vectors), "vector": list(self._vectors.values())}).to_parquet(tmp, index=False)
        tmp.replace(self.path)
        self._dirty = 0

    def ensure(self, texts: Sequence[str], save_every: int = 20, label: str = "") -> int:
        """把還沒算過的文字算好（每批 self.batch 筆）；回傳這次新算的筆數。embedding 一直失敗時例外往外丟（已算的有存）。"""
        todo = self.missing(texts)
        if not todo:
            return 0
        batches = -(-len(todo) // self.batch)
        _say(f"{label}要算 {len(todo)} 筆，{batches} 批（每批 {self.batch} 筆）")
        done = 0
        try:
            for b in range(batches):
                chunk = todo[b * self.batch:(b + 1) * self.batch]
                vectors, _ = self._embed(chunk)
                for text, vector in zip(chunk, vectors):
                    arr = None if vector is None else np.asarray(vector, dtype=np.float32)
                    if self._usable(arr):
                        self._vectors[self.key(text)] = arr
                        self._dirty += 1
                        done += 1
                if (b + 1) % save_every == 0:
                    self.save()
                    _say(f"  {min((b + 1) * self.batch, len(todo))}／{len(todo)}")
        finally:
            self.save()
        skipped = len(todo) - done
        _say(f"{label}新算 {done} 筆" + (f"；{skipped} 筆回傳的向量不能用（維度不對或全是 0），略過" if skipped else ""))
        return done

    def matrix(self, texts: Sequence[str]) -> Tuple[np.ndarray, np.ndarray]:
        """（有向量的列位置, 向量矩陣）；沒算到的文字略過。"""
        rows, vecs = [], []
        for i, text in enumerate(texts):
            vector = self.known(text)
            if vector is not None:
                rows.append(i)
                vecs.append(vector)
        if not vecs:
            return np.zeros(0, dtype=int), np.zeros((0, self.dim or 0), dtype=np.float32)
        return np.asarray(rows, dtype=int), np.stack(vecs)
