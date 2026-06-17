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


def find_similar_logs(content: str, tag: str, past_logs: list) -> list[dict]:
    """
    新規保存時バックグラウンドで呼ぶ。
    過去ログと比較し、重複(duplicate)・関連(related)を判定して返す。
    なければ空リストを返す。
    """
    if not past_logs:
        return []

    past_text = "\n".join([
        f"[id={l['id']}][{l['tag']}] {l['content'][:120]}" for l in past_logs[:30]
    ])

    client = anthropic.Anthropic(api_key=get_api_key())
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        system=(
            "あなたは開発者の知識管理を助けるアシスタントです。\n"
            "新しいメモと過去ログを比較し、関連するものを最大3件選び、種類を判定してください。\n\n"
            "判定基準：\n"
            "- duplicate（重複）: 述べている事実・主張・対象が実質同一。言い回しが違っても可。\n"
            "- related（関連）: 内容は異なるが同じテーマ/対象/プロジェクトに属し、\n"
            "  繋げると考えや作業が進む可能性があるもの。\n\n"
            "重要：テーマが近いだけのものを duplicate にしないこと。\n"
            "duplicate は『同じことを二度書いた』場合のみ。迷えば related にする。\n"
            "どちらも無ければ空配列 [] を返すこと。\n\n"
            "必ず以下のJSON形式のみで返す（前置き不要）：\n"
            '[{"id": <log_id>, "relation_type": "duplicate"|"related", "reason": "<25字以内>"}]'
        ),
        messages=[{
            "role": "user",
            "content": (
                f"【新しいメモ】タグ: {tag}\n{content}\n\n"
                f"【過去のログ】\n{past_text}"
            ),
        }],
    )

    import json as _json
    try:
        result = _json.loads(message.content[0].text.strip())
        return [
            {
                "id": r["id"],
                "relation_type": r.get("relation_type", "related"),
                "reason": r.get("reason", ""),
            }
            for r in result if isinstance(r, dict) and "id" in r
        ]
    except Exception:
        return []


def find_similar_and_suggest(content: str, tag: str, answer: str,
                             past_logs: list, relations: list = None) -> str:
    """
    事前判定された重複/関連(relations)を根拠に、対応策・気づきを提案する。
    relationsはfind_similar_logsの戻り値（id, relation_type, reason）。
    """
    by_id = {l["id"]: l for l in past_logs}
    dup, rel = [], []
    for r in (relations or []):
        lg = by_id.get(r["id"])
        if not lg:
            continue
        line = f"- [id={lg['id']}][{lg['tag']}] {lg['content'][:80]}（{r.get('reason','')}）"
        if r.get("relation_type") == "duplicate":
            dup.append(line)
        else:
            rel.append(line)

    dup_text = "\n".join(dup) or "（なし）"
    rel_text = "\n".join(rel) or "（なし）"

    client = anthropic.Anthropic(api_key=get_api_key())
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        system=(
            "あなたは開発者の知識管理を助けるアシスタントです。\n"
            "このツールの目的は、ユーザーが『過去に書いたことを忘れる』ため、\n"
            "過去メモとの重複・関連に気づかせ、考えや次の行動をクリアにすることです。\n\n"
            "渡される【重複】【関連】はシステムが事前判定したものです。\n"
            "この判定を尊重し、リストに無いログを勝手に『一致』と決めつけないこと。\n\n"
            "・重複がある場合：『同じ内容を前にも残しています』と伝え、\n"
            "  忘れていた＝繰り返し気になるテーマで重要なサインだと前向きに位置づける。\n"
            "  既存ログへの統合・紐付け・対応を促す。\n"
            "・関連がある場合：どの過去メモとどう繋がるかを具体的に示し、\n"
            "  組み合わせると見えてくる次の一歩を提案する。\n"
            "・どちらも無い場合：一般的なアドバイスを簡潔に返す。\n"
            "事実にない一致をでっち上げないこと。日本語で簡潔に。"
        ),
        messages=[{
            "role": "user",
            "content": (
                f"【現在のメモ】タグ: {tag}\n内容: {content}\n\n"
                f"【質問への回答】\n{answer}\n\n"
                f"【システム判定：重複】\n{dup_text}\n\n"
                f"【システム判定：関連】\n{rel_text}"
            ),
        }],
    )
    return message.content[0].text

