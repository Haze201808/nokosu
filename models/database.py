from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone

db = SQLAlchemy()

class Log(db.Model):
    __tablename__ = "logs"

    id         = db.Column(db.Integer, primary_key=True)
    content    = db.Column(db.Text, nullable=False)
    tag        = db.Column(db.String(10), nullable=False)
    project    = db.Column(db.String(100), nullable=False, default="")
    status     = db.Column(db.String(10), nullable=False, default="検討中")
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    VALID_TAGS     = {"error", "idea", "memo"}
    VALID_STATUSES = {"検討中", "やる", "完了"}

    ai_contexts = db.relationship("AiContext", backref="log", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id":         self.id,
            "content":    self.content,
            "tag":        self.tag,
            "project":    self.project,
            "status":     self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class AiContext(db.Model):
    __tablename__ = "ai_contexts"

    id         = db.Column(db.Integer, primary_key=True)
    log_id     = db.Column(db.Integer, db.ForeignKey("logs.id"), nullable=False)
    question   = db.Column(db.Text)
    answer     = db.Column(db.Text)
    suggestion = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id":         self.id,
            "log_id":     self.log_id,
            "question":   self.question,
            "answer":     self.answer,
            "suggestion": self.suggestion,
            "created_at": self.created_at.isoformat(),
        }