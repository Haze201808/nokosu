from flask import Blueprint, request, jsonify
from models.database import db, Log, AiContext, LogRelation
from services.claude_service import ask_context_questions, find_similar_and_suggest, find_similar_logs
import json as _json

ai_bp = Blueprint("ai", __name__)


@ai_bp.route("/api/logs/discover", methods=["GET"])
def discover_unlinked_similar():
    """
    『見つかったかも』全体共通の発見セクション用。
    直近のAI類似度判定結果(ai_contexts)から、まだlog_relationsに
    登録されていない候補ペアを最大5件返す。
    """
    contexts = (
        db.session.query(AiContext)
        .order_by(AiContext.created_at.desc())
        .limit(50)
        .all()
    )

    # 既存の関連ペアをセット化（順不同で比較するためfrozenset）
    existing_rels = db.session.query(LogRelation).all()
    linked_pairs = {frozenset((r.log_id, r.related_log_id)) for r in existing_rels}

    seen_pairs = set()
    candidates = []

    for ctx in contexts:
        if len(candidates) >= 5:
            break
        if not ctx.suggestion:
            continue
        try:
            parsed = _json.loads(ctx.suggestion)
        except (ValueError, TypeError):
            continue
        if not isinstance(parsed, list):
            continue

        for item in parsed:
            if len(candidates) >= 5:
                break
            if not isinstance(item, dict):
                continue
            other_id = item.get("id")
            if other_id is None or other_id == ctx.log_id:
                continue

            pair_key = frozenset((ctx.log_id, other_id))
            if pair_key in linked_pairs or pair_key in seen_pairs:
                continue

            source = db.session.get(Log, ctx.log_id)
            target = db.session.get(Log, other_id)
            if not source or not target:
                continue  # 削除済みログはスキップ

            seen_pairs.add(pair_key)
            candidates.append({
                "source":        source.to_dict(),
                "target":        target.to_dict(),
                "relation_type": item.get("relation_type", "related"),
                "reason":        item.get("reason", ""),
            })

    return jsonify(candidates)


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

    # 自分自身を除外した過去ログ
    past_q = db.session.query(Log).order_by(Log.created_at.desc())
    if log_id:
        past_q = past_q.filter(Log.id != log_id)
    past_logs = past_q.limit(50).all()
    past_list = [l.to_dict() for l in past_logs]

    try:
        # 先に重複/関連を判定し、その結果を根拠に提案文を作る
        relations  = find_similar_logs(content, tag, past_list)
        suggestion = find_similar_and_suggest(content, tag, answer, past_list, relations)

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
    類似ログ（id, relation_type, reason）のリストを返す。
    結果は ai_contexts.suggestion に JSON で保存しておき、
    後でバッジ押下時に get_stored_similar が取り出す。
    """
    data    = request.get_json()
    log_id  = data.get("log_id")
    content = (data.get("content") or "").strip()
    tag     = data.get("tag", "memo")

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

        # 類似結果を専用のai_contextにJSON保存（自然文のsuggestionとは別レコードにする）
        if log_id and similar:
            ctx = AiContext(
                log_id=log_id,
                suggestion=_json.dumps(similar, ensure_ascii=False),
            )
            db.session.add(ctx)
            db.session.commit()

        return jsonify({"similar": similar})
    except Exception as e:
        # バックグラウンドなので200で返す
        return jsonify({"similar": [], "error": str(e)}), 200


@ai_bp.route("/api/logs/<int:log_id>/similar", methods=["GET"])
def get_stored_similar(log_id):
    """
    保存済みの類似検知結果（find_similar_logsのJSON）を取り出し、
    該当ログ本体とjoinして返す。バッジ押下時にフロントが使う。
    """
    contexts = (
        db.session.query(AiContext)
        .filter(AiContext.log_id == log_id)
        .order_by(AiContext.created_at.desc())
        .all()
    )

    detected = []
    for ctx in contexts:
        if not ctx.suggestion:
            continue
        try:
            parsed = _json.loads(ctx.suggestion)
        except (ValueError, TypeError):
            continue  # 自然文の提案はスキップ
        if isinstance(parsed, list) and parsed:
            detected = parsed
            break  # 最新のJSON検知結果を採用

    if not detected:
        return jsonify({"similar": []})

    # すでに手動で紐付け済みのlog_idを集める（候補から除外用）
    rels = (
        db.session.query(LogRelation)
        .filter(db.or_(LogRelation.log_id == log_id,
                       LogRelation.related_log_id == log_id))
        .all()
    )
    linked_ids = set()
    for r in rels:
        linked_ids.add(r.related_log_id if r.log_id == log_id else r.log_id)

    # 候補にログ本体をjoin
    result = []
    for d in detected:
        if not isinstance(d, dict):
            continue
        rid = d.get("id")
        if rid is None or rid == log_id:
            continue
        target = db.session.get(Log, rid)
        if not target:
            continue  # 削除済みログはスキップ
        result.append({
            "id":             target.id,
            "relation_type":  d.get("relation_type", "related"),
            "reason":         d.get("reason", ""),
            "content":        target.content,
            "tag":            target.tag,
            "already_linked": rid in linked_ids,
        })

    return jsonify({"similar": result})

    