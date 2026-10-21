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
    memory = result.get("memory")
    suffix = f"\nFSRS：{memory['reason']} · 下次 {memory['due']}" if memory else ""
    return f"{label} · {result.get('assistance_level', 'none')}\n{result.get('feedback', '')}\n参考答案：{result.get('correct_answer', '')}{suffix}"


def human_output(data):
    if isinstance(data, list):
        if not data:
            return "暂无记录。"
        return "\n\n".join(human_output(row) for row in data)
    if not isinstance(data, dict):
        return str(data) if data is not None else "操作完成。"
    activity = render_activity(data)
    if activity is not None:
        return activity
    if "bkt" in data and "fsrs" in data:
        return (
            f"BKT：统一启用 · pyBKT {data['bkt']['library_version']}\n"
            f"FSRS：统一启用 · {data['fsrs']['library_version']}\n{data.get('notice', '')}"
        )
    if "distribution" in data and "task_completion" in data:
        rows = [
            f"最近 {data['days']} 天学习报告",
            data["notice"],
            f"作答 {data['evidence']['answers']} 次 · 独立 {data['evidence']['independent']} 次",
            "能力分布：" + "、".join(f"{STATUS.get(k, k)} {v}" for k, v in data["distribution"].items()),
            f"到期复习：{len(data['reviews']['due'])} 项",
            "下一步：" + data["next_action"]["reason"],
        ]
        return "\n".join(rows)
    if all(name in data for name in ("due", "upcoming", "unassessed")):
        return "\n".join(
            [
                f"到期 {len(data['due'])} · 未到期 {len(data['upcoming'])} · 待建立证据 {len(data['unassessed'])}"
            ]
            + [
                f"{row['concept_id']}  {row['name']} · {row['due']} · {row['state']}"
                for row in data["due"] + data["upcoming"]
            ]
        )
    if "lesson" in data and "concept_id" in data:
        return f"复习 {data['id']} · {data['status']}\n" + human_output(data["lesson"])
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


def render_activity(data):
    if "next_cursor" in data:
        result = human_output(data["items"])
        return result + ("\n下一页 --cursor " + data["next_cursor"] if data["next_cursor"] else "")
    if "plan" in data:
        return human_output(data["plan"]) if data["plan"] else data.get("reason", "尚无今日任务")
    if "slots" in data:
        return f"今日 {data['local_date']} · 预算 {data['budget_minutes']} 分钟\n" + "\n".join(
            human_output(slot["task"]) + f" · 分配 {slot['allocated_minutes']} 分钟" for slot in data["slots"]
        )
    if "execution_kind" in data:
        return human_output(data["task"]) + (
            "\n继续课堂：learn --space " + data["task"]["study_space_id"]
            if data["execution_kind"] == "lesson"
            else "\n继续诊断：diagnose --space " + data["task"]["study_space_id"]
        )
    if "plan_id" in data and "concept_id" in data:
        return f"{data['id']}  {data['name']} · {data['action']} · {data['status']}\n{data['reason']}"
    if "week_start" in data and "forecast" in data:
        return (
            f"自然周 {data['week_start']} · 作答 {data['answers']} 次 · 独立 {data['independent']} 次\n"
            + data["forecast"]["reason"]
            + "\n"
            + data["notice"]
        )
    if "unknown_calls" in data:
        return (
            f"AI 分析每日额度 {data['utc_date']} UTC · 调用 {data['calls']}/{data['call_limit']}\n"
            f"占用 {data['occupied_tokens']} / {data['token_limit']} tokens · 已知实际 {data['actual_tokens']}"
            f" · 未知用量 {data['unknown_calls']} 次\n{data['notice']}"
        )
    if "source_kind" in data and "reserved_tokens" in data:
        content = data.get("content") or {}
        return f"分析 {data['id']} · {data['status']}\n" + content.get(
            "summary", data.get("error_message") or "处理中"
        )
    if "source_kind" in data and "read_at" in data:
        return f"{data['id']} · {'已读' if data['read_at'] else '未读'} · {data['title']}\n{data['summary']}"
    if "fingerprint" in data and "kind" in data:
        return f"{data['id']} · {data['status']} · {data['title']}\n{data['reason']}"
    if "executions" in data and "available_at" in data:
        return f"{data['id']} · {data['kind']} · {data['status']} · 尝试 {data['attempts']}\n{data.get('error_message') or ''}"
    return None
