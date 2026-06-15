"""
マイグレーションスクリプト
実行: python migrate.py
"""
import sqlite3
import os

DB_PATH = os.environ.get("DB_PATH") or os.path.join(
    os.path.dirname(__file__), "instance", "nokosu.db"
)
# /opt/nokosu/data 配下の場合も考慮
if not os.path.exists(DB_PATH):
    DB_PATH = "/opt/nokosu/data/nokosu.db"

print(f"DB: {DB_PATH}")

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

# ── 既存マイグレーション（冪等） ──────────────────────────────

# statusカラム
cur.execute("PRAGMA table_info(logs)")
columns = [row[1] for row in cur.fetchall()]
if "status" not in columns:
    cur.execute("ALTER TABLE logs ADD COLUMN status TEXT NOT NULL DEFAULT '検討中'")
    print("✅ statusカラムを追加しました")
else:
    print("ℹ️  statusカラムは既に存在します")

# ai_contextsテーブル
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ai_contexts'")
if not cur.fetchone():
    cur.execute("""
        CREATE TABLE ai_contexts (
            id INTEGER NOT NULL,
            log_id INTEGER NOT NULL,
            question TEXT,
            answer TEXT,
            suggestion TEXT,
            created_at DATETIME NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(log_id) REFERENCES logs (id)
        )
    """)
    print("✅ ai_contextsテーブルを作成しました")
else:
    print("ℹ️  ai_contextsテーブルは既に存在します")

# ── 新規マイグレーション ──────────────────────────────────────

# log_relationsテーブル
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='log_relations'")
if not cur.fetchone():
    cur.execute("""
        CREATE TABLE log_relations (
            id INTEGER NOT NULL,
            log_id INTEGER NOT NULL,
            related_log_id INTEGER NOT NULL,
            note VARCHAR(200) DEFAULT '',
            created_at DATETIME NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(log_id) REFERENCES logs (id),
            FOREIGN KEY(related_log_id) REFERENCES logs (id),
            UNIQUE (log_id, related_log_id)
        )
    """)
    print("✅ log_relationsテーブルを作成しました")
else:
    print("ℹ️  log_relationsテーブルは既に存在します")

conn.commit()
conn.close()
print("✅ マイグレーション完了")