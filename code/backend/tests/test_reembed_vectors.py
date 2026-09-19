"""scripts/reembed_vectors.py（DEF-05）：只重算維度不對的向量。離線、零 API 呼叫。"""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("reembed_vectors", ROOT / "scripts" / "reembed_vectors.py")
reembed_vectors = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reembed_vectors)


def _kb():
    return pd.DataFrame({
        "id": ["ok", "old768", "old3072", "none", "blank"],
        "raw_content": ["a", "b", "c", "d", "  "],
        "content_vector": [np.ones(1536), np.ones(768), np.ones(3072), None, np.ones(768)],
        "verified": [True, True, False, True, True],
    })


def test_only_wrong_dimension_rows_are_selected():
    todo = reembed_vectors.rows_to_fix(_kb(), 1536)
    assert todo["id"].tolist() == ["old768", "old3072", "blank"]


def test_reembed_skips_blank_text_and_bad_embeddings():
    calls = []

    def embed(text):
        calls.append(text)
        return [0.5] * 1536 if text == "b" else [0.5] * 768      # 第二筆回傳的維度仍然不對

    fixed = reembed_vectors.reembed(_kb(), embed, 1536)
    assert calls == ["b", "c"]                                  # 空白內容不呼叫 API
    assert list(fixed) == ["old768"] and len(fixed["old768"]) == 1536


def test_apply_local_rewrites_only_fixed_rows_and_keeps_a_backup(tmp_path):
    path = tmp_path / "knowledge_base.parquet"
    _kb().to_parquet(path)
    changed = reembed_vectors.apply_local(path, {"old768": [0.25] * 1536})
    assert changed == 1
    after = pd.read_parquet(path).set_index("id")
    assert len(after.loc["old768", "content_vector"]) == 1536
    assert len(after.loc["old3072", "content_vector"]) == 3072   # 沒有新向量的列不動
    assert len(after.loc["ok", "content_vector"]) == 1536
    assert len(list(tmp_path.glob("knowledge_base.parquet.bak-*"))) == 1
    assert reembed_vectors.rows_to_fix(pd.read_parquet(path), 1536)["id"].tolist() == ["old3072", "blank"]
