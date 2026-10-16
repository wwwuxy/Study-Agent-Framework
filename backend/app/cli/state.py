import json
import os
import tempfile
from pathlib import Path

from app.cli.errors import CLIError


def default_config_dir() -> Path:
    return Path(
        os.environ.get("STUDY_AGENT_CONFIG_DIR")
        or Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "study-agent"
    )


class StateStore:
    """Only session cookies and selection metadata live here, never passwords or model keys."""

    def __init__(self, directory: Path):
        self.directory = directory.expanduser()
        self.path = self.directory / "state.json"
        self.data = {"version": 1, "servers": {}}
        if self.path.is_symlink():
            raise CLIError("invalid_local_state", "会话文件不能是符号链接，请选择独立配置目录。")
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                if (
                    not isinstance(data, dict)
                    or data.get("version") != 1
                    or not isinstance(data.get("servers"), dict)
                ):
                    raise ValueError()
                for server in data["servers"].values():
                    if not isinstance(server, dict) or not isinstance(server.get("cookies", []), list):
                        raise ValueError()
                    if any(
                        not isinstance(c, dict)
                        or not isinstance(c.get("name"), str)
                        or not isinstance(c.get("value"), str)
                        for c in server.get("cookies", [])
                    ):
                        raise ValueError()
                    for cookie in server.get("cookies", []):
                        if any(
                            not isinstance(cookie.get(field, default), str)
                            for field, default in [("domain", ""), ("path", "/")]
                        ):
                            raise ValueError()
                        if any(
                            not isinstance(cookie.get(field, False), bool)
                            for field in ("secure", "domain_specified", "domain_initial_dot")
                        ):
                            raise ValueError()
                        if cookie.get("expires") is not None and type(cookie["expires"]) is not int:
                            raise ValueError()
                    if any(
                        server.get(field) is not None and not isinstance(server[field], str)
                        for field in ("active_space", "user_id")
                    ):
                        raise ValueError()
                self.data = data
            except (ValueError, TypeError):
                raise CLIError(
                    "invalid_local_state", "本地会话文件损坏，未覆盖原文件；请移走后重新登录。"
                ) from None

    def server(self, url):
        return self.data["servers"].setdefault(url, {"cookies": [], "active_space": None, "user_id": None})

    def save(self):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.directory.chmod(0o700)
        descriptor, temporary = tempfile.mkstemp(prefix=".state-", dir=self.directory)
        try:
            with os.fdopen(descriptor, "w") as file:
                json.dump(self.data, file, ensure_ascii=False)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
            self.path.chmod(0o600)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
