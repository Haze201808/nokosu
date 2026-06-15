# 残す / Nokosu

> 開発中に出会うエラー・アイデア・メモを、その瞬間に残しておくための個人用ナレッジツール。

![Phase](https://img.shields.io/badge/Phase-2-blue) ![Stack](https://img.shields.io/badge/Stack-Flask%20%2B%20SQLite-green) ![Deploy](https://img.shields.io/badge/Deploy-AWS%20EC2-orange)

---

## なぜ作ったか

- エラーの対応方法を忘れる → 同じことを何度も調べる
- アイデアをメモしても見返さない → どこに書いたかも忘れる
- 「いつかメモしたやつ」が必要なときに見つからない

シンプルな知識の蓄積ツール。

---

## 機能

### フェーズ1（実装済み）
- **3種類のタグ**：`error` / `idea` / `memo`
- **プロジェクト**：フリーテキストで分類、サジェスト対応
- **検索**：キーワード・プロジェクト・タグで絞り込み
- **一覧表示**：直近200件、タブ切り替え

### フェーズ2（実装済み）
- **AI文脈質問**：メモ保存後にClaudeが1〜2問の深掘り質問
- **類似ログ提案**：回答をもとに過去の関連メモと対応策を提案
- タグに関わらず全種類（error/idea/memo）でAI対応

### フェーズ3（予定）
- ideaタグのステータス管理（検討中 / やる / 完了）
- メモの編集・更新
- 関連ログの手動紐付け → AI提案へ

---

## スタック

| レイヤー | 技術 |
|---|---|
| フロントエンド | HTML + Tailwind CSS（CDN）|
| バックエンド | Flask + Flask-SQLAlchemy |
| DB | SQLite（EC2 EBSに永続化）|
| AI | Anthropic Claude API（claude-sonnet-4-6）|
| インフラ | AWS EC2 t3.micro（CDK管理）|
| 認証情報 | AWS Secrets Manager |

---

## ディレクトリ構成

```
nokosu/
├── app.py                  # Flaskエントリポイント
├── config.py               # 設定（DB URL等）
├── requirements.txt
├── .env.example
├── models/
│   └── database.py         # SQLAlchemyモデル（Logテーブル）
├── routes/
│   ├── logs.py             # /api/logs CRUD
│   └── ai.py               # /api/ai/question, /api/ai/suggest
├── services/
│   └── claude_service.py   # Claude API呼び出し
├── static/
│   └── index.html          # シングルページUI
└── cdk/                    # AWS CDK（EC2デプロイ）
    └── cdk/
        └── nokosu_stack.py
```

---

## ローカル開発

```bash
# 1. クローン
git clone https://github.com/Haze201808/nokosu.git
cd nokosu

# 2. 仮想環境
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. 依存関係
python -m pip install -r requirements.txt
python -m pip install gunicorn boto3 anthropic

# 4. 環境変数
cp .env.example .env
# .envを編集：ANTHROPIC_API_KEY=sk-ant-xxxxx を追加

# 5. 起動
python app.py
# → http://localhost:5001
```

---

## EC2デプロイ（AWS CDK）

```bash
cd cdk

# 初回のみ
cdk bootstrap

# デプロイ
cdk deploy

# 出力されたURLにアクセス
# → http://<EC2 Public IP>
```

### EC2接続（SSM）

```bash
# SSH鍵不要でEC2に接続
aws ssm start-session --target <InstanceId>

# ログ確認
sudo journalctl -u nokosu -n 50 --no-pager

# アプリ更新
cd /opt/nokosu && git pull
sudo systemctl restart nokosu
```

### コードを本番反映する手順

```bash
# ローカルでpush
git add . && git commit -m "feat: xxx" && git push

# EC2側で反映
aws ssm start-session --target <InstanceId>
cd /opt/nokosu && git pull && sudo systemctl restart nokosu
```

---

## 環境変数

| 変数名 | 説明 | ローカル | EC2 |
|---|---|---|---|
| `DATABASE_URL` | SQLite or PostgreSQL URL | `sqlite:///nokosu.db` | `sqlite:////opt/nokosu/data/nokosu.db` |
| `SECRET_KEY` | Flaskセッションキー | 任意の文字列 | 自動生成 |
| `ANTHROPIC_API_KEY` | Claude APIキー（ローカル用） | `.envに記載` | Secrets Manager経由 |
| `ANTHROPIC_SECRET_NAME` | Secrets Manager シークレット名 | 不要 | `fx-diary/anthropic-api-key` |

---

