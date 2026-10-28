from flask import Blueprint, request, jsonify
from models.database import db, NewsItem
import re

news_bp = Blueprint("news", __name__)

SLUG_RE = re.compile(r"^[a-z0-9_-]{1,32}$")
MAX_Q_LEN = 100


@news_bp.route("/api/news", methods=["GET"])
def get_news():
    """
    ニュースタブ用。新しい順に最大100件。
    クエリ: unread=1(未読のみ) / category=<slug> / q=<タイトル部分一致>
    """
    query = NewsItem.query

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
