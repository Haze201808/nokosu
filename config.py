import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///nokosu.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # RenderのDATABASE_URLはpostgres://で始まるが、SQLAlchemyはpostgresql://が必要
    @classmethod
    def fix_db_url(cls):
        url = cls.SQLALCHEMY_DATABASE_URI
        if url.startswith("postgres://"):
            cls.SQLALCHEMY_DATABASE_URI = url.replace("postgres://", "postgresql://", 1)