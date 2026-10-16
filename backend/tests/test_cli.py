import json
import stat

import httpx
import pytest

from app.cli.main import run


@pytest.fixture
def cli(client, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLI_TEST_PASSWORD", "cli-password-2026")
    state_dir = tmp_path / "cli"

    def forward(request):
        client.cookies.clear()
        response = client.request(
            request.method, request.url.path, headers=dict(request.headers), content=request.content
        )
        return httpx.Response(
            response.status_code, headers=list(response.headers.multi_items()), content=response.content
        )

    def invoke(*args, answers=(), secrets=(), json_output=True):
        answer_iter, secret_iter = iter(answers), iter(secrets)
        code = run(
            [
                "--config-dir",
                str(state_dir),
                "--server",
                "http://localhost:8000",
                *(["--json"] if json_output else []),
                *args,
            ],
            transport=httpx.MockTransport(forward),
            input_fn=lambda prompt: next(answer_iter),
            secret_fn=lambda prompt: next(secret_iter),
        )
        captured = capsys.readouterr()
        return (
            code,
            (json.loads(captured.out) if captured.out.strip() else None) if json_output else captured.out,
            captured.err,
        )

    invoke.state_dir = state_dir
    return invoke


def setup_space(cli):
    assert cli("auth", "register", "--username", "cliuser", "--password-env", "CLI_TEST_PASSWORD")[0] == 0
    code, config, _ = cli("provider", "add", "--demo", "--name", "CLI demo")
    assert code == 0
    assert cli("provider", "test", config["id"])[0] == 0
    code, space, _ = cli(
        "space", "create", "--goal", "学习操作系统", "--provider", config["id"], "--request-id", "cli-space"
    )
    assert code == 0
    return config["id"], space["id"]


def test_cli_learning_loop_across_independent_invocations(cli):
    pid, sid = setup_space(cli)
    assert cli("auth", "status")[1]["username"] == "cliuser"
    assert cli("space", "list")[1][0]["id"] == sid
    assert cli("next")[1]["action"] == "DIAGNOSE"
    code, diagnosis, _ = cli("diagnose")
    assert code == 0 and len(diagnosis["items"]) == 5
    for index, item in enumerate(diagnosis["items"]):
        code, result, _ = cli("answer", item["id"], "--answer", "A", "--request-id", f"cli-answer-{index}")
        assert code == 0 and result["is_correct"] is True
    code, lesson, _ = cli("learn", "--request-id", "cli-lesson")
    assert code == 0 and lesson["explanation"]
    assert cli("lesson-complete", lesson["id"])[0] == 0
    code, item_result, _ = cli("answer", lesson["exercises"][0]["id"], "--answer", "A")
    assert code == 0
    code, progress, _ = cli("progress")
    assert code == 0 and progress["profile"]["states"]
    assert cli("events")[1]
    assert cli("runs")[1]
    assert cli("plan")[1]["next_action"]["reason"]
    assert cli("provider", "list")[1][0]["id"] == pid
    assert cli("auth", "logout")[0] == 0
    code, error, _ = cli("progress")
    assert code != 0 and error["error"]["code"] == "no_active_space"


def test_cli_session_permissions_and_secrets_not_stored(cli):
    setup_space(cli)
    state = cli.state_dir / "state.json"
    assert stat.S_IMODE(state.stat().st_mode) == 0o600
    assert stat.S_IMODE(cli.state_dir.stat().st_mode) == 0o700
    assert "cli-password-2026" not in state.read_text()
    assert "demo-secret" not in state.read_text()
    assert cli("auth", "status")[0] == 0


def test_cli_hint_is_preserved_and_submission_is_idempotent(cli):
    _, sid = setup_space(cli)
    item = cli("diagnose")[1]["items"][0]
    assert cli("hint", item["id"])[1]["hint"]
    first = cli("answer", item["id"], "--answer", "A", "--request-id", "one")
    second = cli("answer", item["id"], "--answer", "A", "--request-id", "one")
    assert first[0] == second[0] == 0 and first[1] == second[1]
    assert first[1]["assistance_level"] == "hint"


def test_cli_login_as_different_user_drops_selected_space(cli):
    setup_space(cli)
    assert cli("auth", "register", "--username", "another", "--password-env", "CLI_TEST_PASSWORD")[0] == 0
    assert cli("space", "list")[1] == []
    assert cli("progress")[1]["error"]["code"] == "no_active_space"


def test_cli_failed_login_does_not_leave_old_account_active(cli, monkeypatch):
    setup_space(cli)
    monkeypatch.setenv("WRONG_PASSWORD", "wrong-password-2026")
    assert cli("auth", "login", "--username", "cliuser", "--password-env", "WRONG_PASSWORD")[0] != 0
    assert cli("auth", "status")[1]["error"]["code"] == "unauthenticated"


def test_cli_json_errors_and_transport_failures_do_not_traceback(tmp_path, capsys):
    def fail(request):
        raise httpx.ConnectError("do not echo private upstream details")

    result = run(
        ["--config-dir", str(tmp_path / "state"), "--json", "auth", "status"],
        transport=httpx.MockTransport(fail),
    )
    captured = capsys.readouterr()
    assert result != 0
    assert json.loads(captured.out)["error"]["code"] == "connection_failed"
    assert "Traceback" not in captured.err and "private upstream" not in captured.out


def test_cli_remote_credentials_need_explicit_data_transfer_consent(cli, monkeypatch):
    cli("auth", "register", "--username", "cliuser", "--password-env", "CLI_TEST_PASSWORD")
    monkeypatch.setenv("CLI_TEST_KEY", "SENSITIVE_API_KEY")
    result = cli("provider", "add", "--name", "Real", "--model", "chat", "--api-key-env", "CLI_TEST_KEY")
    assert result[0] != 0 and result[1]["error"]["code"] == "consent_required"
    assert "SENSITIVE_API_KEY" not in str(result)


def test_cli_rejects_corrupt_state_without_overwriting_it(tmp_path, capsys):
    folder = tmp_path / "cli"
    folder.mkdir()
    state = folder / "state.json"
    state.write_text("invalid state")
    result = run(["--config-dir", str(folder), "--json", "auth", "status"])
    assert result != 0
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "invalid_local_state"
    assert state.read_text() == "invalid state"


def test_cli_does_not_send_session_to_different_server(cli, capsys):
    setup_space(cli)
    requests = []

    def remote(request):
        requests.append(request)
        return httpx.Response(401, json={"error": {"code": "unauthenticated", "message": "请登录"}})

    run(
        ["--config-dir", str(cli.state_dir), "--server", "https://other.example", "--json", "auth", "status"],
        transport=httpx.MockTransport(remote),
    )
    assert "cookie" not in requests[0].headers


def test_cli_expired_cookie_is_not_resent(cli):
    setup_space(cli)
    state_file = cli.state_dir / "state.json"
    state = json.loads(state_file.read_text())
    for server in state["servers"].values():
        for cookie in server["cookies"]:
            cookie["expires"] = 1
    state_file.write_text(json.dumps(state))
    assert cli("auth", "status")[1]["error"]["code"] == "unauthenticated"


def test_interactive_diagnosis_hints_skip_quit_and_resume(cli):
    setup_space(cli)
    result = cli("diagnose", answers=["/hint", "A", "/skip", "/quit"], json_output=False)
    assert result[0] == 0
    data = cli("diagnose")[1]
    assert sum(item["answered"] for item in data["items"]) == 1
    assert next(iter(data["attempts"].values()))["assistance_level"] == "hint"
    assert cli("diagnose", answers=["A"] * 4, json_output=False)[0] == 0
    assert all(item["answered"] for item in cli("diagnose")[1]["items"])


def test_interactive_lesson_quit_does_not_mark_read_then_can_resume(cli):
    setup_space(cli)
    assert cli("learn", answers=["/quit"], json_output=False)[0] == 0
    assert not any(e["type"] == "lesson_viewed" for e in cli("events")[1])
    assert cli("learn", answers=["", "A"], json_output=False)[0] == 0
    assert any(e["type"] == "lesson_viewed" for e in cli("events")[1])
    assert any(e["type"] == "assessment_submitted" for e in cli("events")[1])


def test_cli_safe_rendering_never_executes_terminal_control_sequences():
    from app.cli.render import safe_text

    assert safe_text("知识点\x1b[31m红色\x1b[0m\x1b]52;c;malicious\x07\r下一行") == "知识点红色下一行"


def test_secure_cookie_over_http_does_not_claim_login_success(client, tmp_path, capsys):
    client.app.state.settings.cookie_secure = True

    def forward(request):
        response = client.request(
            request.method, request.url.path, headers=dict(request.headers), content=request.content
        )
        return httpx.Response(
            response.status_code, headers=list(response.headers.multi_items()), content=response.content
        )

    code = run(
        ["--config-dir", str(tmp_path / "secure"), "--json", "auth", "register", "--username", "secureuser"],
        transport=httpx.MockTransport(forward),
        secret_fn=lambda _: "secure-password-2026",
    )
    assert code != 0
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "cookie_unavailable"


@pytest.mark.parametrize(
    "server",
    [
        "https://[bad",
        "https://user:secret@example.com",
        "http://remote.example",
        "https://example.com?key=secret",
    ],
)
def test_invalid_server_is_a_clean_error(server, tmp_path, capsys):
    result = run(["--config-dir", str(tmp_path / "cli"), "--server", server, "--json", "auth", "status"])
    captured = capsys.readouterr()
    assert result != 0
    assert json.loads(captured.out)["error"]["code"] in {"invalid_server", "insecure_server"}
    assert "secret" not in captured.out


def test_bad_cookie_expiry_is_rejected_without_a_traceback(cli):
    setup_space(cli)
    state_file = cli.state_dir / "state.json"
    state = json.loads(state_file.read_text())
    next(iter(state["servers"].values()))["cookies"][0]["expires"] = "bad-expiry"
    state_file.write_text(json.dumps(state))
    result = cli("auth", "status")
    assert result[0] != 0 and result[1]["error"]["code"] == "invalid_local_state"


@pytest.mark.parametrize("field,value", [("domain", 42), ("path", []), ("secure", "false")])
def test_malformed_cookie_metadata_does_not_crash_or_overwrite(cli, field, value):
    setup_space(cli)
    state_file = cli.state_dir / "state.json"
    state = json.loads(state_file.read_text())
    next(iter(state["servers"].values()))["cookies"][0][field] = value
    original = json.dumps(state)
    state_file.write_text(original)
    result = cli("auth", "status")
    assert result[0] != 0 and result[1]["error"]["code"] == "invalid_local_state"
    assert state_file.read_text() == original


def test_malformed_proxy_error_is_reported_cleanly(tmp_path, capsys):
    code = run(
        ["--config-dir", str(tmp_path / "state"), "--json", "auth", "status"],
        transport=httpx.MockTransport(lambda _: httpx.Response(502, json={"error": "bad gateway"})),
    )
    assert code != 0
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "request_failed"


def test_learn_new_restores_read_lesson_with_unanswered_practice(cli):
    setup_space(cli)
    first = cli("learn")[1]
    assert cli("lesson-complete", first["id"])[0] == 0
    code, restored, _ = cli("learn", "--new")
    assert code == 0
    assert restored["id"] == first["id"]
    assert restored["exercises"][0]["id"] == first["exercises"][0]["id"]


def test_cli_material_workflow_requires_consent_and_preserves_download(cli, tmp_path):
    from app.providers.probe_pdf import make_probe_pdf

    cli("auth", "register", "--username", "fileuser", "--password-env", "CLI_TEST_PASSWORD")
    code, config, _ = cli("provider", "add", "--demo-files", "--name", "资料演示")
    assert code == 0
    assert cli("provider", "test", config["id"])[0] == 0
    assert cli("space", "create", "--goal", "学习操作系统", "--provider", config["id"])[0] == 0
    path = tmp_path / "教材.pdf"
    path.write_bytes(make_probe_pdf("USER_MATERIAL"))
    assert cli("material", "upload", str(path))[1]["error"]["code"] == "consent_required"
    code, asset, _ = cli(
        "material", "upload", str(path), "--accept-file-transfer", "--request-id", "cli-file"
    )
    assert code == 0
    assert cli("job", "run", asset["job_id"])[1]["status"] == "succeeded"
    assert cli("material", "list")[1][0]["status"] == "ready"
    assert cli("material", "search", "操作系统")[1]["results"]
    assert cli("material", "show", asset["id"])[1]["sections"]
    output = tmp_path / "下载.pdf"
    assert cli("material", "download", asset["id"], "--output", str(output))[0] == 0
    assert output.read_bytes() == path.read_bytes()
    assert cli("material", "download", asset["id"], "--output", str(output))[0] != 0
    assert (
        cli("space", "knowledge-policy", asset["space_id"], "--allow-general-knowledge")[1][
            "allow_general_knowledge"
        ]
        is True
    )
    code, deleted, _ = cli("material", "remove", asset["id"])
    assert code == 0 and cli("job", "run", deleted["job_id"])[1]["status"] == "succeeded"
