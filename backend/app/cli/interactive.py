from app.cli.client import segment
from app.cli.errors import CLIError
from app.cli.render import render_question, render_result, safe_text


def ask(prompt, message):
    return prompt(safe_text(message)).strip()


def practice(client, root, items, attempts, prompt, emit, new_key):
    """Each answer commits immediately. Quitting never manufactures completion evidence."""
    for item in items:
        if item["id"] in attempts:
            emit(f"已作答：{item['prompt']}\n{render_result(attempts[item['id']])}")
            continue
        emit(render_question(item))
        while True:
            answer = ask(prompt, "你的答案（/hint 提示，/skip 跳过，/quit 退出）：")
            if answer == "/quit":
                return
            if answer == "/skip":
                break
            if answer == "/hint":
                result = client.request(
                    "POST", root + "/items/" + segment(item["id"]) + "/hint", {"idempotency_key": new_key()}
                )
                emit(result["hint"])
                continue
            if not answer:
                continue
            try:
                result = client.request(
                    "POST",
                    root + "/attempts",
                    {"item_id": item["id"], "answer": answer, "idempotency_key": new_key()},
                )
            except CLIError as error:
                if error.code not in {"invalid_option", "validation_error"}:
                    raise
                emit(error.message)
                continue
            emit(render_result(result))
            break


def classroom(client, root, lesson, prompt, emit, new_key):
    emit(f"{lesson['title']}\n\n{lesson['explanation']}\n\n示例：{lesson['example']}")
    if not lesson["completed"]:
        answer = ask(prompt, "读完请按回车记录阅读经历（/quit 退出）：")
        if answer == "/quit":
            return
        client.request(
            "POST", root + "/lessons/" + segment(lesson["id"]) + "/complete", {"idempotency_key": new_key()}
        )
        emit("已记录阅读经历；掌握状态仍以作答证据为依据。")
    practice(client, root, lesson["exercises"], lesson.get("attempts", {}), prompt, emit, new_key)
