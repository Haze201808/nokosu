"""
DBマイグレーション: statusカラムの追加
実行方法:
  ローカル: python migrate.py
  EC2:      sudo /opt/nokosu/.venv/bin/python /opt/nokosu/migrate.py
"""
import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()

db_url = os.environ.get("DATABASE_URL", "sqlite:///nokosu.db")

# sqlite:/// (相対) と sqlite://// (絶対) どちらにも対応
if db_url.startswith("sqlite:////"):
    db_path = "/" + db_url[len("sqlite:////"):]
elif db_url.startswith("sqlite:///"):
    # 相対パスの場合はinstance/配下を探す
    rel = db_url[len("sqlite:///"):]
    db_path = os.path.join(os.path.dirname(__file__), "instance", rel)
else:
    db_path = db_url

print(f"DB: {db_path}")

conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.execute("PRAGMA table_info(logs)")
columns = [row[1] for row in cur.fetchall()]

if "status" not in columns:
    cur.execute("ALTER TABLE logs ADD COLUMN status TEXT NOT NULL DEFAULT '検討中'")
    conn.commit()
    print("✅ statusカラムを追加しました")
else:
    print("ℹ️  statusカラムは既に存在します")

conn.close()

# ai_contextsテーブルを追加
conn2 = sqlite3.connect(db_path)
cur2 = conn2.cursor()
cur2.execute("""
    CREATE TABLE IF NOT EXISTS ai_contexts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        log_id INTEGER NOT NULL REFERENCES logs(id),
        question TEXT,
        answer TEXT,
        suggestion TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
""")
conn2.commit()
print("✅ ai_contextsテーブルを確認/作成しました")
conn2.close()