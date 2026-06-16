from flask import Blueprint, request, jsonify
from models.database import db, Log, AiContext
from services.claude_service import ask_context_questions, find_similar_and_suggest, find_similar_logs

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



@ai_bp.route("/api/ai/similar", methods=["POST"])
def get_similar():
    """
    新規保存後バックグラウンドで呼ばれる。
    類似ログIDのリストを返す（フロントがバッジ表示に使う）。
    """
    data    = request.get_json()
    log_id  = data.get("log_id")
    content = (data.get("content") or "").strip()
    tag     = data.get("tag", "memo")
    print("similar: log_id =", log_id, "content =", content[:20])

    if not content:
        return jsonify({"similar": []}), 200

    # 自分自身を除いた過去ログ
    past_logs = (
        db.session.query(Log)
        .filter(Log.id != log_id)
        .order_by(Log.created_at.desc())
        .limit(50)
        .all()
    )
    past_list = [l.to_dict() for l in past_logs]

    try:
        similar = find_similar_logs(content, tag, past_list)
        #AI応答のログ確認
        print("similar result:", similar)
        # log_idのai_contextにsimilarを保存（次にカードを開いたとき取得可能に）
        if log_id and similar:
            from models.database import AiContext
            ctx = db.session.query(AiContext).filter(
                AiContext.log_id == log_id,
                AiContext.suggestion.is_(None),
            ).order_by(AiContext.created_at.desc()).first()
            # suggestion フィールドに類似結果をJSON保存
            import json as _json
            if ctx:
                ctx.suggestion = _json.dumps(similar, ensure_ascii=False)
            else:
                ctx = AiContext(log_id=log_id, suggestion=_json.dumps(similar, ensure_ascii=False))
                db.session.add(ctx)
            db.session.commit()

        return jsonify({"similar": similar})
    except Exception as e:
        return jsonify({"similar": [], "error": str(e)}), 200  # バックグラウンドなので200で返す