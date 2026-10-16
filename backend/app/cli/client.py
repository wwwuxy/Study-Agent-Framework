from http.cookiejar import Cookie
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

from app.cli.errors import CLIError


def normalize_server(url: str) -> str:
    try:
        parsed = urlsplit(url)
        _ = parsed.port
    except ValueError:
        raise CLIError("invalid_server", "服务器地址或端口无效。", 2) from None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise CLIError("invalid_server", "服务器地址须为无凭证和查询参数的 HTTP(S) 地址。", 2)
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise CLIError("insecure_server", "远程服务器须使用 HTTPS；本机 localhost 可使用 HTTP。", 2)
    return urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/"), "", ""))


def segment(value):
    return quote(str(value), safe="")


class APIClient:
    def __init__(self, server, store, timeout=100, transport=None):
        self.server, self.store = normalize_server(server), store
        self.state = store.server(self.server)
        self.http = httpx.Client(
            timeout=timeout, transport=transport, follow_redirects=False, trust_env=False
        )
        try:
            for cookie in self.state.get("cookies", []):
                self.http.cookies.jar.set_cookie(
                    Cookie(
                        version=0,
                        name=cookie["name"],
                        value=cookie["value"],
                        port=None,
                        port_specified=False,
                        domain=cookie.get("domain", ""),
                        domain_specified=cookie.get("domain_specified", False),
                        domain_initial_dot=cookie.get("domain_initial_dot", False),
                        path=cookie.get("path", "/"),
                        path_specified=True,
                        secure=cookie.get("secure", False),
                        expires=cookie.get("expires"),
                        discard=False,
                        comment=None,
                        comment_url=None,
                        rest={"HttpOnly": None},
                        rfc2109=False,
                    )
                )
        except (TypeError, ValueError):
            self.http.close()
            raise CLIError(
                "invalid_local_state", "本地会话 Cookie 无效，请移走会话文件后重新登录。"
            ) from None

    def close(self):
        self.http.close()

    def save_session(self):
        self.state["cookies"] = [
            {
                "name": c.name,
                "value": c.value,
                "domain": c.domain,
                "path": c.path,
                "secure": c.secure,
                "expires": c.expires,
                "domain_specified": c.domain_specified,
                "domain_initial_dot": c.domain_initial_dot,
            }
            for c in self.http.cookies.jar
            if c.name == "study_session" and not c.is_expired()
        ]
        self.store.save()

    def clear_session(self):
        self.http.cookies.clear()
        self.state.update(cookies=[], active_space=None, user_id=None)
        self.store.save()

    def request(self, method, path, body=None):
        try:
            response = self.http.request(method, self.server + "/api/v1" + path, json=body)
        except httpx.TimeoutException:
            raise CLIError(
                "request_timeout", "请求超时；写操作可能已完成，可使用原 --request-id 重试或查询进度。"
            ) from None
        except httpx.RequestError:
            raise CLIError(
                "connection_failed", "无法连接 StudyAgent 服务。请先运行 scripts/serve.sh，或检查 --server。"
            ) from None
        if response.status_code == 401:
            self.clear_session()
        if response.status_code == 204:
            return None
        try:
            data = response.json()
        except ValueError:
            raise CLIError("invalid_response", "服务未返回 JSON；请检查服务器地址与反向代理配置。") from None
        if response.status_code >= 300:
            error = data.get("error", {}) if isinstance(data, dict) else {}
            if not isinstance(error, dict):
                error = {}
            code, message = error.get("code"), error.get("message")
            raise CLIError(
                code if isinstance(code, str) else "request_failed",
                message if isinstance(message, str) else f"请求失败（HTTP {response.status_code}）。",
            )
        return data

    def active_space(self, explicit=None):
        space_id = explicit or self.state.get("active_space")
        if not space_id:
            raise CLIError("no_active_space", "尚未选择学习空间。请运行 space create 或 space use ID。", 2)
        return "/study-spaces/" + segment(space_id)

    def select_space(self, space_id):
        data = self.request("GET", "/study-spaces/" + segment(space_id))
        self.state["active_space"] = data["id"]
        self.save_session()
        return data
