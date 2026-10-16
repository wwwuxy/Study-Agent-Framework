import asyncio
import hashlib
import hmac
import ipaddress
import secrets
import socket
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken

from app.providers.base import ProviderError


class CredentialVault:
    def __init__(self, key: str):
        if not key:
            raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY 未配置，请先运行 scripts/setup.sh")
        self.fernet = Fernet(key.encode())

    def encrypt(self, secret: str) -> str:
        return self.fernet.encrypt(secret.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self.fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken:
            raise ProviderError("credential_unavailable", "无法解密凭证，请更新模型密钥", 503) from None


def password_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return f"{salt}:{digest}"


def check_password(password: str, stored: str) -> bool:
    salt, expected = stored.split(":")
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return hmac.compare_digest(digest, expected)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def resolve_host(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    records = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(record[4][0] for record in records))


async def validate_base_url(url: str, allow_private=False, resolver=None) -> tuple[str, str]:
    """Return a validated address for connection pinning. Never follow redirects."""
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or (parsed.scheme != "https" and not allow_private)
    ):
        raise ProviderError("unsafe_provider_url", "模型地址须为无凭证、查询参数的 HTTPS 地址", 422)
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        addresses = await asyncio.wait_for((resolver or resolve_host)(parsed.hostname, port), timeout=5)
        if not addresses or (
            not allow_private and any(not ipaddress.ip_address(a).is_global for a in addresses)
        ):
            raise ValueError("non-public address")
    except (ValueError, OSError, TimeoutError):
        raise ProviderError("unsafe_provider_url", "模型地址不可解析或指向非公网网络", 422) from None
    return parsed.hostname, addresses[0]
