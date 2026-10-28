"""news取り込み(ワーカー・API・マイグレーション)のテスト。AWS不要。

実行: python -m pytest tests/
"""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workers import news_ingest as w  # noqa: E402

GOOD = {
    "schema_version": 1,
    "item_id": "a" * 64,
    "source": "fsa",
    "category": "regulation",
    "title": "貸金業法施行規則の改正",
    "url": "https://www.fsa.go.jp/news/x.html",
    "summary": "",
    "published_at": "2026-08-06T09:30:00Z",
    "fetched_at": "2026-10-28T00:00:00Z",
}


@pytest.fixture
def db(tmp_path):
    """migrate.py で実際にテーブルを作る(既存テーブルのある状態を再現)。"""
    path = tmp_path / "nokosu.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE logs (id INTEGER PRIMARY KEY, content TEXT, tag TEXT, project TEXT, created_at DATETIME, updated_at DATETIME)")
    conn.commit(); conn.close()
    env = {**os.environ, "DB_PATH": str(path)}
    out = subprocess.run([sys.executable, "migrate.py"], cwd=ROOT, env=env, capture_output=True, text=True, check=True)
    assert "news_itemsテーブルを作成しました" in out.stdout
    # 2回目は冪等
    out2 = subprocess.run([sys.executable, "migrate.py"], cwd=ROOT, env=env, capture_output=True, text=True, check=True)
    assert "既に存在します" in out2.stdout
    return path


@pytest.mark.parametrize("patch", [
    {"schema_version": 2},
    {"item_id": "xyz"},
    {"source": "FSA!"},
    {"url": "javascript:alert(1)"},
    {"url": "ftp://example.com/a"},
    {"title": ""},
    {"title": "あ" * 301},
    {"fetched_at": None},
    {"published_at": "2026/08/06"},
])
def test_validate_rejects(patch):
    with pytest.raises(w.InvalidMessage):
        w.validate(json.dumps({**GOOD, **patch}))


def test_validate_rejects_non_json():
    with pytest.raises(w.InvalidMessage):
        w.validate("not json")


def test_validate_ok_and_strips_control_chars():
    row = w.validate(json.dumps({**GOOD, "title": "a\u0007b\nc"}))
    assert row["title"] == "a b c"
    assert row["published_at"] == "2026-08-06 09:30:00.000000"


class FakeSqs:
    def __init__(self, bodies):
        self.batches = [[{"MessageId": str(i), "ReceiptHandle": f"rh{i}", "Body": b} for i, b in enumerate(bodies)]]
        self.deleted = []

    def receive_message(self, **kw):
        return {"Messages": self.batches.pop(0)} if self.batches else {}

    def delete_message_batch(self, QueueUrl, Entries):
        self.deleted += [e["Id"] for e in Entries]
        return {"Successful": Entries, "Failed": []}


def test_run_saves_dedupes_and_keeps_invalid(db):
    bodies = [json.dumps(GOOD), json.dumps(GOOD), json.dumps({**GOOD, "url": "javascript:x"})]
    sqs = FakeSqs(bodies)
    conn = sqlite3.connect(db)
    stats = w.run(sqs, conn, "q")
    conn.close()
    assert stats == {"received": 3, "saved": 1, "duplicate": 1, "invalid": 1}
    assert sqs.deleted == ["0", "1"]  # 不正なものは削除しない(DLQへ回す)
    n = sqlite3.connect(db).execute("SELECT COUNT(*) FROM news_items").fetchone()[0]
    assert n == 1


def test_api_reads_worker_rows(db, monkeypatch):
    """ワーカーが書いた行を、Flask(SQLAlchemy)側が正しく読めること。"""
    conn = sqlite3.connect(db)
    w.save(conn, w.validate(json.dumps(GOOD)))
    conn.commit(); conn.close()

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    import importlib
    import config
    importlib.reload(config)
    import app as app_module
    importlib.reload(app_module)
    client = app_module.create_app().test_client()

    res = client.get("/api/news?unread=1")
    assert res.status_code == 200
    items = res.get_json()
    assert len(items) == 1
    assert items[0]["published_at"] == "2026-08-06T09:30:00Z"
    assert items[0]["is_read"] is False

    nid = items[0]["id"]
    assert client.patch(f"/api/news/{nid}/read", json={"is_read": "yes"}).status_code == 400
    assert client.patch(f"/api/news/{nid}/read", json={"is_read": True}).status_code == 200
    assert client.get("/api/news?unread=1").get_json() == []
    assert client.get("/api/news?category=BAD!").status_code == 400
    assert client.patch("/api/news/9999/read", json={"is_read": True}).status_code == 404
