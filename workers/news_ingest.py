"""news-collector の SQS キューから新着を取り込むワーカー。

実行: python -m workers.news_ingest   (systemd timer から1時間ごとに起動)

Flaskアプリをimportせず、sqlite3 で直接書き込む独立プロセスとして動かす。
gunicornの中で動かすとワーカープロセスごとにポーリングが走り、取り合いになるため。

処理の順序(取りこぼし防止のため厳守):
  受信 -> バリデーション -> INSERT OR IGNORE -> COMMIT -> SQSから削除

  - 重複(同じitem_idの再配信)は UNIQUE 制約で無視し、削除だけ行う
  - バリデーションに失敗したメッセージは削除しない。
    可視性タイムアウト後に再配信され、3回でDLQへ移る(=アラームで気づける)

必要な環境変数:
  NEWS_QUEUE_URL      SQSキューURL(シークレットではない。systemdユニットで渡す)
  AWS_DEFAULT_REGION  ap-northeast-1
  DB_PATH             省略時 /opt/nokosu/data/nokosu.db

認証情報はEC2インスタンスロールから自動取得する(キーは持たない)。
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import sys
import urllib.parse
from datetime import datetime, timezone

logger = logging.getLogger("news_ingest")

SCHEMA_VERSION = 1
MAX_BATCHES = 20            # 1回の起動で最大 20 x 10 = 200件
SQLITE_TIMEOUT_SEC = 30     # gunicorn側の書き込みと競合したときの待ち時間
ITEM_ID_RE = re.compile(r"^[0-9a-f]{64}$")
SLUG_RE = re.compile(r"^[a-z0-9_-]{1,32}$")
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
MAX_TITLE, MAX_SUMMARY, MAX_URL = 300, 500, 2048


class InvalidMessage(ValueError):
    pass


def _parse_utc(value, *, required: bool) -> str | None:
    """'YYYY-MM-DDTHH:MM:SSZ' を SQLAlchemy(SQLite)と同じ 'YYYY-MM-DD HH:MM:SS.ffffff' に変換する。"""
    if value is None:
        if required:
            raise InvalidMessage("必須の日時がない")
        return None
    if not isinstance(value, str) or not ISO_RE.match(value):
        raise InvalidMessage(f"日時の形式が不正: {value!r}")
    dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")


def _str(msg: dict, key: str, max_len: int, *, allow_empty=False) -> str:
    v = msg.get(key)
    if not isinstance(v, str):
        raise InvalidMessage(f"{key} が文字列でない")
    v = v.strip()
    if not v and not allow_empty:
        raise InvalidMessage(f"{key} が空")
    if len(v) > max_len:
        raise InvalidMessage(f"{key} が長すぎる({len(v)})")
    # 制御文字を除去(改行・タブは空白に寄せる)
    return "".join(ch if ch.isprintable() else " " for ch in v)


def validate(body: str) -> dict:
    """SQSメッセージ本文を検証し、DBに入れる値を返す。

    [セキュリティ] 収集側(Lambda)でも検証しているが、受信側でも信用せずに再検証する。
    キューに書ける主体が将来増えても、ここで弾けるようにするため。
    """
    try:
        msg = json.loads(body)
    except (json.JSONDecodeError, TypeError) as e:
        raise InvalidMessage(f"JSONでない: {e}") from e
    if not isinstance(msg, dict):
        raise InvalidMessage("オブジェクトでない")
    if msg.get("schema_version") != SCHEMA_VERSION:
        raise InvalidMessage(f"未対応のschema_version: {msg.get('schema_version')!r}")

    item_id = msg.get("item_id")
    if not isinstance(item_id, str) or not ITEM_ID_RE.match(item_id):
        raise InvalidMessage("item_id が不正")
    for key in ("source", "category"):
        if not isinstance(msg.get(key), str) or not SLUG_RE.match(msg[key]):
            raise InvalidMessage(f"{key} が不正")

    url = _str(msg, "url", MAX_URL)
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise InvalidMessage(f"URLのスキームが不正: {url[:50]!r}")  # javascript: 等を拒否

    return {
        "item_id": item_id,
        "source": msg["source"],
        "category": msg["category"],
        "title": _str(msg, "title", MAX_TITLE),
        "url": url,
        "summary": _str(msg, "summary", MAX_SUMMARY, allow_empty=True),
        "published_at": _parse_utc(msg.get("published_at"), required=False),
        "fetched_at": _parse_utc(msg.get("fetched_at"), required=True),
    }


def save(conn: sqlite3.Connection, row: dict) -> bool:
    """保存できたらTrue、重複ならFalse。"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO news_items
          (item_id, source, category, title, url, summary,
           published_at, fetched_at, is_read, created_at)
        VALUES (:item_id, :source, :category, :title, :url, :summary,
                :published_at, :fetched_at, 0, :created_at)
        """,
        {**row, "created_at": now},
    )
    return cur.rowcount == 1


def run(sqs, conn: sqlite3.Connection, queue_url: str) -> dict:
    stats = {"received": 0, "saved": 0, "duplicate": 0, "invalid": 0}
    for _ in range(MAX_BATCHES):
        resp = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=20,      # ロングポーリング
            VisibilityTimeout=300,
        )
        messages = resp.get("Messages", [])
        if not messages:
            break
        stats["received"] += len(messages)

        to_delete = []
        for m in messages:
            try:
                row = validate(m["Body"])
            except InvalidMessage as e:
                # 削除しない -> 再配信 -> 3回でDLQ。本文はログに出さない(外部由来のため)
                logger.warning("不正なメッセージ: id=%s reason=%s", m.get("MessageId"), e)
                stats["invalid"] += 1
                continue
            if save(conn, row):
                stats["saved"] += 1
            else:
                stats["duplicate"] += 1
            to_delete.append({"Id": m["MessageId"], "ReceiptHandle": m["ReceiptHandle"]})

        # COMMITしてから削除する(逆にすると保存失敗時にデータを失う)
        conn.commit()
        if to_delete:
            result = sqs.delete_message_batch(QueueUrl=queue_url, Entries=to_delete)
            for f in result.get("Failed", []):
                # 削除失敗は再配信されるだけ(UNIQUEで重複は防げる)なので警告に留める
                logger.warning("削除失敗: id=%s code=%s", f.get("Id"), f.get("Code"))
    return stats


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    queue_url = os.environ.get("NEWS_QUEUE_URL", "")
    if not re.match(r"^https://sqs\.[a-z0-9-]+\.amazonaws\.com/\d{12}/[\w-]{1,80}$", queue_url):
        logger.error("NEWS_QUEUE_URL が未設定または不正")
        return 2
    db_path = os.environ.get("DB_PATH", "/opt/nokosu/data/nokosu.db")
    if not os.path.exists(db_path):
        logger.error("DBが見つからない: %s", db_path)
        return 2

    import boto3  # テストでboto3なしでも validate/save を検証できるよう遅延import

    sqs = boto3.client("sqs")
    conn = sqlite3.connect(db_path, timeout=SQLITE_TIMEOUT_SEC)
    try:
        stats = run(sqs, conn, queue_url)
    finally:
        conn.close()
    logger.info("完了: %s", stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
