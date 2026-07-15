from __future__ import annotations

import pytest

from app.services.environment_service import EnvironmentProfileError


def test_runtime_fingerprint_finalizes_once(services) -> None:
    account_id = services["accounts"].create("+16595590986", "https://example.test/code")
    snapshot = {"navigator": {"userAgent": "Chromium/140"}, "screen": {"width": 1920}}
    service = services["environments"]
    service.finalize_runtime_snapshot(
        account_id,
        snapshot,
        browser_version="140.0.0.0",
        user_agent="Chromium/140",
    )
    service.finalize_runtime_snapshot(
        account_id,
        snapshot,
        browser_version="140.0.0.0",
        user_agent="Chromium/140",
    )
    with pytest.raises(EnvironmentProfileError):
        service.finalize_runtime_snapshot(
            account_id,
            {"navigator": {"userAgent": "Chromium/141"}},
            browser_version="141.0.0.0",
            user_agent="Chromium/141",
        )


def test_regeneration_requires_all_safety_conditions(services) -> None:
    account_id = services["accounts"].create("+16595590986", "https://example.test/code")
    with pytest.raises(EnvironmentProfileError):
        services["environments"].regenerate(
            account_id,
            browser_stopped=True,
            no_active_tasks=True,
            profile_backup_exists=False,
        )
