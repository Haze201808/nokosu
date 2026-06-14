
uv venv && source .venv/bin/activate


## 構成
EC2 t3.micro (Ubuntu)
  └── Security Group (80, 443, 22)
  └── Flask app (gunicorn + nginx)
  └── SQLite (EBSに永続化、デフォルトで8GB)


## ディレクトリ構成
```text
nokosu/
├── app.py                  # Flaskメインアプリ
├── config.py               # 設定（DB path、APIキーなど）
├── requirements.txt
├── .env                    # ローカル用（.gitignore対象）
├── .gitignore
│
├── db/
│   └── nokosu.db           # SQLite（ローカルツールなのでこれで十分）
│
├── models/
│   ├── __init__.py
│   ├── database.py         # DB初期化・接続
│   └── log.py              # Logモデル（CRUD）
│
├── routes/
│   ├── __init__.py
│   ├── logs.py             # /api/logs (GET, POST)
│   └── ai.py               # /api/ai/question (フェーズ2用、今は空)
│
├── services/
│   ├── __init__.py
│   └── claude_service.py   # Claude API呼び出し（フェーズ2〜）
│
└── static/
    └── index.html          # SPAライクなシングルHTML（Tailwind CDN）
```


