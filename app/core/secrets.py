from __future__ import annotations

import base64
import ctypes
import os
from ctypes import wintypes
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class SecretStoreError(RuntimeError):
    pass


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_char]]:
    buffer = ctypes.create_string_buffer(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


class SecretStore:
    """Encrypts sensitive values with Windows DPAPI or a local Fernet key fallback."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._fernet: Fernet | None = None

    def encrypt(self, value: str) -> str:
        data = value.encode("utf-8")
        if os.name == "nt":
            try:
                return "dpapi:" + base64.urlsafe_b64encode(self._dpapi_protect(data)).decode("ascii")
            except Exception as exc:
                raise SecretStoreError(f"DPAPI encryption failed: {exc}") from exc
        return "fernet:" + self._get_fernet().encrypt(data).decode("ascii")

    def decrypt(self, token: str | None) -> str:
        if not token:
            return ""
        try:
            if token.startswith("dpapi:"):
                raw = base64.urlsafe_b64decode(token[6:].encode("ascii"))
                return self._dpapi_unprotect(raw).decode("utf-8")
            if token.startswith("fernet:"):
                return self._get_fernet().decrypt(token[7:].encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError, OSError) as exc:
            raise SecretStoreError("Unable to decrypt stored secret") from exc
        raise SecretStoreError("Unsupported secret token format")

    def _get_fernet(self) -> Fernet:
        if self._fernet is not None:
            return self._fernet
        key_path = self.directory / "local.key"
        if key_path.exists():
            key = key_path.read_bytes().strip()
        else:
            key = Fernet.generate_key()
            key_path.write_bytes(key)
            try:
                os.chmod(key_path, 0o600)
            except OSError:
                pass
        self._fernet = Fernet(key)
        return self._fernet

    @staticmethod
    def _dpapi_protect(data: bytes) -> bytes:
        in_blob, in_buf = _blob(data)
        out_blob = _DataBlob()
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        if not crypt32.CryptProtectData(
            ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
        ):
            raise ctypes.WinError()
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            kernel32.LocalFree(out_blob.pbData)
            del in_buf

    @staticmethod
    def _dpapi_unprotect(data: bytes) -> bytes:
        in_blob, in_buf = _blob(data)
        out_blob = _DataBlob()
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        if not crypt32.CryptUnprotectData(
            ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
        ):
            raise ctypes.WinError()
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            kernel32.LocalFree(out_blob.pbData)
            del in_buf
