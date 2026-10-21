from test_cli import cli, setup_space  # noqa: F401, F811


def test_cli_activity_roundtrip(cli):  # noqa: F811
    setup_space(cli)
    assert cli("today")[1]["plan"] is None
    assert cli("weekly", "current")[1]["preview"] is True
    assert cli("analysis-usage")[1]["calls"] == 0
    code, plan, _ = cli("today", "--refresh", "--request-id", "cli-day")
    assert code == 0
    task = plan["slots"][0]["task"]
    args = ("task", "start", task["id"], "--request-id", "cli-start")
    code, started, _ = cli(*args)
    assert code == 0 and started["execution_kind"] == "diagnostic"
    assert cli(*args)[1] == started
    assert cli("task", "complete", task["id"])[0] != 0
    assert cli("task", "postpone", task["id"])[1]["status"] == "postponed"
    assert cli("task", "list")[0] == 0
    assert cli("suggestion", "list")[0] == 0
    assert cli("activity-jobs", "list", "--limit", "1")[1]["items"] == []
    assert cli("inbox", "list", "--limit", "1")[0] == 0
    week = cli("weekly", "refresh")[1]
    assert cli("weekly", "show", week["id"])[1] == week
    assert cli("weekly", "list", "--limit", "1")[1]["items"][0]["id"] == week["id"]
    assert cli("analysis-usage")[1]["calls"] == 0
    args = ("analyze", "--source", "weekly_summary", "--source-id", week["id"], "--request-id", "cli-ai")
    result = cli(*args)[1]
    assert result["status"] == "completed"
    assert cli(*args)[1] == result
    assert cli("analysis", "show", result["id"])[1] == result
    assert cli("analysis", "list")[1]["items"][0]["id"] == result["id"]
    assert cli("analysis-usage")[1]["calls"] == 1
    for command in [("today",), ("weekly", "current"), ("inbox", "list"), ("analysis-usage",)]:
        code, text, _ = cli(*command, json_output=False)
        assert code == 0 and text.strip() and "lease_token" not in text
