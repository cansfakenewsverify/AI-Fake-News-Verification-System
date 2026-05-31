"""
Quick DB inspector. Run from backend folder:
    venv\\Scripts\\python scripts/check_db.py
"""
import sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import os
os.chdir(ROOT)

from app.database_sql import SessionLocal, init_sql_db
from app.models.fact_check_record import FactCheckRecord

init_sql_db()
db = SessionLocal()
try:
    records = db.query(FactCheckRecord).order_by(FactCheckRecord.created_at.desc()).all()
    print(f"\n=== SQLite: {len(records)} records ===\n")
    for i, r in enumerate(records, 1):
        print(f"[{i}] {r.risk_type or 'PENDING':8s} | score={r.ai_score} | {r.news_title[:50] if r.news_title else '(no title)'}")
        print(f"     URL: {r.source_url}")
        print(f"     AI summary: {r.ai_summary or '(none)'}")
        print(f"     Created: {r.created_at}")
        print()
finally:
    db.close()

# Also check Pandas knowledge base
from app.services.pandas_store import PandasStore
ps = PandasStore()
df = ps.get_all_records()
print(f"\n=== Parquet knowledge_base: {len(df)} records ===\n")
if len(df) > 0:
    cols = ['data_type', 'risk_type', 'category', 'confidence_score']
    cols = [c for c in cols if c in df.columns]
    print(df[cols].to_string())
