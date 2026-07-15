from __future__ import annotations

import pytest

from app.services.group_service import GroupLinkError, normalize_group_link


def test_normalize_public_and_private_group_links() -> None:
    assert normalize_group_link("@example_group") == {
        "canonical_link": "https://t.me/example_group",
        "username": "example_group",
        "link_type": "public",
    }
    private = normalize_group_link("https://t.me/+AbCdEf123")
    assert private["link_type"] == "private_invite"
    assert private["username"] is None


def test_import_deduplicates_links(services) -> None:
    result = services["groups"].import_links(
        "https://t.me/example_group\n@EXAMPLE_GROUP\nhttps://t.me/+AbCdEf123"
    )
    assert len(result["created_ids"]) == 2
    assert result["duplicates"] == ["https://t.me/example_group"]
    result2 = services["groups"].import_links("https://t.me/example_group")
    assert result2["duplicates"] == ["https://t.me/example_group"]


def test_invalid_host_is_rejected() -> None:
    with pytest.raises(GroupLinkError):
        normalize_group_link("https://example.com/group")
