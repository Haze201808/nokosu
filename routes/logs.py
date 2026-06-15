from flask import Blueprint, request, jsonify
from models.database import db, Log, LogRelation
from datetime import datetime, timezone

logs_bp = Blueprint("logs", __name__)

@logs_bp.route("/api/logs", methods=["GET"])
def get_logs():
    tag     = request.args.get("tag")
    project = request.args.get("project")
    q       = request.args.get("q")

    query = Log.query

    if tag and tag in Log.VALID_TAGS:
        query = query.filter(Log.tag == tag)
    if project:
        query = query.filter(Log.project == project)
    if q:
        query = query.filter(Log.content.ilike(f"%{q}%"))

    logs = query.order_by(Log.created_at.desc()).limit(10).all()
    return jsonify([l.to_dict() for l in logs])


@logs_bp.route("/api/logs", methods=["POST"])
def create_log():
    data = request.get_json()

    content = (data.get("content") or "").strip()
    tag     = data.get("tag", "memo")
    project = (data.get("project") or "").strip()

    if not content:
        return jsonify({"error": "content is required"}), 400
    if tag not in Log.VALID_TAGS:
        return jsonify({"error": f"tag must be one of {Log.VALID_TAGS}"}), 400

    log = Log(content=content, tag=tag, project=project)
    db.session.add(log)
    db.session.commit()
    return jsonify(log.to_dict()), 201


@logs_bp.route("/api/logs/<int:log_id>", methods=["DELETE"])
def delete_log(log_id):
    log = db.session.get(Log, log_id)
    if not log:
        return jsonify({"error": "not found"}), 404
    db.session.delete(log)
    db.session.commit()
    return jsonify({"deleted": log_id})


@logs_bp.route("/api/projects", methods=["GET"])
def get_projects():
    """logsテーブルからユニークなproject名を返す（サジェスト用）"""
    rows = db.session.query(Log.project).filter(Log.project != "").distinct().all()
    projects = sorted([r[0] for r in rows])
    return jsonify(projects)


@logs_bp.route("/api/logs/<int:log_id>", methods=["PUT"])
def update_log(log_id):
    log = db.session.get(Log, log_id)
    if not log:
        return jsonify({"error": "not found"}), 404

    data    = request.get_json()
    content = (data.get("content") or "").strip()
    tag     = data.get("tag", log.tag)
    project = (data.get("project") or "").strip()

    if not content:
        return jsonify({"error": "content is required"}), 400
    if tag not in Log.VALID_TAGS:
        return jsonify({"error": f"tag must be one of {Log.VALID_TAGS}"}), 400

    log.content    = content
    log.tag        = tag
    log.project    = project
    log.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify(log.to_dict())


@logs_bp.route("/api/logs/<int:log_id>/status", methods=["PATCH"])
def update_status(log_id):
    """ideaタグのステータスをワンクリックで次に進める"""
    log = db.session.get(Log, log_id)
    if not log:
        return jsonify({"error": "not found"}), 404

    cycle = ["検討中", "やる", "完了"]
    current = log.status if log.status in cycle else "検討中"
    next_status = cycle[(cycle.index(current) + 1) % len(cycle)]

    log.status     = next_status
    log.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify(log.to_dict())

# ─── 関連ログ ────────────────────────────────────────────

@logs_bp.route("/api/logs/<int:log_id>/relations", methods=["GET"])
def get_relations(log_id):
    """このログに関連付けられたログ一覧を返す（双方向）"""
    log = db.session.get(Log, log_id)
    if not log:
        return jsonify({"error": "not found"}), 404

    # log_id が元・先どちらの場合もまとめて取得
    relations = (
        db.session.query(LogRelation)
        .filter(
            db.or_(
                LogRelation.log_id == log_id,
                LogRelation.related_log_id == log_id,
            )
        )
        .all()
    )

    result = []
    for r in relations:
        # 相手側のlog_idを特定
        other_id = r.related_log_id if r.log_id == log_id else r.log_id
        other = db.session.get(Log, other_id)
        if other:
            result.append({
                "relation_id":    r.id,
                "note":           r.note,
                "related_log":    other.to_dict(),
            })

    return jsonify(result)


@logs_bp.route("/api/logs/<int:log_id>/relations", methods=["POST"])
def create_relation(log_id):
    """
    カードから新規ログを作成して関連付け、または既存ログIDで紐付け
    body: { "content": str, "tag": str, "project": str, "note": str }
         または
         { "related_log_id": int, "note": str }
    """
    log = db.session.get(Log, log_id)
    if not log:
        return jsonify({"error": "not found"}), 404

    data = request.get_json()
    note = (data.get("note") or "").strip()

    # 既存ログとの紐付け
    if "related_log_id" in data:
        related_id = data["related_log_id"]
        if related_id == log_id:
            return jsonify({"error": "自己参照はできません"}), 400

        # 重複チェック
        existing = db.session.query(LogRelation).filter(
            db.or_(
                db.and_(LogRelation.log_id == log_id, LogRelation.related_log_id == related_id),
                db.and_(LogRelation.log_id == related_id, LogRelation.related_log_id == log_id),
            )
        ).first()
        if existing:
            return jsonify({"error": "already related"}), 409

        relation = LogRelation(log_id=log_id, related_log_id=related_id, note=note)
        db.session.add(relation)
        db.session.commit()
        related_log = db.session.get(Log, related_id)
        return jsonify({
            "relation_id": relation.id,
            "note":        relation.note,
            "related_log": related_log.to_dict(),
        }), 201

    # 新規ログを作成して関連付け
    content = (data.get("content") or "").strip()
    tag     = data.get("tag", "memo")
    project = (data.get("project") or log.project).strip()

    if not content:
        return jsonify({"error": "content is required"}), 400
    if tag not in Log.VALID_TAGS:
        return jsonify({"error": f"tag must be one of {Log.VALID_TAGS}"}), 400

    new_log = Log(content=content, tag=tag, project=project)
    db.session.add(new_log)
    db.session.flush()  # new_log.id を確定

    relation = LogRelation(log_id=log_id, related_log_id=new_log.id, note=note)
    db.session.add(relation)
    db.session.commit()

    return jsonify({
        "relation_id": relation.id,
        "note":        relation.note,
        "related_log": new_log.to_dict(),
    }), 201


@logs_bp.route("/api/logs/<int:log_id>/relations/<int:relation_id>", methods=["DELETE"])
def delete_relation(log_id, relation_id):
    """関連付けを削除（ログ自体は消えない）"""
    relation = db.session.get(LogRelation, relation_id)
    if not relation:
        return jsonify({"error": "not found"}), 404
    if relation.log_id != log_id and relation.related_log_id != log_id:
        return jsonify({"error": "forbidden"}), 403

    db.session.delete(relation)
    db.session.commit()
    return jsonify({"deleted": relation_id})