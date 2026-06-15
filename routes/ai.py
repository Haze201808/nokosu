from flask import Blueprint, request, jsonify
from models.database import db, Log, AiContext
from services.claude_service import ask_context_questions, find_similar_and_suggest

ai_bp = Blueprint("ai", __name__)


@ai_bp.route("/api/ai/question", methods=["POST"])
def get_question():
    """保存直後に呼ばれる：AIが文脈質問を返す"""
    data    = request.get_json()
    log_id  = data.get("log_id")
    content = (data.get("content") or "").strip()
    tag     = data.get("tag", "memo")

    if not content:
        return jsonify({"error": "content is required"}), 400

    try:
        question = ask_context_questions(content, tag)

        # ai_contextを作成（answerとsuggestionは後で埋める）
        if log_id:
            ctx = AiContext(log_id=log_id, question=question)
            db.session.add(ctx)
            db.session.commit()
            return jsonify({"question": question, "ai_context_id": ctx.id})

        return jsonify({"question": question})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@ai_bp.route("/api/ai/suggest", methods=["POST"])
def get_suggestion():
    """質問への回答後に呼ばれる：類似ログ＋対応策を返す"""
    data           = request.get_json()
    log_id         = data.get("log_id")
    ai_context_id  = data.get("ai_context_id")
    content        = (data.get("content") or "").strip()
    tag            = data.get("tag", "memo")
    answer         = (data.get("answer") or "").strip()

    if not content or not answer:
        return jsonify({"error": "content and answer are required"}), 400

    past_logs = (
        db.session.query(Log)
        .order_by(Log.created_at.desc())
        .limit(50)
        .all()
    )
    past_list = [l.to_dict() for l in past_logs]

    try:
        suggestion = find_similar_and_suggest(content, tag, answer, past_list)

        # ai_contextにanswerとsuggestionを保存
        if ai_context_id:
            ctx = db.session.get(AiContext, ai_context_id)
            if ctx:
                ctx.answer     = answer
                ctx.suggestion = suggestion
                db.session.commit()
        elif log_id:
            ctx = AiContext(log_id=log_id, answer=answer, suggestion=suggestion)
            db.session.add(ctx)
            db.session.commit()

        return jsonify({"suggestion": suggestion})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@ai_bp.route("/api/logs/<int:log_id>/ai_contexts", methods=["GET"])
def get_ai_contexts(log_id):
    """ログに紐付いたAI会話履歴を返す"""
    contexts = (
        db.session.query(AiContext)
        .filter(AiContext.log_id == log_id)
        .order_by(AiContext.created_at.asc())
        .all()
    )
    return jsonify([c.to_dict() for c in contexts])

