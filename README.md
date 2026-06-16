# Nokosu

> 開発中に出会うエラー・アイデア・メモを、その瞬間に残しておくための個人用ナレッジツール。

![Phase](https://img.shields.io/badge/Phase-4-blue) ![Stack](https://img.shields.io/badge/Stack-Flask%20%2B%20SQLite-green) ![Deploy](https://img.shields.io/badge/Deploy-AWS%20EC2-orange)

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
- **一覧表示**：直近10件、タブ切り替え

### フェーズ2（実装済み）
- **AI文脈質問**：メモ保存後にClaudeが1〜2問の深掘り質問
- **類似ログ提案**：回答をもとに過去の関連メモと対応策を提案
- タグに関わらず全種類（error/idea/memo）でAI対応

### フェーズ3（実装済み）
- **ideaステータス管理**：`検討中` / `やる` / `完了` をワンクリックで切り替え
- **ログ編集**：内容・タグ・プロジェクトをインライン編集
- **日本時間表示**：UTC→JSTに自動変換
- **関連ログの紐付け**：カードから新規ログを作成して紐付け、双方向で表示・削除
- **バックグラウンド類似分析**：保存時にAIが過去ログを分析し、類似ログがあれば 💡 類似あり バッジで通知
- **🔗 関連あり バッジ**：関連ログが存在するカードを一目で識別

### フェーズ4（実装済み）
- **memoステータス管理**：memoタグにも `検討中` / `やる` / `完了` を追加（ナレッジとして残すか・対応するかを管理）
- **memo/ideaタブで200件表示**：memoとideaは最大200件表示（errorは10件のまま）
- **既存ログへの検索紐付け**：関連ログ作成時に「既存から選ぶ」タブでキーワード検索して既存ログと紐付け可能
- **🔗ボタン常時表示**：全カードの右上に関連ログボタンを常時表示（関連ログがないカードからも操作可能）

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
├── migrate.py              # DBマイグレーション
├── requirements.txt
├── models/
│   └── database.py         # SQLAlchemyモデル（Log / AiContext / LogRelation）
├── routes/
│   ├── logs.py             # /api/logs CRUD + 関連ログエンドポイント
│   └── ai.py               # /api/ai/question, suggest, similar
├── services/
│   └── claude_service.py   # Claude API呼び出し
├── static/
│   └── index.html          # シングルページUI
└── cdk/                    # AWS CDK（EC2デプロイ）
    └── cdk/
        └── nokosu_stack.py
```

---

## DBスキーマ

```
logs            # メインのログ
ai_contexts     # AI質問・回答・提案の履歴（logsに紐付き）
log_relations   # ログ同士の関連付け（双方向、logsに紐付き）
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

# 5. DBマイグレーション（初回・更新時）
python migrate.py

# 6. 起動
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
sudo git -C /opt/nokosu pull
sudo systemctl restart nokosu
```

### コードを本番反映する手順

```bash
# ローカルでpush
git add . && git commit -m "feat: xxx" && git push

# EC2側で反映
aws ssm start-session --target <InstanceId>
sudo git -C /opt/nokosu pull
sudo systemctl restart nokosu
```

---

## 環境変数

| 変数名 | 説明 | ローカル | EC2 |
|---|---|---|---|
| `DATABASE_URL` | SQLite URL | `sqlite:///nokosu.db` | `sqlite:////opt/nokosu/data/nokosu.db` |
| `SECRET_KEY` | Flaskセッションキー | 任意の文字列 | 自動生成 |
| `ANTHROPIC_API_KEY` | Claude APIキー（ローカル用） | `.envに記載` | Secrets Manager経由 |
| `ANTHROPIC_SECRET_NAME` | Secrets Manager シークレット名 | 不要 | `fx-diary/anthropic-api-key` |

---
