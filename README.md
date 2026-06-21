# Nokosu

> 開発中に出会うエラー・アイデア・メモを、その瞬間に残しておくための個人用ナレッジツール。

![Phase](https://img.shields.io/badge/Phase-5-blue) ![Stack](https://img.shields.io/badge/Stack-Flask%20%2B%20SQLite-green) ![Deploy](https://img.shields.io/badge/Deploy-AWS%20EC2-orange) ![HTTPS](https://img.shields.io/badge/HTTPS-enabled-success)

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

### フェーズ5（実装済み）
- **重複/関連の判定ロジック改善**：AIの類似検知に明確な判定基準（duplicate=実質同一内容のみ／related=テーマが近いが内容は別）を導入し、過敏な重複判定を抑制
- **自己照合バグの修正**：`/api/ai/suggest`が保存直後の自分自身を「過去ログ」として誤検知していた問題を修正（自己除外フィルタを追加）
- **バッジの出し分け**：🔁 重複 / 🔗 関連の気づき をAIの判定結果に応じて表示
- **AI候補からの紐付けUI**：バッジを押すと「AIが見つけた候補（reason付き）」が関連ログエリアに表示され、ボタン1つで`log_relations`に紐付け可能（採用は人が判断）
- **マインドマップ（静的・1階層）**：カードの🗺️ボタンから、選択したカードを中心に1階層の関連ログを放射状に表示するモーダルを追加。ノードクリックでそのカードを起点に再表示、「← 戻る」で辿った履歴を戻れる（PC専用・静的表示）
- **ログ単体取得API追加**：`GET /api/logs/<id>` を追加し、一覧の件数制限（10/200件）に関わらず特定のログを確実に取得できるように
- **本番環境のセキュリティ強化**：
  - 独自ドメイン（`nokosu.haze-lab.com`）取得 + Let's EncryptによるHTTPS化
  - nginx Basic認証を追加（知らない第三者のアクセスを防止）
  - 不要なポート（22, 5001）をセキュリティグループから削除し、80（→443リダイレクト）・443のみ開放
  - Elastic IPをCDKコードで明示的に管理（`CfnEIP` + `CfnEIPAssociation`）し、デプロイの度にIPが変わる問題を解消

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
│   ├── logs.py             # /api/logs CRUD + ログ単体取得 + 関連ログエンドポイント
│   └── ai.py                # /api/ai/question, suggest, similar + 保存済み類似候補取得
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

# 出力されたElastic IPをDNS（Aレコード）に設定
# → https://nokosu.haze-lab.com でアクセス（Basic認証あり）
```

CDKでElastic IPを管理しているため、`cdk deploy`を何度実行してもIPアドレスは変わりません。DNS（Cloudflare）のAレコードは初回設定後、基本的に変更不要です。

### 本番アクセス

- URL: `https://nokosu.haze-lab.com`
- 認証: nginx Basic認証（ユーザー名・パスワードは別途管理）
- HTTPS: Let's Encrypt（Certbot、自動更新）

### EC2接続（SSM）

```bash
# SSH鍵不要でEC2に接続
aws ssm start-session --target <InstanceId>

# 初回のみ（safe.directory設定、ssm-userのホームはセッションごとにリセットされる）
git config --global --add safe.directory /opt/nokosu

# ログ確認
sudo journalctl -u nokosu -n 50 --no-pager

# 証明書の確認
sudo certbot certificates
```

### コードを本番反映する手順

```bash
# ローカルでpush
git add . && git commit -m "feat: xxx" && git push

# EC2側で反映（pullではなくfetch + reset --hardを使う）
aws ssm start-session --target <InstanceId>
git config --global --add safe.directory /opt/nokosu
sudo git -C /opt/nokosu fetch origin
sudo git -C /opt/nokosu reset --hard origin/master
sudo systemctl restart nokosu
```

> **Note:** `git pull`は使わない。ローカルでforce pushした履歴があると、EC2側のブランチがdivergeしてマージコンフリクト（コンフリクトマーカーが本番ファイルに残る等）が発生したことがあるため、常にリモートの状態に強制一致させる`fetch + reset --hard`に統一している。

---

## 環境変数

| 変数名 | 説明 | ローカル | EC2 |
|---|---|---|---|
| `DATABASE_URL` | SQLite URL | `sqlite:///nokosu.db` | `sqlite:////opt/nokosu/data/nokosu.db` |
| `SECRET_KEY` | Flaskセッションキー | 任意の文字列 | 自動生成 |
| `ANTHROPIC_API_KEY` | Claude APIキー（ローカル用） | `.envに記載` | Secrets Manager経由 |
| `ANTHROPIC_SECRET_NAME` | Secrets Manager シークレット名 | 不要 | `fx-diary/anthropic-api-key` |

---
