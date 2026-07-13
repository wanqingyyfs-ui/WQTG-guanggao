from dataclasses import dataclass
from urllib.parse import quote, unquote, urlsplit


@dataclass
class ParsedProxy:
    raw_proxy: str
    username: str
    password: str
    host: str
    port: int
    scheme: str = "http"

    @property
    def server(self) -> str:
        host = f"[{self.host}]" if ":" in self.host and not self.host.startswith("[") else self.host
        return f"{self.scheme}://{host}:{self.port}"

    @property
    def requests_proxy_url(self) -> str:
        if not self.username and not self.password:
            return self.server
        username = quote(self.username, safe="")
        password = quote(self.password, safe="")
        return f"{self.scheme}://{username}:{password}@{self.server.split('://', 1)[1]}"

    @property
    def requests_proxies(self) -> dict:
        proxy_url = self.requests_proxy_url
        return {"http": proxy_url, "https": proxy_url}

    @property
    def playwright_proxy(self) -> dict:
        result = {"server": self.server}
        if self.username:
            result["username"] = self.username
        if self.password:
            result["password"] = self.password
        return result

    @property
    def masked_raw_proxy(self) -> str:
        if self.username:
            return f"{self.username}:******@{self.host}:{self.port}"
        return f"{self.host}:{self.port}"


def parse_raw_proxy(raw_proxy: str) -> ParsedProxy:
    """Parse an HTTP(S)/SOCKS proxy into Playwright's official proxy shape.

    Supported formats:
    - username:password@hostname:port
    - http://username:password@hostname:port
    - https://username:password@hostname:port
    - socks5://username:password@hostname:port
    - hostname:port

    Credentials may be raw or percent-encoded. Splitting authentication before
    URL parsing also preserves characters such as ``@``, ``#`` and ``?`` in
    passwords supplied by proxy vendors.
    """
    original = str(raw_proxy or "").strip()
    if not original:
        raise ValueError("代理为空")

    if "://" in original:
        scheme, remainder = original.split("://", 1)
        scheme = scheme.lower()
    else:
        scheme, remainder = "http", original
    if scheme not in {"http", "https", "socks5"}:
        raise ValueError(f"不支持的代理协议：{scheme}")

    username = ""
    password = ""
    host_part = remainder
    if "@" in remainder:
        auth_part, host_part = remainder.rsplit("@", 1)
        if ":" not in auth_part:
            raise ValueError("代理账号密码部分缺少冒号")
        raw_username, raw_password = auth_part.split(":", 1)
        username = unquote(raw_username)
        password = unquote(raw_password)

    parsed_host = urlsplit(f"//{host_part}")
    host = parsed_host.hostname or ""
    try:
        port = parsed_host.port
    except ValueError as exc:
        raise ValueError(f"代理端口不是有效数字：{original}") from exc

    if not host:
        raise ValueError(f"代理 host 为空：{original}")
    if port is None:
        raise ValueError(f"代理格式错误，缺少端口：{original}")
    if not 1 <= int(port) <= 65535:
        raise ValueError(f"代理端口超出范围：{port}")
    if bool(username) != bool(password):
        raise ValueError("代理用户名和密码必须同时填写")
    if password and set(password) == {"*"}:
        raise ValueError("代理密码是脱敏值，不能用于认证；请重新保存完整 raw_proxy")

    return ParsedProxy(
        raw_proxy=original,
        username=username,
        password=password,
        host=host,
        port=int(port),
        scheme=scheme,
    )
