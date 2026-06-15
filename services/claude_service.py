import boto3
import json
import os
import anthropic
from botocore.exceptions import ClientError


def get_api_key() -> str:
    """Secrets ManagerからAnthropic APIキーを取得（ローカルは.envから）"""
    # ローカル開発用
    local_key = os.environ.get("ANTHROPIC_API_KEY")
    if local_key:
        return local_key

    # EC2本番：Secrets Managerから取得
    secret_name = os.environ.get("ANTHROPIC_SECRET_NAME", "fx-diary/anthropic-api-key")
    client = boto3.client("secretsmanager", region_name="ap-northeast-1")
    response = client.get_secret_value(SecretId=secret_name)
    secret = response["SecretString"]

    # JSON形式 or 生文字列どちらにも対応
    try:
        return json.loads(secret).get("api_key", secret)
    except (json.JSONDecodeError, AttributeError):
        return secret


def ask_context_questions(content: str, tag: str) -> str:
    """
    入力内容に対してAIが文脈を深める質問を1〜2問返す
    """
    tag_guidance = {
        "error": "エラーや問題の再現条件、試したこと、環境などを把握するための質問",
        "idea":  "アイデアの目的、対象ユーザー、実現可能性などを深掘りする質問",
        "memo":  "メモの背景や関連情報、次のアクションなどを確認する質問",
    }
    guidance = tag_guidance.get(tag, "内容を深掘りする質問")

    client = anthropic.Anthropic(api_key=get_api_key())
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        system=(
            "あなたは開発者の知識管理を助けるアシスタントです。\n"
            "ユーザーが残したメモに対して、後で見返したときに役立つ情報を補完するため、\n"
            f"{guidance}を1〜2問だけ日本語で行ってください。\n"
            "質問のみを返してください。前置きや説明は不要です。"
        ),
        messages=[{"role": "user", "content": f"タグ: {tag}\n内容: {content}"}],
    )
    return message.content[0].text


def find_similar_and_suggest(content: str, tag: str, answer: str, past_logs: list) -> str:
    """
    ユーザーの回答 + 過去ログをもとに類似ログと対応策を提案
    """
    past_text = "\n".join([
        f"- [{l['tag']}] {l['content']}" for l in past_logs[:20]
    ]) or "（過去ログなし）"

    client = anthropic.Anthropic(api_key=get_api_key())
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        system=(
            "あなたは開発者の知識管理を助けるアシスタントです。\n"
            "ユーザーの現在の状況と過去のログをもとに、\n"
            "類似する過去の記録を指摘し、役立つ対応策や関連情報を日本語で提案してください。\n"
            "過去ログに類似がない場合は、一般的なアドバイスを簡潔に返してください。"
        ),
        messages=[{
            "role": "user",
            "content": (
                f"【現在のメモ】\nタグ: {tag}\n内容: {content}\n\n"
                f"【質問への回答】\n{answer}\n\n"
                f"【過去のログ】\n{past_text}"
            )
        }],
    )
    return message.content[0].text




def find_similar_logs(content: str, tag: str, past_logs: list) -> list[dict]:
    """
    新規保存時バックグラウンドで呼ぶ。
    類似ログがあればそのIDとスコア・理由を返す。
    なければ空リストを返す。
    """
    if not past_logs:
        return []

    past_text = "\n".join([
        f"[id={l['id']}][{l['tag']}] {l['content'][:80]}" for l in past_logs[:30]
    ])

    client = anthropic.Anthropic(api_key=get_api_key())
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        system=(
            "あなたは開発者の知識管理を助けるアシスタントです。\n"
            "新しいメモと過去のログを比較し、関連性が高いものを最大3件選んでください。\n"
            "必ず以下のJSON形式のみで返してください（前置き・説明不要）：\n"
            '[{"id": <log_id>, "reason": "<関連理由を20字以内>"}]\n'
            "関連性が高いものがなければ空配列 [] を返してください。"
        ),
        messages=[{
            "role": "user",
            "content": (
                f"【新しいメモ】タグ: {tag}\n{content}\n\n"
                f"【過去のログ】\n{past_text}"
            )
        }],
    )

    import json as _json
    try:
        raw = message.content[0].text.strip()
        return _json.loads(raw)
    except Exception:
        return []