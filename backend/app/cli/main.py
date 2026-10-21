import argparse
import getpass
import json
import os
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import quote, urlencode

from app.cli.client import APIClient, segment
from app.cli.errors import CLIError
from app.cli.interactive import classroom, practice
from app.cli.render import human_output, safe_text
from app.cli.state import StateStore, default_config_dir
from app.core.settings import MAX_MATERIAL_BYTES


def build_parser():
    parser = argparse.ArgumentParser(prog="study-agent", description="StudyAgent 个人学习命令行客户端")
    parser.add_argument(
        "--server",
        default=os.getenv("STUDY_AGENT_SERVER", "http://127.0.0.1:8000"),
        help="后端地址；远程须 HTTPS",
    )
    parser.add_argument("--config-dir", type=Path, default=default_config_dir(), help="独立的本地会话目录")
    parser.add_argument("--json", action="store_true", help="JSON 输出，不进入交互答题")
    parser.add_argument("--timeout", type=float, default=100, help="HTTP 超时秒数，默认 100")
    groups = parser.add_subparsers(dest="command", required=True)

    auth = groups.add_parser("auth", help="账号与会话").add_subparsers(dest="action", required=True)
    for action in ("register", "login"):
        command = auth.add_parser(action, help="注册" if action == "register" else "登录")
        command.add_argument("--username", required=True)
        command.add_argument("--password-env", help="从指定环境变量读取密码，默认可用 STUDY_AGENT_PASSWORD")
    auth.add_parser("status", help="查看当前登录用户")
    auth.add_parser("logout", help="撤销当前会话并清除本地选择")

    providers = groups.add_parser("provider", help="模型连接管理").add_subparsers(
        dest="action", required=True
    )
    providers.add_parser("list")
    add = providers.add_parser("add")
    add.add_argument("--name", required=True)
    add.add_argument("--model")
    add.add_argument("--base-url", default="https://api.openai.com/v1")
    add.add_argument("--api-key-env", help="包含 API Key 的环境变量名称")
    add.add_argument("--files", action="store_true", help="Files + Responses 原生 PDF 适配器，需实际能力检测")
    add.add_argument("--demo-files", action="store_true", help="固定资料样例，未读取上传内容")
    add.add_argument("--embedding-model", help="可选：同一服务商远端 Embedding 模型 ID")
    add.add_argument("--demo", action="store_true", help="固定操作系统离线演示，须服务端允许")
    add.add_argument(
        "--accept-data-transfer",
        action="store_true",
        help="授权将学习目标、教学上下文和答案发送至该模型服务商",
    )
    for action in ("test", "capabilities", "remove", "update"):
        command = providers.add_parser(action)
        command.add_argument("id")
        if action == "update":
            command.add_argument("--name")
            command.add_argument("--model")
            command.add_argument("--embedding-model")
            command.add_argument("--clear-embedding-model", action="store_true")
            command.add_argument("--base-url")
            command.add_argument("--rotate-key", action="store_true")
            command.add_argument("--api-key-env")
            command.add_argument("--accept-data-transfer", action="store_true")

    spaces = groups.add_parser("space", help="学习空间与目标").add_subparsers(dest="action", required=True)
    spaces.add_parser("list")
    create = spaces.add_parser("create")
    create.add_argument("--goal", required=True)
    create.add_argument("--provider", required=True)
    create.add_argument("--minutes", type=int, default=30)
    create.add_argument("--target-date", help="目标日期 YYYY-MM-DD")
    create.add_argument("--level", default="基础掌握")
    create.add_argument("--request-id", help="可复用的初始化幂等键")
    for action in ("use", "show", "switch-provider"):
        command = spaces.add_parser(action)
        command.add_argument("id")
        if action == "switch-provider":
            command.add_argument("--provider", required=True)

    policy = spaces.add_parser("knowledge-policy", help="教材不足时是否允许通用知识补充")
    policy.add_argument("id")
    policy.add_argument("--allow-general-knowledge", action=argparse.BooleanOptionalAction, required=True)

    materials = groups.add_parser("material", help="私人 PDF 教材").add_subparsers(
        dest="action", required=True
    )
    for action in ("list", "upload", "show", "search", "reindex", "remove", "download"):
        command = materials.add_parser(action)
        command.add_argument("--space")
        if action == "upload":
            command.add_argument("file", type=Path)
        elif action == "search":
            command.add_argument("query")
            command.add_argument("--mode", choices=["auto", "keyword", "embedding"], default="auto")
        elif action != "list":
            command.add_argument("id")
        if action in {"upload", "reindex"}:
            command.add_argument(
                "--accept-file-transfer",
                action="store_true",
                help="授权本次远端文件理解，知悉第三方保留政策和费用",
            )
            command.add_argument(
                "--embeddings", action="store_true", help="授权将远端摘要发送到已检测的远端 Embedding API"
            )
            command.add_argument("--request-id")
        if action == "download":
            command.add_argument("--output", type=Path, required=True)
    jobs = groups.add_parser("job", help="资料处理任务").add_subparsers(dest="action", required=True)
    for action in ("show", "run", "wait", "cancel", "retry"):
        command = jobs.add_parser(action)
        command.add_argument("id")
        if action == "retry":
            command.add_argument("--request-id")
        if action == "wait":
            command.add_argument("--seconds", type=int, default=180)

    review = groups.add_parser("review", help="FSRS 复习").add_subparsers(dest="action", required=True)
    for action in ("list", "start", "submit"):
        command = review.add_parser(action)
        command.add_argument("--space")
        if action == "start":
            command.add_argument("--concept", required=True)
        if action == "submit":
            command.add_argument("id")
            command.add_argument("--item", required=True)
            command.add_argument("--answer")
            command.add_argument("--rating", choices=["again", "hard", "good", "easy"])
        if action != "list":
            command.add_argument("--request-id")
    report = groups.add_parser("report", help="学习报告")
    report.add_argument("--days", type=int, choices=[7, 30], default=7)
    report.add_argument("--space")
    algorithms = groups.add_parser("algorithms", help="查看统一启用的 BKT 与 FSRS")
    algorithms.add_argument("--space")

    today = groups.add_parser("today", help="今日任务（读取不调用模型）")
    today.add_argument("--space")
    today.add_argument("--refresh", action="store_true")
    today.add_argument("--request-id")
    for group, actions in {
        "task": ("list", "start", "complete", "skip", "postpone"),
        "suggestion": ("list", "accept", "skip"),
        "inbox": ("list", "read"),
        "weekly": ("list", "show", "current", "refresh"),
        "analysis": ("list", "show"),
        "activity-jobs": ("list", "retry"),
    }.items():
        commands = groups.add_parser(group).add_subparsers(dest="action", required=True)
        for action in actions:
            command = commands.add_parser(action)
            if group not in {"inbox", "activity-jobs"}:
                command.add_argument("--space")
            if action not in {"list", "current", "refresh"}:
                command.add_argument("id")
            if action not in {"list", "show", "current"}:
                command.add_argument("--request-id")
            if action == "list" and group in {"inbox", "weekly", "analysis", "activity-jobs"}:
                command.add_argument("--cursor")
                command.add_argument("--limit", type=int, default=30)
    analyze = groups.add_parser("analyze", help="明确请求一次 AI 分析，可能产生费用")
    analyze.add_argument("--source", choices=["daily_plan", "weekly_summary"], required=True)
    analyze.add_argument("--source-id", required=True)
    analyze.add_argument("--retry-of")
    analyze.add_argument("--request-id")
    analyze.add_argument("--space")
    groups.add_parser("analysis-usage", help="本账号每日 AI 分析额度（按 UTC 日期重置）")

    for name, help_text in (
        ("progress", "知识掌握状态与证据"),
        ("next", "下一步推荐及理由"),
        ("plan", "当前学习计划"),
        ("events", "学习事件"),
        ("runs", "模型调用与用量"),
        ("diagnose", "初始诊断，可继续未完成题目"),
        ("learn", "开始或继续交互课堂"),
        ("answer", "提交单题答案"),
        ("hint", "请求提示"),
        ("lesson-complete", "记录已阅读讲解"),
    ):
        command = groups.add_parser(name, help=help_text)
        command.add_argument("--space", help="本次使用的空间 ID，不改变默认选择")
        if name in ("answer", "hint", "lesson-complete"):
            command.add_argument("id")
        if name in ("learn", "diagnose"):
            command.add_argument(
                "--no-interactive", action="store_true", help="只获取内容，不记录阅读或提交答案"
            )
        if name == "learn":
            command.add_argument(
                "--new", action="store_true", help="请求下一课堂；服务端会优先恢复未完成课堂"
            )
        if name in ("learn", "answer", "hint", "lesson-complete"):
            command.add_argument("--request-id", help="写操作幂等键，超时重试请复用")
        if name == "answer":
            command.add_argument("--answer", help="省略时从终端输入答案")
            command.add_argument("--assistance", choices=["none", "hint", "solution"], default="none")
    return parser


def read_secret(env_name, fallback_env, label, prompt):
    name = env_name or (fallback_env if os.getenv(fallback_env) else None)
    if name:
        value = os.getenv(name)
        if not value:
            raise CLIError("missing_secret", f"环境变量 {name} 为空或未设置。", 2)
        return value
    if prompt is None and not sys.stdin.isatty():
        raise CLIError("missing_secret", f"非交互模式请通过环境变量提供{label}。", 2)
    return (prompt or getpass.getpass)(f"{label}（隐藏输入）：")


def new_request_key(args):
    if not getattr(args, "request_id", None):
        args.request_id = str(uuid.uuid4())
    return args.request_id


def require_consent(args):
    if not args.accept_data_transfer:
        raise CLIError(
            "consent_required",
            "模型调用会将目标、上下文和答案发送至所选第三方，并可能产生费用；请明确添加 --accept-data-transfer。",
            2,
        )


def page_query(args):
    values = {"limit": args.limit}
    if args.cursor:
        values["cursor"] = args.cursor
    return "?" + urlencode(values)


def execute(args, client, prompt, secret_prompt, interactive, emit):
    if args.command == "auth":
        if args.action == "status":
            return client.request("GET", "/auth/me")
        if args.action == "logout":
            client.request("POST", "/auth/logout")
            client.clear_session()
            return {"message": "已退出登录，本地会话和空间选择已清除。"}
        password = read_secret(args.password_env, "STUDY_AGENT_PASSWORD", "密码", secret_prompt)
        client.clear_session()
        user = client.request(
            "POST", "/auth/" + args.action, {"username": args.username, "password": password}
        )
        client.state["user_id"] = user["id"]
        client.save_session()
        if not any(
            not cookie["secure"] or client.server.startswith("https://") for cookie in client.state["cookies"]
        ):
            raise CLIError(
                "cookie_unavailable",
                "服务未返回有效会话。HTTP 本机开发请设置 COOKIE_SECURE=false；远程请使用 HTTPS。",
            )
        return user
    if args.command == "provider":
        path = "/providers"
        if args.action == "list":
            return client.request("GET", path)
        if args.action == "add":
            demo = args.demo or args.demo_files
            if not demo:
                require_consent(args)
                if not args.model:
                    raise CLIError("missing_model", "请使用 --model 指定聊天模型名称。", 2)
            body = {
                "name": args.name,
                "provider_type": ("fake_files" if args.demo_files else "fake")
                if demo
                else ("openai_files" if args.files else "openai_compatible"),
                "embedding_model": args.embedding_model,
                "chat_model": "demo-model" if demo else args.model,
                "base_url": args.base_url,
                "api_key": "demo"
                if demo
                else read_secret(args.api_key_env, "STUDY_AGENT_API_KEY", "API Key", secret_prompt),
            }
            return client.request("POST", path, body)
        path += "/" + segment(args.id)
        if args.action == "test":
            return client.request("POST", path + "/test")
        if args.action == "capabilities":
            return client.request("GET", path + "/capabilities")
        if args.action == "remove":
            client.request("DELETE", path)
            return {"message": "模型配置已删除。"}
        body = {
            name: value
            for name, value in [("name", args.name), ("chat_model", args.model), ("base_url", args.base_url)]
            if value is not None
        }
        if args.clear_embedding_model or args.embedding_model is not None:
            body["embedding_model"] = None if args.clear_embedding_model else args.embedding_model
        if args.base_url:
            require_consent(args)
        if args.rotate_key or args.api_key_env:
            body["api_key"] = read_secret(
                args.api_key_env, "STUDY_AGENT_API_KEY", "新 API Key", secret_prompt
            )
        if not body:
            raise CLIError("empty_update", "请指定要更新的名称、模型、地址或 --rotate-key。", 2)
        return client.request("PATCH", path, body)
    if args.command == "space":
        if args.action == "list":
            return client.request("GET", "/study-spaces")
        if args.action == "create":
            data = client.request(
                "POST",
                "/study-spaces",
                {
                    "goal": args.goal,
                    "provider_id": args.provider,
                    "daily_minutes": args.minutes,
                    "target_date": args.target_date,
                    "expected_level": args.level,
                    "idempotency_key": new_request_key(args),
                },
            )
            client.state["active_space"] = data["id"]
            client.save_session()
            return data
        if args.action == "use":
            return client.select_space(args.id)
        path = "/study-spaces/" + segment(args.id)
        if args.action == "knowledge-policy":
            return client.request("PATCH", path, {"allow_general_knowledge": args.allow_general_knowledge})
        if args.action == "switch-provider":
            return client.request("PATCH", path, {"provider_id": args.provider})
        return client.request("GET", path)

    if args.command == "job":
        path = "/jobs/" + segment(args.id)
        if args.action == "wait":
            if not 1 <= args.seconds <= 3600:
                raise CLIError("invalid_wait", "--seconds 须为 1–3600。", 2)
            deadline = time.monotonic() + args.seconds
            while True:
                data = client.request("GET", path)
                if data["status"] not in {"queued", "running"}:
                    return data
                if time.monotonic() >= deadline:
                    raise CLIError("job_pending", "任务仍在处理，可稍后再次 job show/wait。")
                time.sleep(1)
        if args.action == "show":
            return client.request("GET", path)
        return client.request(
            "POST",
            path + "/" + args.action,
            {"idempotency_key": new_request_key(args)} if args.action == "retry" else None,
        )
    if args.command == "material":
        root = client.active_space(args.space) + "/materials"
        if args.action in {"upload", "reindex"} and not args.accept_file_transfer:
            raise CLIError(
                "consent_required",
                "本次文件与摘要将发送至所选服务商，可能产生费用并被远端保留；请添加 --accept-file-transfer。",
                2,
            )
        if args.action == "list":
            return client.request("GET", root)
        if args.action == "search":
            return client.request("POST", root + "/search", {"query": args.query, "mode": args.mode})
        if args.action == "upload":
            if args.file.stat().st_size > MAX_MATERIAL_BYTES:
                raise CLIError("file_too_large", "上传文件不能超过 1024 MiB；实例可设置更小上限。", 2)
            with args.file.open("rb") as source:
                return client.request(
                    "POST",
                    root,
                    content=source,
                    headers={
                        "Content-Type": "application/pdf",
                        "Content-Length": str(os.fstat(source.fileno()).st_size),
                        "X-Filename": quote(args.file.name, safe=""),
                        "X-File-Consent": "true",
                        "X-Use-Embeddings": str(args.embeddings).lower(),
                        "Idempotency-Key": new_request_key(args),
                    },
                )
        path = root + "/" + segment(args.id)
        if args.action == "reindex":
            return client.request(
                "POST",
                path + "/reindex",
                {
                    "idempotency_key": new_request_key(args),
                    "consent": True,
                    "use_embeddings": args.embeddings,
                },
            )
        if args.action == "download":
            # Never overwrite an existing local file; downloaded originals remain private.
            if args.output.exists():
                raise CLIError("output_exists", "下载路径已存在，请选择新的 --output。", 2)
            client.download(path + "/download", args.output)
            return {"message": "原始文件已下载至 " + str(args.output)}
        return client.request("DELETE" if args.action == "remove" else "GET", path)

    if args.command == "analysis-usage":
        return client.request("GET", "/analysis-usage")
    if args.command in {"inbox", "activity-jobs"}:
        path = "/" + args.command
        if args.action == "list":
            return client.request("GET", path + page_query(args))
        return client.request(
            "POST",
            path + "/" + segment(args.id) + "/" + args.action,
            {"idempotency_key": new_request_key(args)},
        )

    root = client.active_space(args.space)
    if args.command == "today":
        if args.refresh:
            return client.request(
                "POST", root + "/daily-plans/refresh", {"idempotency_key": new_request_key(args)}
            )
        return client.request("GET", root + "/daily-plans/today")
    if args.command in {"task", "suggestion", "weekly", "analysis"}:
        path = (
            root
            + {
                "task": "/tasks",
                "suggestion": "/suggestions",
                "weekly": "/weekly-summaries",
                "analysis": "/analyses",
            }[args.command]
        )
        if args.action == "list":
            return client.request("GET", path + (page_query(args) if hasattr(args, "limit") else ""))
        if args.action in {"show", "current"}:
            return client.request(
                "GET", path + "/" + ("current" if args.action == "current" else segment(args.id))
            )
        suffix = args.action if args.action == "refresh" else segment(args.id) + "/" + args.action
        return client.request("POST", path + "/" + suffix, {"idempotency_key": new_request_key(args)})
    if args.command == "analyze":
        return client.request(
            "POST",
            root + "/analyses",
            {
                "source_kind": args.source,
                "source_id": args.source_id,
                "retry_of": args.retry_of,
                "idempotency_key": new_request_key(args),
            },
        )
    if args.command == "algorithms":
        return client.request("GET", root + "/algorithms")
    if args.command == "report":
        return client.request("GET", root + "/report?days=" + str(args.days))
    if args.command == "review":
        if args.action == "list":
            return client.request("GET", root + "/reviews")
        if args.action == "start":
            result = client.request(
                "POST",
                root + "/reviews/start",
                {"concept_id": args.concept, "idempotency_key": new_request_key(args)},
            )
            if interactive:
                classroom(client, root, result["lesson"], prompt, emit, lambda: str(uuid.uuid4()))
                return client.request("GET", root + "/reviews/" + segment(result["id"]))
            return result
        answer = args.answer
        if answer is None:
            if not interactive:
                raise CLIError("missing_answer", "非交互复习需要 --answer", 2)
            answer = prompt("你的答案：")
        return client.request(
            "POST",
            root + "/reviews/" + segment(args.id) + "/submit",
            {
                "item_id": args.item,
                "answer": answer,
                "memory_rating": args.rating,
                "idempotency_key": new_request_key(args),
            },
        )
    if args.command == "progress":
        return {
            "profile": client.request("GET", root + "/profile"),
            "concepts": client.request("GET", root + "/concepts"),
        }
    suffixes = {"next": "next-action", "plan": "plan", "events": "events", "runs": "runs"}
    if args.command in suffixes:
        return client.request("GET", root + "/" + suffixes[args.command])
    if args.command == "diagnose":
        data = client.request("POST", root + "/diagnostics")
        if interactive:
            emit(data["notice"])
            practice(client, root, data["items"], data["attempts"], prompt, emit, lambda: str(uuid.uuid4()))
            return client.request("GET", root + "/next-action")
        return data
    if args.command == "learn":
        # A read receipt is not completion of the associated practice, even with --new.
        data = client.request("GET", root + "/lessons/current")
        if data is None or (
            data["completed"] and all(q["id"] in data.get("attempts", {}) for q in data["exercises"])
        ):
            data = client.request("POST", root + "/lessons", {"idempotency_key": new_request_key(args)})
        if interactive:
            classroom(client, root, data, prompt, emit, lambda: str(uuid.uuid4()))
            return client.request("GET", root + "/next-action")
        return data
    if args.command == "answer":
        answer = args.answer
        if answer is None:
            if not interactive:
                raise CLIError("missing_answer", "非交互模式请使用 --answer 提供答案。", 2)
            answer = prompt("你的答案：")
        return client.request(
            "POST",
            root + "/attempts",
            {
                "item_id": args.id,
                "answer": answer,
                "assistance_level": args.assistance,
                "idempotency_key": new_request_key(args),
            },
        )
    if args.command == "hint":
        return client.request(
            "POST", root + "/items/" + segment(args.id) + "/hint", {"idempotency_key": new_request_key(args)}
        )
    return client.request(
        "POST",
        root + "/lessons/" + segment(args.id) + "/complete",
        {"idempotency_key": new_request_key(args)},
    )


def run(argv=None, *, transport=None, input_fn=None, secret_fn=None):
    args, client = None, None
    try:
        args = build_parser().parse_args(argv)
        if not 1 <= args.timeout <= 300:
            raise CLIError("invalid_timeout", "--timeout 必须为 1–300 秒。", 2)
        store = StateStore(args.config_dir)
        client = APIClient(args.server, store, args.timeout, transport)
        interactive = (
            not args.json
            and not getattr(args, "no_interactive", False)
            and (sys.stdin.isatty() or input_fn is not None)
        )
        # The standalone answer command can prompt in a terminal too.
        data = execute(
            args, client, input_fn or input, secret_fn, interactive, lambda text: print(safe_text(text))
        )
        print(json.dumps(data, ensure_ascii=False) if args.json else safe_text(human_output(data)))
        return 0
    except CLIError as exc:
        if args and args.json:
            error = {"error": {"code": exc.code, "message": exc.message}}
            if getattr(args, "request_id", None):
                error["request_id"] = args.request_id
            print(json.dumps(error, ensure_ascii=False))
        else:
            print(safe_text(f"错误 [{exc.code}]：{exc.message}"), file=sys.stderr)
            if args and getattr(args, "request_id", None):
                print(f"请求幂等键：{args.request_id}（重试可使用 --request-id）", file=sys.stderr)
        return exc.exit_code
    except (EOFError, KeyboardInterrupt, StopIteration):
        message = {"message": "已停止，已提交的学习记录已保留。"}
        print(json.dumps(message, ensure_ascii=False) if args and args.json else message["message"])
        return 130
    except OSError:
        message = "无法读写本地会话目录，请检查 --config-dir 和目录权限。"
        if args and args.json:
            print(json.dumps({"error": {"code": "local_io_error", "message": message}}, ensure_ascii=False))
        else:
            print(message, file=sys.stderr)
        return 1
    except SystemExit as exc:
        return exc.code
    finally:
        if client:
            client.close()


def main():
    sys.exit(run())
