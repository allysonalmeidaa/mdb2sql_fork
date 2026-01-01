import duckdb
from pathlib import Path

DB_PATH = (
    Path(__file__).resolve().parents[1]
    / "interface"
    / "uploads"
    / "2025-11-05_DB4.duckdb"
)

con = duckdb.connect(str(DB_PATH))

query = """
SELECT table_name, COUNT(*) AS c
FROM _fulltext
WHERE content_norm LIKE '%aux%'
  AND content_norm LIKE '%unidad%'
GROUP BY table_name
ORDER BY c DESC
LIMIT 50;
"""

rows = con.execute(query).fetchall()

print(f"DB: {DB_PATH}")
print("Top tables with 'aux' AND 'unidad' in content_norm:")
for table_name, c in rows:
    print(f"{table_name}: {c}")
