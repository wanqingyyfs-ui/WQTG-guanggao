from __future__ import annotations

from typing import Any


def wait_for_calibration_close(
    context: Any,
    preferred_page: Any | None = None,
    *,
    interval_ms: int = 250,
) -> None:
    """Keep Playwright's sync event loop moving until all calibration pages close.

    ``time.sleep`` does not dispatch callbacks initiated by browser-side
    ``expose_function`` calls. A Playwright wait call does, so use one while the
    visual calibration window remains open.
    """
    delay_ms = max(25, int(interval_ms))
    active_page = preferred_page

    while True:
        pages = list(context.pages)
        if not pages:
            return

        if active_page not in pages or _is_closed(active_page):
            active_page = next((page for page in pages if not _is_closed(page)), pages[0])

        try:
            active_page.wait_for_timeout(delay_ms)
        except KeyboardInterrupt:
            raise
        except Exception:
            # A page may close between the snapshot and the wait call. Re-read
            # the context on the next iteration and select another live page.
            active_page = None
            if not list(context.pages):
                return


def _is_closed(page: Any | None) -> bool:
    if page is None:
        return True
    try:
        return bool(page.is_closed()) if hasattr(page, "is_closed") else False
    except Exception:
        return True
