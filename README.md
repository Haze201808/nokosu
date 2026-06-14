


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


RenderからEC2への移行は簡単か？
はい、かなり楽です。 PostgreSQLは同じなので：
bash

# Renderから export
pg_dump $RENDER_DATABASE_URL > nokosu_backup.sql

# EC2のPostgreSQLに import
psql $EC2_DATABASE_URL < nokosu_backup.sql
コードは一切変更不要（接続URLを環境変数で切り替えるだけ）。