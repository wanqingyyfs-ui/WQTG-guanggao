from __future__ import annotations

import os
from pathlib import Path

import open_account_browser as module


def main() -> int:
    override = str(os.environ.get("WQTG_ACCOUNT_PROXY_MAP_OVERRIDE") or "").strip()
    if not override:
        raise RuntimeError("账号浏览器缺少静态代理运行表，禁止直连")
    map_path = Path(override).expanduser().resolve()
    if not map_path.exists():
        raise FileNotFoundError(f"静态代理运行表不存在：{map_path}")
    module.ACCOUNT_PROXY_MAP_FILE = map_path
    module.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
