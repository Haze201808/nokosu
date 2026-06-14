from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone

db = SQLAlchemy()

class Log(db.Model):
    __tablename__ = "logs"

    id         = db.Column(db.Integer, primary_key=True)
    content    = db.Column(db.Text, nullable=False)
    tag        = db.Column(db.String(10), nullable=False)  # error / idea / memo
    project    = db.Column(db.String(100), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    VALID_TAGS = {"error", "idea", "memo"}

    def to_dict(self):
        return {
            "id":         self.id,
            "content":    self.content,
            "tag":        self.tag,
            "project":    self.project,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

