from __future__ import annotations

import asyncio
import base64
import ipaddress
import socket
import ssl
import threading
from dataclasses import dataclass

from proxy_utils import ParsedProxy


class ProxyBridgeError(RuntimeError):
    pass


@dataclass
class PreparedPlaywrightProxy:
    proxy: dict[str, str]
    bridge: "AuthenticatedProxyBridge | None" = None

    def stop(self) -> None:
        if self.bridge is not None:
            self.bridge.stop()


class AuthenticatedProxyBridge:
    """Expose a local no-auth SOCKS5 endpoint backed by an authenticated proxy.

    Chromium cannot use username/password authentication with SOCKS5 directly.
    The bridge accepts only loopback clients and forwards every TCP stream via
    the configured upstream proxy. It never opens a direct destination socket.
    """

    def __init__(self, upstream: ParsedProxy) -> None:
        self.upstream = upstream
        self._loop: asyncio.AbstractEventLoop | None = None
        self._server: asyncio.AbstractServer | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._start_error: BaseException | None = None
        self._port = 0

    @property
    def playwright_proxy(self) -> dict[str, str]:
        if self._port <= 0:
            raise ProxyBridgeError("本地代理桥接器尚未启动")
        return {"server": f"socks5://127.0.0.1:{self._port}"}

    def start(self, timeout: float = 10.0) -> "AuthenticatedProxyBridge":
        if self._thread is not None and self._thread.is_alive():
            return self
        self._ready.clear()
        self._start_error = None
        self._thread = threading.Thread(
            target=self._thread_main,
            name="wqtg-auth-proxy-bridge",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(timeout):
            self.stop()
            raise ProxyBridgeError("启动本地代理桥接器超时")
        if self._start_error is not None:
            raise ProxyBridgeError(f"启动本地代理桥接器失败：{self._start_error}")
        if self._port <= 0:
            raise ProxyBridgeError("本地代理桥接器没有获得监听端口")
        return self

    def stop(self) -> None:
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        thread = self._thread
        if (
            thread is not None
            and thread.is_alive()
            and thread is not threading.current_thread()
        ):
            thread.join(timeout=3.0)
        self._thread = None
        self._loop = None
        self._server = None
        self._port = 0

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            server = loop.run_until_complete(
                asyncio.start_server(self._handle_client, "127.0.0.1", 0)
            )
            self._server = server
            sockets = list(server.sockets or [])
            if not sockets:
                raise ProxyBridgeError("本地代理桥接器没有监听套接字")
            self._port = int(sockets[0].getsockname()[1])
            self._ready.set()
            loop.run_forever()
        except BaseException as exc:
            self._start_error = exc
            self._ready.set()
        finally:
            server = self._server
            if server is not None:
                server.close()
                try:
                    loop.run_until_complete(server.wait_closed())
                except Exception:
                    pass
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                try:
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
                except Exception:
                    pass
            loop.close()

    async def _handle_client(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        upstream_writer: asyncio.StreamWriter | None = None
        try:
            version, method_count = await self._read_exact_pair(client_reader)
            if version != 5:
                raise ProxyBridgeError("本地桥接器只支持 SOCKS5")
            methods = await client_reader.readexactly(method_count)
            if 0 not in methods:
                client_writer.write(b"\x05\xff")
                await client_writer.drain()
                return
            client_writer.write(b"\x05\x00")
            await client_writer.drain()

            version, command, reserved, address_type = await self._read_request_header(
                client_reader
            )
            if version != 5 or reserved != 0:
                raise ProxyBridgeError("无效的 SOCKS5 请求")
            if command != 1:
                await self._send_socks_reply(client_writer, 7)
                return

            destination_host = await self._read_socks_address(
                client_reader,
                address_type,
            )
            destination_port = int.from_bytes(
                await client_reader.readexactly(2),
                "big",
            )
            upstream_reader, upstream_writer = await self._open_upstream_tunnel(
                destination_host,
                destination_port,
            )
            await self._send_socks_reply(client_writer, 0)
            await self._relay_bidirectional(
                client_reader,
                client_writer,
                upstream_reader,
                upstream_writer,
            )
        except (asyncio.IncompleteReadError, ConnectionError, OSError):
            pass
        except Exception:
            try:
                await self._send_socks_reply(client_writer, 1)
            except Exception:
                pass
        finally:
            if upstream_writer is not None:
                upstream_writer.close()
                try:
                    await upstream_writer.wait_closed()
                except Exception:
                    pass
            client_writer.close()
            try:
                await client_writer.wait_closed()
            except Exception:
                pass

    @staticmethod
    async def _read_exact_pair(reader: asyncio.StreamReader) -> tuple[int, int]:
        data = await reader.readexactly(2)
        return data[0], data[1]

    @staticmethod
    async def _read_request_header(
        reader: asyncio.StreamReader,
    ) -> tuple[int, int, int, int]:
        data = await reader.readexactly(4)
        return data[0], data[1], data[2], data[3]

    @staticmethod
    async def _read_socks_address(
        reader: asyncio.StreamReader,
        address_type: int,
    ) -> str:
        if address_type == 1:
            return socket.inet_ntop(socket.AF_INET, await reader.readexactly(4))
        if address_type == 4:
            return socket.inet_ntop(socket.AF_INET6, await reader.readexactly(16))
        if address_type == 3:
            length = (await reader.readexactly(1))[0]
            return (await reader.readexactly(length)).decode("idna")
        raise ProxyBridgeError(f"不支持的 SOCKS5 地址类型：{address_type}")

    @staticmethod
    def _encode_socks_address(host: str) -> bytes:
        try:
            parsed = ipaddress.ip_address(host)
        except ValueError:
            encoded = host.encode("idna")
            if len(encoded) > 255:
                raise ProxyBridgeError("目标域名过长")
            return b"\x03" + bytes([len(encoded)]) + encoded
        if parsed.version == 4:
            return b"\x01" + parsed.packed
        return b"\x04" + parsed.packed

    @staticmethod
    async def _send_socks_reply(
        writer: asyncio.StreamWriter,
        status: int,
    ) -> None:
        writer.write(bytes([5, status, 0, 1, 0, 0, 0, 0, 0, 0]))
        await writer.drain()

    async def _open_upstream_tunnel(
        self,
        destination_host: str,
        destination_port: int,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        scheme = str(self.upstream.scheme or "").lower()
        if scheme == "socks5":
            return await self._open_socks5_tunnel(
                destination_host,
                destination_port,
            )
        if scheme in {"http", "https"}:
            return await self._open_http_connect_tunnel(
                destination_host,
                destination_port,
                use_tls=scheme == "https",
            )
        raise ProxyBridgeError(f"不支持的上游代理协议：{scheme}")

    async def _open_socks5_tunnel(
        self,
        destination_host: str,
        destination_port: int,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        reader, writer = await asyncio.open_connection(
            self.upstream.host,
            self.upstream.port,
        )
        try:
            use_auth = bool(self.upstream.username or self.upstream.password)
            writer.write(b"\x05\x01" + (b"\x02" if use_auth else b"\x00"))
            await writer.drain()
            version, method = await self._read_exact_pair(reader)
            if version != 5 or method == 255:
                raise ProxyBridgeError("上游 SOCKS5 拒绝认证方式")
            if method == 2:
                username = self.upstream.username.encode("utf-8")
                password = self.upstream.password.encode("utf-8")
                if not 1 <= len(username) <= 255 or not 1 <= len(password) <= 255:
                    raise ProxyBridgeError("SOCKS5 代理账号或密码长度无效")
                writer.write(
                    b"\x01"
                    + bytes([len(username)])
                    + username
                    + bytes([len(password)])
                    + password
                )
                await writer.drain()
                auth_version, auth_status = await self._read_exact_pair(reader)
                if auth_version != 1 or auth_status != 0:
                    raise ProxyBridgeError("上游 SOCKS5 用户名或密码错误")
            elif method != 0:
                raise ProxyBridgeError(f"上游 SOCKS5 返回未知认证方式：{method}")

            writer.write(
                b"\x05\x01\x00"
                + self._encode_socks_address(destination_host)
                + int(destination_port).to_bytes(2, "big")
            )
            await writer.drain()
            version, status, reserved, address_type = await self._read_request_header(
                reader
            )
            if version != 5 or reserved != 0 or status != 0:
                raise ProxyBridgeError(
                    f"上游 SOCKS5 建立隧道失败，状态码：{status}"
                )
            await self._read_socks_address(reader, address_type)
            await reader.readexactly(2)
            return reader, writer
        except Exception:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            raise

    async def _open_http_connect_tunnel(
        self,
        destination_host: str,
        destination_port: int,
        *,
        use_tls: bool,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        ssl_context = ssl.create_default_context() if use_tls else None
        reader, writer = await asyncio.open_connection(
            self.upstream.host,
            self.upstream.port,
            ssl=ssl_context,
            server_hostname=self.upstream.host if use_tls else None,
        )
        try:
            display_host = (
                f"[{destination_host}]"
                if ":" in destination_host and not destination_host.startswith("[")
                else destination_host
            )
            target = f"{display_host}:{int(destination_port)}"
            headers = [
                f"CONNECT {target} HTTP/1.1",
                f"Host: {target}",
                "Proxy-Connection: Keep-Alive",
            ]
            if self.upstream.username:
                token = base64.b64encode(
                    f"{self.upstream.username}:{self.upstream.password}".encode("utf-8")
                ).decode("ascii")
                headers.append(f"Proxy-Authorization: Basic {token}")
            writer.write(("\r\n".join(headers) + "\r\n\r\n").encode("ascii"))
            await writer.drain()
            response = await reader.readuntil(b"\r\n\r\n")
            if len(response) > 65536:
                raise ProxyBridgeError("上游 HTTP 代理响应头过大")
            status_line = response.split(b"\r\n", 1)[0].decode(
                "latin-1",
                "replace",
            )
            parts = status_line.split(" ", 2)
            if len(parts) < 2 or parts[1] != "200":
                raise ProxyBridgeError(
                    f"上游 HTTP 代理 CONNECT 失败：{status_line}"
                )
            return reader, writer
        except Exception:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            raise

    @staticmethod
    async def _relay_bidirectional(
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        upstream_reader: asyncio.StreamReader,
        upstream_writer: asyncio.StreamWriter,
    ) -> None:
        async def pump(
            source: asyncio.StreamReader,
            destination: asyncio.StreamWriter,
        ) -> None:
            while True:
                data = await source.read(65536)
                if not data:
                    break
                destination.write(data)
                await destination.drain()

        tasks = {
            asyncio.create_task(pump(client_reader, upstream_writer)),
            asyncio.create_task(pump(upstream_reader, client_writer)),
        }
        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*done, *pending, return_exceptions=True)


def prepare_playwright_proxy(parsed_proxy: ParsedProxy) -> PreparedPlaywrightProxy:
    if (
        str(parsed_proxy.scheme or "").lower() == "socks5"
        and bool(parsed_proxy.username or parsed_proxy.password)
    ):
        bridge = AuthenticatedProxyBridge(parsed_proxy).start()
        return PreparedPlaywrightProxy(
            proxy=bridge.playwright_proxy,
            bridge=bridge,
        )
    return PreparedPlaywrightProxy(proxy=parsed_proxy.playwright_proxy)
