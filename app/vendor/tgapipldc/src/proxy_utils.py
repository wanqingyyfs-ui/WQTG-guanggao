from dataclasses import dataclass


@dataclass
class ParsedProxy:
    raw_proxy: str
    username: str
    password: str
    host: str
    port: int

    @property
    def requests_proxy_url(self) -> str:
        return f"http://{self.username}:{self.password}@{self.host}:{self.port}"

    @property
    def requests_proxies(self) -> dict:
        proxy_url = self.requests_proxy_url
        return {
            "http": proxy_url,
            "https": proxy_url,
        }

    @property
    def playwright_proxy(self) -> dict:
        return {
            "server": f"http://{self.host}:{self.port}",
            "username": self.username,
            "password": self.password,
        }

    @property
    def masked_raw_proxy(self) -> str:
        return f"{self.username}:******@{self.host}:{self.port}"


def parse_raw_proxy(raw_proxy: str) -> ParsedProxy:
    """
    支持这种格式：

    username:password@hostname:port

    示例：

    Qg8Ajet4-res-us-sid-571609344-sidtime-70:xxxxxx@proxy.global.ip2up.com:12348
    """

    if not raw_proxy:
        raise ValueError("代理为空")

    raw_proxy = raw_proxy.strip()

    if raw_proxy.startswith("http://"):
        raw_proxy = raw_proxy[len("http://"):]

    if raw_proxy.startswith("https://"):
        raw_proxy = raw_proxy[len("https://"):]

    if "@" not in raw_proxy:
        raise ValueError(f"代理格式错误，缺少 @：{raw_proxy}")

    auth_part, host_part = raw_proxy.rsplit("@", 1)

    if ":" not in auth_part:
        raise ValueError(f"代理格式错误，账号密码部分缺少冒号：{raw_proxy}")

    username, password = auth_part.split(":", 1)

    if ":" not in host_part:
        raise ValueError(f"代理格式错误，host 端口部分缺少冒号：{raw_proxy}")

    host, port_text = host_part.rsplit(":", 1)

    if not username:
        raise ValueError("代理用户名为空")

    if not password:
        raise ValueError("代理密码为空")

    if not host:
        raise ValueError("代理 host 为空")

    try:
        port = int(port_text)
    except ValueError:
        raise ValueError(f"代理端口不是数字：{port_text}")

    return ParsedProxy(
        raw_proxy=raw_proxy,
        username=username,
        password=password,
        host=host,
        port=port,
    )