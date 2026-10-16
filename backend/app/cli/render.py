import json
import re

STATUS = {"unknown": "待诊断", "learning": "学习中", "mastered": "已掌握"}


def safe_text(value):
    text = str(value)
    text = re.sub(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))", "", text)
    return "".join(c for c in text if c in "\n\t" or (ord(c) >= 32 and not 127 <= ord(c) <= 159))


def render_question(item):
    rows = [f"题目 {item['id']}", item["prompt"]]
    if item.get("citations"):
        rows.append(render_citations(item["citations"]))
    rows.extend(f"  {key}. {value}" for key, value in item.get("options", {}).items())
    return "\n".join(rows)


def render_result(result):
    correct = result.get("is_correct")
    label = "回答正确" if correct is True else "尚未答对" if correct is False else "需要进一步评估"
    return f"{label} · {result.get('assistance_level', 'none')}\n{result.get('feedback', '')}\n参考答案：{result.get('correct_answer', '')}"


def human_output(data):
    if isinstance(data, list):
        if not data:
            return "暂无记录。"
        return "\n\n".join(human_output(row) for row in data)
    if not isinstance(data, dict):
        return str(data) if data is not None else "操作完成。"
    if "profile" in data:
        names = {c["key"]: c["name"] for c in data.get("concepts", [])}
        profile = data["profile"]
        rows = [profile["goal"], profile.get("notice", "")]
        for state in profile["states"]:
            rows.append(
                f"  {names.get(state['concept_id'], state['concept_id'])}：{STATUS.get(state['status'], state['status'])}"
                f" · {state['evidence_count']} 条有效证据 · {state['independent_correct_count']} 次独立达标"
            )
        return "\n".join(rows)
    if "items" in data:
        return data.get("notice", "") + "\n\n" + "\n\n".join(render_question(q) for q in data["items"])
    if "filename" in data and "status" in data:
        return f"{data['id']}  {data['filename']} · {data['status']}\n任务：{data.get('job_id')}\n{data.get('warning') or data.get('retention_notice', '')}"
    if "results" in data:
        return f"检索方式：{data.get('mode')}\n" + "\n\n".join(
            f"{s['filename']} / {s['heading']}（模型提取，页码未核实）\n{s['summary']}\n来源：{s['source_id']}"
            for s in data["results"]
        )
    if "explanation" in data:
        return (
            render_citations(data.get("citations", []))
            + f"{data['title']}\n\n{data['explanation']}\n\n示例：{data['example']}\n\n"
            + "\n\n".join(render_question(q) for q in data["exercises"])
        )
    if "feedback" in data:
        return render_result(data)
    if "action" in data and "reason" in data:
        return f"下一步：{data['action']} · 约 {data['estimated_minutes']} 分钟\n{data['reason']}\n知识点：{', '.join(data['concept_ids'])}"
    if "id" in data and "goal" in data:
        return f"{data['id']}  {data['goal']}\n每日 {data['daily_minutes']} 分钟 · 模型生成、待核实"
    if "id" in data and "chat_model" in data:
        return f"{data['id']}  {data['name']} · {data['chat_model']} · {'已检测' if data['tested'] else '待检测'}"
    if "username" in data:
        return f"已登录：{data['username']}"
    if "hint" in data:
        return "提示：" + data["hint"]
    if "message" in data:
        return data["message"]
    return json.dumps(data, ensure_ascii=False, indent=2)


def render_citations(sources):
    if not sources:
        return ""
    return (
        "教材证据（模型提取，页码未核实）：\n"
        + "\n".join(f"  {s['filename']} / {s['heading']} · {s['source_id']}" for s in sources)
        + "\n\n"
    )
