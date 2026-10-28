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
    # ステータス管理対象タグ（error以外）
    STATUS_TAGS    = {"idea", "memo"}

    ai_contexts = db.relationship("AiContext", backref="log", cascade="all, delete-orphan")

    # 関連ログ（このログが「元」になるもの）
    relations_as_source = db.relationship(
        "LogRelation",
        foreign_keys="LogRelation.log_id",
        backref="source_log",
        cascade="all, delete-orphan",
    )
    # 関連ログ（このログが「先」になるもの）
    relations_as_target = db.relationship(
        "LogRelation",
        foreign_keys="LogRelation.related_log_id",
        backref="target_log",
        cascade="all, delete-orphan",
    )

    def to_dict(self):
        has_relations = bool(self.relations_as_source or self.relations_as_target)
        return {
            "id":            self.id,
            "content":       self.content,
            "tag":           self.tag,
            "project":       self.project,
            "status":        self.status,
            "has_relations": has_relations,
            "created_at":    self.created_at.isoformat(),
            "updated_at":    self.updated_at.isoformat(),
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


class LogRelation(db.Model):
    """ログ同士の関連付け（双方向）"""
    __tablename__ = "log_relations"

    id             = db.Column(db.Integer, primary_key=True)
    log_id         = db.Column(db.Integer, db.ForeignKey("logs.id"), nullable=False)
    related_log_id = db.Column(db.Integer, db.ForeignKey("logs.id"), nullable=False)
    note           = db.Column(db.String(200), default="")
    created_at     = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint("log_id", "related_log_id", name="uq_log_relation"),
    )

    def to_dict(self):
        return {
            "id":             self.id,
            "log_id":         self.log_id,
            "related_log_id": self.related_log_id,
            "note":           self.note,
            "created_at":     self.created_at.isoformat(),
        }

class NewsItem(db.Model):
    """news-collector(個人AWS)から取り込んだ公開情報。

    [セキュリティ] title/summary/url は外部サイト由来の文字列である。
      - 表示時は必ずエスケープする(index.html の esc() を通す)
      - AIの深掘り質問・類似分析には渡さない(logsとテーブルを分けているのはそのため)
    """
    __tablename__ = "news_items"

    id           = db.Column(db.Integer, primary_key=True)
    item_id      = db.Column(db.String(64), nullable=False, unique=True)  # 正規化URLのsha256
    source       = db.Column(db.String(32), nullable=False)
    category     = db.Column(db.String(32), nullable=False)
    title        = db.Column(db.String(300), nullable=False)
    url          = db.Column(db.String(2048), nullable=False)
    summary      = db.Column(db.String(500), nullable=False, default="")
    published_at = db.Column(db.DateTime, index=True)  # UTC(naive)
    fetched_at   = db.Column(db.DateTime, nullable=False)  # UTC(naive)
    is_read      = db.Column(db.Boolean, nullable=False, default=False)
    created_at   = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    @staticmethod
    def _utc_iso(dt):
        # SQLiteはtzを保持しないため、UTCであることを明示して返す
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None

    def to_dict(self):
        return {
            "id":           self.id,
            "source":       self.source,
            "category":     self.category,
            "title":        self.title,
            "url":          self.url,
            "summary":      self.summary,
            "published_at": self._utc_iso(self.published_at),
            "fetched_at":   self._utc_iso(self.fetched_at),
            "is_read":      self.is_read,
        }
