from __future__ import annotations

import re

from app.core.models import (
    MatchOptions,
    RuleConfig,
    RULE_TYPE_KEYWORD,
)


class KeywordMatcher:
    def __init__(self, rules: list[RuleConfig], match_options: MatchOptions):
        self.rules = rules
        self.match_options = match_options

    def update(self, rules: list[RuleConfig], match_options: MatchOptions) -> None:
        self.rules = rules
        self.match_options = match_options

    def _normalize_text(self, text: str) -> str:
        value = text or ""
        if self.match_options.strip_text:
            value = value.strip()
        return value

    def _normalize_for_compare(self, text: str) -> str:
        value = self._normalize_text(text)
        if self.match_options.ignore_case:
            value = value.lower()
        return value

    def _match_contains(self, message_text: str, keywords: list[str]) -> bool:
        source = self._normalize_for_compare(message_text)
        for keyword in keywords:
            candidate = self._normalize_for_compare(keyword)
            if candidate and candidate in source:
                return True
        return False

    def _match_exact(self, message_text: str, keywords: list[str]) -> bool:
        source = self._normalize_for_compare(message_text)
        for keyword in keywords:
            candidate = self._normalize_for_compare(keyword)
            if source == candidate:
                return True
        return False

    def _match_regex(self, message_text: str, keywords: list[str]) -> bool:
        source = self._normalize_text(message_text)
        flags = re.IGNORECASE if self.match_options.ignore_case else 0
        for pattern in keywords:
            try:
                if re.search(pattern, source, flags=flags):
                    return True
            except re.error:
                continue
        return False

    def match_all_in_order(self, message_text: str) -> list[RuleConfig]:
        matched_rules: list[RuleConfig] = []

        for rule in self.rules:
            if not rule.enabled:
                continue
            if rule.rule_type != RULE_TYPE_KEYWORD:
                continue

            match_type = rule.match_type.strip().lower()

            if match_type == "contains":
                matched = self._match_contains(message_text, rule.keywords)
            elif match_type == "exact":
                matched = self._match_exact(message_text, rule.keywords)
            elif match_type == "regex":
                matched = self._match_regex(message_text, rule.keywords)
            else:
                matched = False

            if matched:
                matched_rules.append(rule)

        return matched_rules