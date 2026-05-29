from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse, unquote

SUPPORTED_PROXY_TYPES = {"socks5", "http"}
DEFAULT_PROXY_TYPE = "socks5"


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y", "on", "是", "启用", "开启"}:
            return True
        if text in {"0", "false", "no", "n", "off", "否", "禁用", "关闭"}:
            return False
    return bool(value)


def _safe_port(value: Any) -> int:
    try:
        port = int(str(value or "").strip())
    except (TypeError, ValueError):
        return 0
    return port if 1 <= port <= 65535 else 0


def _normalize_proxy_type(value: Any) -> str:
    proxy_type = str(value or DEFAULT_PROXY_TYPE).strip().lower()
    if proxy_type in {"socks", "socks5h"}:
        proxy_type = "socks5"
    if proxy_type not in SUPPORTED_PROXY_TYPES:
        proxy_type = DEFAULT_PROXY_TYPE
    return proxy_type


def parse_proxy_text(raw_proxy: str, default_proxy_type: str = DEFAULT_PROXY_TYPE) -> dict[str, Any]:
    """Parse common proxy text formats.

    Supported examples:
    - 103.23.130.28:1337:username:password
    - username:password@103.23.130.28:1337
    - socks5://username:password@103.23.130.28:1337
    - http://username:password@103.23.130.28:1337
    - 103.23.130.28:1337
    """
    raw_text = str(raw_proxy or "").strip()
    if not raw_text:
        return {}

    proxy_type = _normalize_proxy_type(default_proxy_type)
    parsed_text = raw_text
    if "://" not in parsed_text and "@" in parsed_text:
        parsed_text = f"{proxy_type}://{parsed_text}"

    if "://" in parsed_text:
        parsed = urlparse(parsed_text)
        scheme = _normalize_proxy_type(parsed.scheme or proxy_type)
        host = str(parsed.hostname or "").strip()
        port = _safe_port(parsed.port)
        username = unquote(parsed.username or "")
        password = unquote(parsed.password or "")
        return {
            "enabled": True,
            "proxy_type": scheme,
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "raw_proxy": raw_text,
        }

    parts = raw_text.split(":")
    if len(parts) < 2:
        return {
            "enabled": True,
            "proxy_type": proxy_type,
            "host": raw_text,
            "port": 0,
            "username": "",
            "password": "",
            "raw_proxy": raw_text,
        }

    host = parts[0].strip()
    port = _safe_port(parts[1])
    username = parts[2].strip() if len(parts) >= 3 else ""
    password = ":".join(parts[3:]).strip() if len(parts) >= 4 else ""
    return {
        "enabled": True,
        "proxy_type": proxy_type,
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "raw_proxy": raw_text,
    }


def normalize_proxy_config(value: Any, *, strict: bool = False) -> dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    raw_proxy = str(data.get("raw_proxy", "") or "").strip()
    proxy_type = _normalize_proxy_type(data.get("proxy_type", DEFAULT_PROXY_TYPE))

    parsed: dict[str, Any] = {}
    if raw_proxy:
        parsed = parse_proxy_text(raw_proxy, proxy_type)
        proxy_type = _normalize_proxy_type(parsed.get("proxy_type", proxy_type))

    enabled = _to_bool(data.get("enabled"), bool(raw_proxy or parsed))
    host = str(data.get("host", parsed.get("host", "")) or "").strip()
    port = _safe_port(data.get("port", parsed.get("port", 0)))
    username = str(data.get("username", parsed.get("username", "")) or "").strip()
    password = str(data.get("password", parsed.get("password", "")) or "")
    remark = str(data.get("remark", "") or "")

    if raw_proxy and parsed:
        host = str(parsed.get("host", host) or "").strip()
        port = _safe_port(parsed.get("port", port))
        username = str(parsed.get("username", username) or "").strip()
        password = str(parsed.get("password", password) or "")

    result = {
        "enabled": bool(enabled),
        "proxy_type": proxy_type,
        "host": host,
        "port": int(port),
        "username": username,
        "password": password,
        "raw_proxy": raw_proxy,
        "remark": remark,
    }

    if strict and result["enabled"]:
        validate_proxy_config(result)

    return result


def validate_proxy_config(config: dict[str, Any]) -> None:
    if not _to_bool(config.get("enabled"), False):
        return
    proxy_type = _normalize_proxy_type(config.get("proxy_type"))
    host = str(config.get("host", "") or "").strip()
    port = _safe_port(config.get("port"))
    if proxy_type not in SUPPORTED_PROXY_TYPES:
        raise ValueError("代理类型只支持 socks5 或 http")
    if not host:
        raise ValueError("启用代理时代理地址不能为空")
    if port <= 0:
        raise ValueError("启用代理时端口必须是 1-65535")


def mask_proxy_config(config: dict[str, Any] | None) -> str:
    data = normalize_proxy_config(config or {})
    if not data.get("enabled"):
        return "直连"
    auth = ""
    if str(data.get("username", "") or "").strip():
        auth = "***:***@"
    return f"{data.get('proxy_type', DEFAULT_PROXY_TYPE)}://{auth}{data.get('host', '')}:{data.get('port', '')}"


def proxy_identity(config: dict[str, Any] | None) -> tuple[Any, ...]:
    data = normalize_proxy_config(config or {})
    if not data.get("enabled"):
        return (False,)
    return (
        True,
        data.get("proxy_type", DEFAULT_PROXY_TYPE),
        data.get("host", ""),
        int(data.get("port", 0) or 0),
        data.get("username", ""),
        data.get("password", ""),
    )


def proxy_to_telethon(config: dict[str, Any] | None):
    data = normalize_proxy_config(config or {}, strict=True)
    if not data.get("enabled"):
        return None

    try:
        import socks  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "当前环境缺少 PySocks，无法使用账号组代理。请先执行：pip install pysocks"
        ) from exc

    proxy_type = _normalize_proxy_type(data.get("proxy_type"))
    socks_type = socks.SOCKS5 if proxy_type == "socks5" else socks.HTTP
    username = str(data.get("username", "") or "").strip() or None
    password = str(data.get("password", "") or "") or None
    return (
        socks_type,
        str(data.get("host", "") or "").strip(),
        int(data.get("port", 0) or 0),
        True,
        username,
        password,
    )


def config_base_from_sessions_dir(sessions_dir: str | Path | None) -> Path:
    text = str(sessions_dir or "").strip()
    if text:
        return Path(text).expanduser().parent
    return Path.cwd()
