from flask import Blueprint, request, jsonify
from models.database import db, Log
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