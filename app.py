from flask import Flask, send_from_directory
from flask_cors import CORS
from config import Config
from models.database import db
from routes.logs import logs_bp
from routes.ai import ai_bp
import os

def create_app():
    app = Flask(__name__, static_folder="static")

    Config.fix_db_url()
    app.config.from_object(Config)

    CORS(app)
    db.init_app(app)

    app.register_blueprint(logs_bp)
    app.register_blueprint(ai_bp)

    @app.route("/")
    def index():
        return send_from_directory("static", "index.html")

    with app.app_context():
        db.create_all()

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5001)

