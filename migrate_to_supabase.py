import sqlite3
import psycopg2
import os

SQLITE_PATH = "instance/ias_machine_v2.db"
PG_URL = os.environ.get("DATABASE_URL")
if not PG_URL:
    print("ERROR: DATABASE_URL not set.")
    exit(1)

PG_URL = PG_URL.replace("postgresql+psycopg2://", "postgresql://")

# Columns that need 0/1 → False/True conversion
BOOL_COLS = {"ocr_used", "correct"}

TABLES = [
    "book", "page", "question", "question_source", "answer", "student_answer",
    "news_article", "interview_transcript", "interview_qa",
    "mock_test", "mock_item", "exam_sim", "exam_sim_question",
    "study_plan", "topper"
]

print("Connecting to SQLite...")
sq = sqlite3.connect(SQLITE_PATH)
sq.row_factory = sqlite3.Row
sq_cur = sq.cursor()

print("Connecting to Postgres...")
pg = psycopg2.connect(PG_URL)
pg_cur = pg.cursor()

# Clear existing partial data so we start fresh
for tbl in reversed(TABLES):
    try:
        pg_cur.execute(f'DELETE FROM "{tbl}"')
    except Exception:
        pg.rollback()
pg.commit()
print("Cleared any partial data in Postgres.")

for tbl in TABLES:
    try:
        sq_cur.execute(f"SELECT * FROM {tbl}")
        rows = sq_cur.fetchall()
    except sqlite3.OperationalError:
        print(f"  {tbl}: skipped (not in SQLite)")
        continue

    if not rows:
        print(f"  {tbl}: 0 rows")
        continue

    cols = [d[0] for d in sq_cur.description]
    placeholders = ",".join(["%s"] * len(cols))
    col_list = ",".join([f'"{c}"' for c in cols])
    insert_sql = f'INSERT INTO "{tbl}" ({col_list}) VALUES ({placeholders})'

    inserted = 0
    for row in rows:
        # Convert values
        values = []
        for i, v in enumerate(row):
            cname = cols[i]
            if cname in BOOL_COLS and v is not None:
                values.append(bool(v))
            else:
                values.append(v)

        try:
            pg_cur.execute(insert_sql, tuple(values))
            inserted += 1
        except Exception as e:
            print(f"    skip: {str(e)[:80]}")
            pg.rollback()
            continue
    pg.commit()
    print(f"  {tbl}: {inserted}/{len(rows)} rows migrated")

    # Fix auto-increment sequence
    try:
        pg_cur.execute(
            f"SELECT setval(pg_get_serial_sequence('{tbl}', 'id'), "
            f"COALESCE((SELECT MAX(id) FROM \"{tbl}\"), 1), true)"
        )
        pg.commit()
    except Exception:
        pg.rollback()

sq.close()
pg.close()
print("Migration complete.")