from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, Response
from models.database import db, NewsItem
import re

news_bp = Blueprint("news", __name__)

SLUG_RE = re.compile(r"^[a-z0-9_-]{1,32}$")
MAX_Q_LEN = 100
MAX_REASON_LEN = 200
EXPORT_DEFAULT_LIMIT = 50
EXPORT_MAX_LIMIT = 100
EXPORT_ID_LEN = 12  # item_id(sha256)の先頭12桁。貼り戻し時の書き写し間違いを減らす
_WS_RE = re.compile(r"\s+")


@news_bp.route("/api/news", methods=["GET"])
def get_news():
    """
    ニュースタブ用。新しい順に最大100件。
    クエリ: unread=1(未読のみ) / category=<slug> / q=<タイトル部分一致>
            triage=none(未判定) | A | B | C
    """
    query = NewsItem.query

    triage = request.args.get("triage", "")
    if triage:
        if triage == "none":
            query = query.filter(NewsItem.triage.is_(None))
        elif triage in NewsItem.TRIAGE_VALUES:
            query = query.filter(NewsItem.triage == triage)
        else:
            return jsonify({"error": "invalid triage"}), 400

    if request.args.get("unread") == "1":
        query = query.filter(NewsItem.is_read.is_(False))

    category = request.args.get("category", "")
    if category:
        if not SLUG_RE.match(category):
            return jsonify({"error": "invalid category"}), 400
        query = query.filter(NewsItem.category == category)

    q = (request.args.get("q") or "").strip()[:MAX_Q_LEN]
    if q:
        query = query.filter(NewsItem.title.ilike(f"%{q}%"))

    # published_atが無いものは取得日時で並べる
    items = (
        query.order_by(db.func.coalesce(NewsItem.published_at, NewsItem.fetched_at).desc())
        .limit(100)
        .all()
    )
    return jsonify([i.to_dict() for i in items])


@news_bp.route("/api/news/<int:news_id>/read", methods=["PATCH"])
def set_read(news_id):
    data = request.get_json(silent=True) or {}
    is_read = data.get("is_read")
    if not isinstance(is_read, bool):
        return jsonify({"error": "is_read must be boolean"}), 400

    item = db.session.get(NewsItem, news_id)
    if not item:
        return jsonify({"error": "not found"}), 404
    item.is_read = is_read
    db.session.commit()
    return jsonify(item.to_dict())


@news_bp.route("/api/news/<int:news_id>/triage", methods=["PATCH"])
def set_triage(news_id):
    """判定を付ける。body: {"triage": "A"|"B"|"C"|null, "reason": "任意(200文字まで)"}

    null で未判定に戻す(理由・判定日時も消す)。
    [セキュリティ] 値は許可リストで検証する。reasonは自分で入れる文字列だが、
    表示側で必ずesc()を通す前提で長さだけ制限する。
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or "triage" not in data:
        return jsonify({"error": "triage is required"}), 400

    triage = data["triage"]
    if triage is not None and (not isinstance(triage, str) or triage not in NewsItem.TRIAGE_VALUES):
        return jsonify({"error": "triage must be A, B, C or null"}), 400

    reason = data.get("reason", "")
    if not isinstance(reason, str) or len(reason) > MAX_REASON_LEN:
        return jsonify({"error": f"reason must be a string up to {MAX_REASON_LEN} chars"}), 400

    item = db.session.get(NewsItem, news_id)
    if not item:
        return jsonify({"error": "not found"}), 404

    if triage is None:
        item.triage, item.triage_reason, item.triaged_at = None, "", None
    else:
        item.triage = triage
        item.triage_reason = _WS_RE.sub(" ", reason).strip()
        item.triaged_at = datetime.now(timezone.utc).replace(tzinfo=None)  # UTC(naive)
    db.session.commit()
    return jsonify(item.to_dict())


def _one_line(text):
    """改行・制御文字を潰して1行にする。
    [セキュリティ] 出力は自分のClaudeに貼るため、外部記事の文字列が行頭の指示や
    別エントリの偽装(改行+「[id]」など)にならないよう、必ず1行に畳む。"""
    return _WS_RE.sub(" ", "".join(ch if ch.isprintable() or ch.isspace() else " " for ch in text or "")).strip()


@news_bp.route("/api/news/triage-export", methods=["GET"])
def triage_export():
    """未判定の記事を、個人のClaudeに貼るためのプレーンテキストで返す。

    HTML表示(esc()経由)とは別経路。text/plainで返し、ブラウザに解釈させない。
    番号は連番ではなく item_id の先頭12桁(判定を貼り戻すときの対応付け用)。
    クエリ: limit=1〜100(既定50)
    """
    raw = request.args.get("limit", str(EXPORT_DEFAULT_LIMIT))
    if not raw.isdigit() or not (1 <= int(raw) <= EXPORT_MAX_LIMIT):
        return jsonify({"error": f"limit must be 1-{EXPORT_MAX_LIMIT}"}), 400

    items = (
        NewsItem.query.filter(NewsItem.triage.is_(None))
        .order_by(db.func.coalesce(NewsItem.published_at, NewsItem.fetched_at).desc())
        .limit(int(raw))
        .all()
    )

    # トリアージ時にClaudeへ貼る形式: 「[短縮ID] タイトル」+ 次の行にURL。
    # 概要は含めない(AWSの概要は長く、貼る量が数倍になるため)。
    blocks = []
    for n in items:
        url = _one_line(n.url)
        if not url.startswith(("https://", "http://")):
            url = "(URLなし)"  # ワーカーが弾いているはずだが、出力側でも確認する
        blocks.append(f"[{n.item_id[:EXPORT_ID_LEN]}] {_one_line(n.title)}\n{url}")

    return Response(
        "\n\n".join(blocks) + ("\n" if blocks else ""),
        mimetype="text/plain",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
    )
