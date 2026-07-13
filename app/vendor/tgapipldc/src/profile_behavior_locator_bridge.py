from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

LOCATOR_CLICK_TYPE = "locator.click"
LOCATOR_CLICK_LABEL = "点击自定义定位目标"
MANAGED_TARGET_PREFIX = "workflow."
MANAGED_BY = "profile_behavior_step"
ID_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")

BUILTIN_STEP_TARGETS = {
    "photo.crop_confirm": "telegram.photo.editor_save",
    "profile.save": "telegram.profile.save",
    "folder.add": "telegram.folder.add",
}


def normalize_id(value: str, label: str) -> str:
    clean = str(value or "").strip().lower()
    if not ID_RE.fullmatch(clean):
        raise ValueError(f"{label} ID 只能使用小写字母、数字、点、下划线和连字符，并且必须以字母开头：{value}")
    return clean


def managed_target_id(behavior_id: str, step_id: str) -> str:
    return f"{MANAGED_TARGET_PREFIX}{normalize_id(behavior_id, '行为')}.{normalize_id(step_id, '步骤')}"


def make_custom_click_step(behavior_id: str, step_id: str, name: str) -> dict[str, Any]:
    behavior_id = normalize_id(behavior_id, "行为")
    step_id = normalize_id(step_id, "步骤")
    clean_name = str(name or "").strip() or step_id
    return {
        "id": step_id,
        "name": clean_name,
        "type": LOCATOR_CLICK_TYPE,
        "enabled": True,
        "required": True,
        "retries": 1,
        "wait_after_ms": 800,
        "params": {"target_id": managed_target_id(behavior_id, step_id)},
    }


def locator_target_for_step(behavior_id: str, step: dict[str, Any] | None) -> str:
    item = dict(step or {})
    params = item.get("params") if isinstance(item.get("params"), dict) else {}
    explicit = str(params.get("target_id") or item.get("locator_target_id") or "").strip()
    if explicit:
        return explicit
    step_type = str(item.get("type") or "").strip()
    return BUILTIN_STEP_TARGETS.get(step_type, "")


def blank_managed_target(
    target_id: str,
    behavior_id: str,
    behavior_name: str,
    step_id: str,
    step_name: str,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    old = deepcopy(previous or {})
    strategies = old.get("strategies") if isinstance(old.get("strategies"), list) else []
    if not strategies:
        strategies = [{
            "type": "css",
            "value": f"[data-wqtg-unconfigured-target='{target_id}']",
            "enabled": True,
        }]
    absolute = old.get("absolute_position") if isinstance(old.get("absolute_position"), dict) else {
        "x": 0.0,
        "y": 0.0,
        "viewport_width": 1200,
        "viewport_height": 900,
        "captured": False,
    }
    return {
        "category": f"行为：{str(behavior_name or behavior_id)}",
        "description": str(step_name or step_id),
        "timeout_ms": int(old.get("timeout_ms") or 15000),
        "locator_mode": str(old.get("locator_mode") or "strategies"),
        "absolute_position": absolute,
        "strategies": strategies,
        "managed_by": MANAGED_BY,
        "behavior_id": str(behavior_id),
        "step_id": str(step_id),
    }


def ensure_locator_click_support() -> None:
    import profile_behavior_workflow as workflow

    workflow.STEP_TYPES.setdefault(LOCATOR_CLICK_TYPE, LOCATOR_CLICK_LABEL)
    workflow.STEP_TYPE_LABELS = workflow.STEP_TYPES

    original = workflow.execute_step
    if getattr(original, "_wqtg_locator_click_support", False):
        return

    def execute_step(module, page, item, state, config, stack):
        if str(item.get("type") or "") == LOCATOR_CLICK_TYPE:
            behavior_id = str(stack[-1] if stack else "custom")
            target_id = locator_target_for_step(behavior_id, item)
            if not target_id:
                raise RuntimeError(f"自定义点击步骤缺少定位目标：{behavior_id}.{item.get('id')}")
            if not workflow.locator_click(module, page, target_id):
                raise RuntimeError(f"未能点击定位目标：{target_id}")
            return "success"
        return original(module, page, item, state, config, stack)

    execute_step._wqtg_locator_click_support = True
    workflow.execute_step = execute_step
