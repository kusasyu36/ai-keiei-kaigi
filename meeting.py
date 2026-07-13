"""仮想経営会議のオーケストレーション。

流れ（3ラウンド）:
  Round 1: 4人の専門AIがそれぞれ独立に意見を出す（互いの意見は見せない）
  Round 2: 各専門AIが他の3人の意見を読み、見落とし・過大評価を指摘する（相互レビュー）
  Round 3: 議長AIが全体を統合し、経営者向けの提言書を作る

Round 2 を挟む理由:
  独立意見だけを束ねると、各AIの楽観・悲観がそのまま提言書に残る。
  批評役を一段挟むことで、根拠の弱い主張が提言書に昇格するのを防ぐ
  （批評エージェント導入でタスク成功率が大きく改善した過去プロジェクトの知見を踏襲）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from llm_client import call_llm
from personas import SPECIALISTS, FACILITATOR_SYSTEM

def _ask(**kwargs) -> str:
    """call_llm の薄いラッパー。空応答（None/空文字）を欠損として扱い、1回だけ再試行する。
    それでも空なら例外にする（欠けた発言が無言のまま提言書に混ざるのを防ぐ）。
    """
    for attempt in range(2):
        text = call_llm(**kwargs)
        if text and text.strip():
            return text.strip()
    raise RuntimeError("LLMが空応答を返しました（2回試行）")


OPINION_FORMAT = """
次の見出し構成で、日本語で簡潔に書いてください。

## 結論（1〜2文）
## 根拠（与えられた事実に基づくもののみ）
## 前提とした仮定（事実ではないが、こう仮定した、という項目）
## 不足している情報（経営者に確認したいこと）
"""

REVIEW_FORMAT = """
次の見出し構成で、日本語で簡潔に書いてください。

## 同意できる点
## 見落とし・過大評価の指摘（どの担当の、どの主張に対してかを明記）
## 指摘を踏まえて自分の意見を修正するなら（なければ「修正なし」）
"""

REPORT_FORMAT = """
次の見出し構成の「提言書」を日本語で書いてください。経営者がそのまま読める文章にすること。

# 提言書: {title}

## 1. 事実情報の整理
（相談内容から確定している事実だけを箇条書き。推測を混ぜない）

## 2. 経営者への質問（不足している情報）
（会議で「不足」と挙がった情報を、優先度順に質問の形で）

## 3. 論点（専門AI間で意見が分かれた点・重要な分岐）

## 4. 次に考えるべきこと
（判断の順番が分かるように番号付きで）

## 5. 相談すべき先
（誰に・何を持って行くか。例: 税理士に◯◯の試算、金融機関担当者に◯◯の条件確認）
"""


@dataclass
class MeetingLog:
    """会議の全発言記録。Markdown で保存できる形で持つ。"""
    consultation: str
    opinions: dict[str, str] = field(default_factory=dict)
    reviews: dict[str, str] = field(default_factory=dict)
    report: str = ""

    def to_markdown(self) -> str:
        parts = ["# 会議ログ", "", "## 相談内容", "", self.consultation, ""]
        parts += ["---", "", "## Round 1: 各専門AIの独立意見", ""]
        for name, text in self.opinions.items():
            parts += [f"### {name}", "", text, ""]
        parts += ["---", "", "## Round 2: 相互レビュー", ""]
        for name, text in self.reviews.items():
            parts += [f"### {name} からの指摘", "", text, ""]
        parts += ["---", "", "## Round 3: 提言書", "", self.report, ""]
        return "\n".join(parts)


def _round1_opinion(name: str, spec: dict, consultation: str) -> str:
    user_prompt = (
        f"経営者から次の相談が来ています。あなた（{name}）の立場から意見を述べてください。\n\n"
        f"{consultation}\n\n{OPINION_FORMAT}"
    )
    return _ask(
        system_prompt=spec["system"],
        user_prompt=user_prompt,
        temperature=0.4,
        max_retries=2,
    )


def _round2_review(name: str, spec: dict, consultation: str,
                   opinions: dict[str, str]) -> str:
    others = "\n\n".join(
        f"### {other} の意見\n{text}"
        for other, text in opinions.items() if other != name
    )
    user_prompt = (
        f"経営者からの相談:\n{consultation}\n\n"
        f"他の3人の専門AIの意見は以下の通りです。\n\n{others}\n\n"
        f"あなた（{name}）の専門の立場から、レビューしてください。\n{REVIEW_FORMAT}"
    )
    return _ask(
        system_prompt=spec["system"],
        user_prompt=user_prompt,
        temperature=0.3,
        max_retries=2,
    )


def _round3_report(title: str, consultation: str,
                   opinions: dict[str, str], reviews: dict[str, str]) -> str:
    body = "\n\n".join(
        [f"### {n} の意見\n{t}" for n, t in opinions.items()]
        + [f"### {n} からの指摘\n{t}" for n, t in reviews.items()]
    )
    user_prompt = (
        f"経営者からの相談:\n{consultation}\n\n"
        f"会議での全発言:\n\n{body}\n\n"
        + REPORT_FORMAT.format(title=title)
    )
    return _ask(
        system_prompt=FACILITATOR_SYSTEM,
        user_prompt=user_prompt,
        temperature=0.3,
        max_retries=2,
    )


def run_meeting(consultation: str, title: str = "経営相談",
                verbose: bool = True) -> MeetingLog:
    """相談内容を受け取り、3ラウンドの会議を実行して提言書まで返す。"""
    log = MeetingLog(consultation=consultation)

    for name, spec in SPECIALISTS.items():
        if verbose:
            print(f"  Round 1: {name} が意見を作成中...")
        log.opinions[name] = _round1_opinion(name, spec, consultation)

    for name, spec in SPECIALISTS.items():
        if verbose:
            print(f"  Round 2: {name} が相互レビュー中...")
        log.reviews[name] = _round2_review(name, spec, consultation, log.opinions)

    if verbose:
        print("  Round 3: 議長が提言書を作成中...")
    log.report = _round3_report(title, consultation, log.opinions, log.reviews)
    return log
