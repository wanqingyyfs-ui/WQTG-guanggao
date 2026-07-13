from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "app" / "vendor" / "tgapipldc" / "src"
sys.path.insert(0, str(SRC))

from automation_playwright_pump import wait_for_calibration_close


class FakePage:
    def __init__(self, context, *, close_after: int | None = None) -> None:
        self.context = context
        self.close_after = close_after
        self.wait_calls = 0
        self.closed = False

    def is_closed(self) -> bool:
        return self.closed

    def wait_for_timeout(self, delay_ms: int) -> None:
        self.wait_calls += 1
        if delay_ms < 25:
            raise AssertionError("delay must be clamped")
        if self.close_after is not None and self.wait_calls >= self.close_after:
            self.closed = True
            self.context.pages = [page for page in self.context.pages if page is not self]


class FakeContext:
    def __init__(self) -> None:
        self.pages = []


class PlaywrightPumpTests(unittest.TestCase):
    def test_wait_uses_playwright_calls_until_last_page_closes(self) -> None:
        context = FakeContext()
        page = FakePage(context, close_after=3)
        context.pages = [page]

        wait_for_calibration_close(context, page, interval_ms=10)

        self.assertEqual(page.wait_calls, 3)
        self.assertEqual(context.pages, [])

    def test_wait_switches_to_another_page_when_preferred_page_closes(self) -> None:
        context = FakeContext()
        first = FakePage(context, close_after=1)
        second = FakePage(context, close_after=2)
        context.pages = [first, second]

        wait_for_calibration_close(context, first, interval_ms=50)

        self.assertEqual(first.wait_calls, 1)
        self.assertEqual(second.wait_calls, 2)
        self.assertEqual(context.pages, [])


if __name__ == "__main__":
    unittest.main()
