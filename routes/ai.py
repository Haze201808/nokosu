from flask import Blueprint, request, jsonify
from models.database import Log, db
from services.claude_service import ask_context_questions, find_similar_and_suggest

ai_bp = Blueprint("ai", __name__)


@ai_bp.route("/api/ai/question", methods=["POST"])
def get_question():
    """保存直後に呼ばれる：AIが文脈質問を返す"""
    data    = request.get_json()
    content = (data.get("content") or "").strip()
    tag     = data.get("tag", "memo")

    if not content:
        return jsonify({"error": "content is required"}), 400

    try:
        question = ask_context_questions(content, tag)
        return jsonify({"question": question})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@ai_bp.route("/api/ai/suggest", methods=["POST"])
def get_suggestion():
    """質問への回答後に呼ばれる：類似ログ＋対応策を返す"""
    data    = request.get_json()
    content = (data.get("content") or "").strip()
    tag     = data.get("tag", "memo")
    answer  = (data.get("answer") or "").strip()

    if not content or not answer:
        return jsonify({"error": "content and answer are required"}), 400

    # 過去ログを取得（同じタグ優先、最新50件）
    past_logs = (
        db.session.query(Log)
        .order_by(Log.created_at.desc())
        .limit(50)
        .all()
    )
    past_list = [l.to_dict() for l in past_logs]

    try:
        suggestion = find_similar_and_suggest(content, tag, answer, past_list)
        return jsonify({"suggestion": suggestion})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


