from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol


class VerificationProvider(Protocol):
    def parse(self, html: str, text: str) -> "VerificationResult": ...


@dataclass(frozen=True)
class VerificationResult:
    code: str | None
    two_factor_password: str | None


class GenericHtmlProvider:
    CODE_PATTERNS = (
        re.compile(r"(?:code|验证码|verification)[^0-9]{0,20}([0-9]{5,8})", re.I),
        re.compile(r"\b([0-9]{5,8})\b"),
    )
    PASSWORD_PATTERNS = (
        re.compile(r"(?:2fa|password|密码)[^:\n]{0,20}[:：]\s*([^\s<]{4,128})", re.I),
    )

    def parse(self, html: str, text: str) -> VerificationResult:
        source = f"{text}\n{html}"
        code = None
        password = None
        for pattern in self.CODE_PATTERNS:
            match = pattern.search(source)
            if match:
                code = match.group(1)
                break
        for pattern in self.PASSWORD_PATTERNS:
            match = pattern.search(source)
            if match:
                password = match.group(1)
                break
        return VerificationResult(code=code, two_factor_password=password)


class JieMaHtmlProvider(GenericHtmlProvider):
    pass


def provider_for(url: str) -> VerificationProvider:
    lowered = url.lower()
    if "jie-ma" in lowered or "jiema" in lowered:
        return JieMaHtmlProvider()
    return GenericHtmlProvider()
