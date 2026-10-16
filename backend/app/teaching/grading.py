from app.providers.base import ProviderError
from app.schemas.domain import Grade


def grade_choice(item: dict, answer: str) -> Grade:
    selected = answer.strip()
    if selected not in item["options"]:
        matches = [key for key in item["options"] if key.casefold() == selected.casefold()]
        if len(matches) != 1:
            raise ProviderError("invalid_option", "请提交题目提供的选项", 422)
        selected = matches[0]
    correct = selected == item["answer"]
    return Grade(
        is_correct=correct,
        confidence="high",
        feedback=("回答正确。" if correct else "这道题尚未答对。") + item["rubric"],
        misconceptions=[],
    )
