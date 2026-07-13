from __future__ import annotations

import json, re, time
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable
from automation_atomic_io import atomic_write_text

MODE_STRATEGIES = LOCATOR_MODE_STRATEGIES = "strategies"
MODE_ABSOLUTE = LOCATOR_MODE_ABSOLUTE = "absolute_position"
SUPPORTED_LOCATOR_MODES = {MODE_STRATEGIES, MODE_ABSOLUTE}


class CalibrationSelector(str):
    def __new__(cls, value: str, payload: dict[str, Any]):
        obj = str.__new__(cls, value)
        obj.calibration_payload = deepcopy(payload)
        return obj


def _abs():
    return {"x": 0.0, "y": 0.0, "viewport_width": 1200, "viewport_height": 900, "captured": False}


def _target(category, description, *strategies, timeout=10000):
    return {"category": category, "description": description, "timeout_ms": timeout, "locator_mode": MODE_STRATEGIES, "absolute_position": _abs(), "strategies": list(strategies)}


def _role(role, regex): return {"type": "role", "role": role, "name_regex": regex, "enabled": True}
def _css(value): return {"type": "css", "value": value, "enabled": True}
def _text(regex): return {"type": "text", "value_regex": regex, "enabled": True}
def _xy(x, y): return {"type": "relative_coordinate", "x_ratio": x, "y_ratio": y, "enabled": False}


DEFAULT_CONFIG = {
    "schema_version": 2,
    "viewport": {"width": 1200, "height": 900, "device_scale_factor": 1.0, "browser_zoom": 1.0},
    "targets": {
        "telegram.login.use_phone": _target("Telegram 登录", "使用手机号登录", _role("button", "phone|手机号|telephone"), _text("log in by phone|使用手机号登录|手机号登录"), _css("button.btn-primary"), _xy(.5, .72), timeout=8000),
        "telegram.login.next": _target("Telegram 登录", "手机号输入后的下一步", _role("button", "next|continue|继续|下一步"), _text("^next$|^continue$|^下一步$|^继续$"), _css("button.btn-primary"), _xy(.5, .76)),
        "telegram.login.phone_confirm": _target("Telegram 登录", "确认手机号弹窗", _role("button", "yes|ok|confirm|是|确定|确认"), _css(".popup button.btn-primary,.modal button.btn-primary"), _xy(.64, .61), timeout=5000),
        "telegram.main.menu": _target("Telegram 主界面", "左上角主菜单", _role("button", "menu|菜单"), _css("button.btn-menu,.sidebar-header button.btn-icon,button[aria-label*='menu' i]"), _xy(.025, .038), timeout=8000),
        "telegram.settings.open": _target("账号资料", "打开设置", _role("menuitem", "settings|设置"), _text("^settings$|^设置$"), _css("[data-menu-id='settings'],.btn-menu-item"), _xy(.12, .36), timeout=8000),
        "telegram.profile.edit": _target("账号资料", "右上角编辑资料按钮", _role("button", "edit|编辑"), _css("button.btn-icon.rp,button[aria-label*='edit' i]"), _xy(.965, .06)),
        "telegram.profile.avatar": _target("账号资料", "头像上传区域", _css(".avatar.avatar-120,.avatar-120,input[type='file'][accept*='image']"), _role("button", "photo|avatar|头像|照片"), _xy(.5, .2)),
        "telegram.photo.editor_save": _target("账号资料", "头像裁剪确认", _role("button", "done|save|apply|完成|保存|确定"), _css(".media-editor__finish-button,.media-editor button.btn-primary"), _xy(.9517, .9356), timeout=15000),
        "telegram.profile.save": _target("账号资料", "资料保存按钮", _role("button", "save|done|保存|完成"), _css("button.btn-circle.btn-corner.rp.is-visible,button.btn-primary"), _xy(.9517, .9356), timeout=15000),
        "telegram.folder.add": _target("分组文件夹", "添加或加入文件夹", _role("button", "add folder|add|join|apply|save|done|ok|添加文件夹|添加|加入|保存|完成|确定"), _css(".popup button.btn-primary,.modal button.btn-primary,button.btn-primary"), _xy(.5, .84), timeout=30000),
        "mytelegram.api_tools": _target("my.telegram.org", "API Development Tools", _role("link", "api development tools"), _text("api development tools"), _css("a[href*='apps']"), _xy(.5, .46), timeout=12000),
        "mytelegram.app.create": _target("my.telegram.org", "创建应用按钮", _role("button", "create application|create app|save|创建|保存"), _css("button.btn-primary,input[type='submit']"), _xy(.5, .86), timeout=12000),
    },
}


def normalize_locator_mode(value: object) -> str:
    mode = str(value or MODE_STRATEGIES).strip().lower()
    mode = {"strategy": MODE_STRATEGIES, "selector": MODE_STRATEGIES, "selectors": MODE_STRATEGIES, "absolute": MODE_ABSOLUTE, "position": MODE_ABSOLUTE, "coordinate": MODE_ABSOLUTE}.get(mode, mode)
    if mode not in SUPPORTED_LOCATOR_MODES: raise ValueError(f"不支持的定位模式：{value}")
    return mode


class LocatorConfigStore:
    def __init__(self, path): self.config_path = Path(path).expanduser().resolve()

    def load(self):
        data = deepcopy(DEFAULT_CONFIG)
        if self.config_path.exists():
            try:
                raw = json.loads(self.config_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict): data = self._merge(data, raw)
            except Exception: pass
        data = self.validate(data)
        if not self.config_path.exists(): self.save(data)
        return data

    def save(self, data):
        data = self.validate(data)
        atomic_write_text(self.config_path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        return data

    def save_target(self, target_id, target):
        data = self.load()
        if target_id not in data["targets"]: raise KeyError(f"未知定位目标：{target_id}")
        payload = _payload_from_target(target)
        data["targets"][target_id] = apply_calibration_payload(data["targets"][target_id], payload)[0] if payload else deepcopy(target)
        return self.save(data)

    def reset_target(self, target_id):
        if target_id not in DEFAULT_CONFIG["targets"]: raise KeyError(f"未知定位目标：{target_id}")
        data = self.load(); data["targets"][target_id] = deepcopy(DEFAULT_CONFIG["targets"][target_id]); return self.save(data)

    def validate(self, data):
        if not isinstance(data, dict) or not isinstance(data.get("targets"), dict): raise ValueError("定位配置缺少 targets")
        out = deepcopy(data); out["schema_version"] = max(2, int(out.get("schema_version") or 1))
        vp = out.get("viewport") if isinstance(out.get("viewport"), dict) else {}
        vp["width"] = max(320, int(vp.get("width") or 1200)); vp["height"] = max(240, int(vp.get("height") or 900)); out["viewport"] = vp
        for tid, target in out["targets"].items():
            if not isinstance(target, dict): raise ValueError(f"定位目标必须是对象：{tid}")
            target["description"] = str(target.get("description") or tid); target["category"] = str(target.get("category") or "其他")
            target["timeout_ms"] = max(250, min(120000, int(target.get("timeout_ms") or 8000)))
            target["locator_mode"] = normalize_locator_mode(target.get("locator_mode"))
            strategies = target.get("strategies")
            if not isinstance(strategies, list): raise ValueError(f"定位目标 strategies 必须是列表：{tid}")
            for s in strategies:
                if not isinstance(s, dict) or s.get("type") not in {"role", "css", "text", "xpath", "icon_text", "relative_coordinate"}: raise ValueError(f"不支持的定位策略：{tid}/{s}")
                s["enabled"] = bool(s.get("enabled", True))
                if s["type"] == "relative_coordinate" and not (0 <= float(s.get("x_ratio", 0)) <= 1 and 0 <= float(s.get("y_ratio", 0)) <= 1): raise ValueError(f"相对坐标必须在 0~1：{tid}")
            target["absolute_position"] = self._absolute(target.get("absolute_position"), vp, strategies)
            if target["locator_mode"] == MODE_STRATEGIES and not any(s.get("enabled", True) and s.get("type") != "relative_coordinate" for s in strategies): raise ValueError(f"Strategies 模式没有可用元素策略：{tid}")
        return out

    @staticmethod
    def _absolute(raw, vp, strategies):
        raw = raw if isinstance(raw, dict) else {}
        result = {"x": float(raw.get("x") or 0), "y": float(raw.get("y") or 0), "viewport_width": max(1, int(raw.get("viewport_width") or vp["width"])), "viewport_height": max(1, int(raw.get("viewport_height") or vp["height"])), "captured": bool(raw.get("captured", False))}
        if not result["captured"]:
            legacy = next((s for s in strategies if s.get("type") == "relative_coordinate" and s.get("enabled", False)), None)
            if legacy:
                result.update(x=round(float(legacy.get("x_ratio") or 0) * result["viewport_width"], 2), y=round(float(legacy.get("y_ratio") or 0) * result["viewport_height"], 2), captured=True)
        if result["x"] < 0 or result["y"] < 0: raise ValueError("绝对位置坐标不能为负数")
        return result

    @staticmethod
    def _merge(a, b):
        out = deepcopy(a)
        for k, v in b.items(): out[k] = LocatorConfigStore._merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else deepcopy(v)
        return out


class LocatorEngine:
    def __init__(self, config_path, diagnostics_dir, log_func: Callable[[str], None] | None = None):
        self.store = LocatorConfigStore(config_path); self.diagnostics_dir = Path(diagnostics_dir).resolve(); self.log = log_func or (lambda _m: None)

    def click(self, page, target_id, verify=None, diagnose_on_failure=True):
        target = self._target(target_id); mode = target["locator_mode"]; attempts = []
        if mode == MODE_ABSOLUTE:
            try:
                self._click_absolute(page, target_id, target); page.wait_for_timeout(250)
                if not verify or verify(): return True
                attempts.append({"mode": mode, "result": "verification_failed"})
            except Exception as exc: attempts.append({"mode": mode, "result": "error", "error": str(exc)})
        else:
            for s in target["strategies"]:
                if not s.get("enabled", True) or s.get("type") == "relative_coordinate": continue
                try:
                    item = self._first_visible(self._locator(page, s), target["timeout_ms"])
                    if item is None: attempts.append({"strategy": s, "result": "not_visible"}); continue
                    try: item.scroll_into_view_if_needed(timeout=3000)
                    except Exception: pass
                    item.click(timeout=target["timeout_ms"]); page.wait_for_timeout(250)
                    if verify and not verify(): attempts.append({"strategy": s, "result": "verification_failed"}); continue
                    self.log(f"定位点击成功：{target_id} -> strategies/{s['type']}"); return True
                except Exception as exc: attempts.append({"strategy": s, "result": "error", "error": str(exc)})
        if diagnose_on_failure: self.dump_diagnostics(page, target_id, attempts)
        return False

    def resolve(self, page, target_id):
        target = self._target(target_id)
        if target["locator_mode"] != MODE_STRATEGIES: return None
        for s in target["strategies"]:
            if s.get("enabled", True) and s.get("type") != "relative_coordinate":
                item = self._first_visible(self._locator(page, s), target["timeout_ms"])
                if item is not None: return item
        return None

    def _click_absolute(self, page, target_id, target):
        pos = target.get("absolute_position") or {}
        if not pos.get("captured"): raise ValueError(f"绝对位置尚未校准：{target_id}")
        x, y = float(pos.get("x") or 0), float(pos.get("y") or 0)
        vp = getattr(page, "viewport_size", None) or self.store.load()["viewport"]; width, height = float(vp.get("width") or 0), float(vp.get("height") or 0)
        if width > 0 and height > 0 and not (0 <= x < width and 0 <= y < height): raise ValueError(f"绝对位置超出当前视口：({x}, {y}) / ({width}, {height})")
        saved = (int(pos.get("viewport_width") or 0), int(pos.get("viewport_height") or 0))
        if saved[0] and saved[1] and (int(width or saved[0]), int(height or saved[1])) != saved: self.log(f"绝对位置视口与校准时不同：当前 {int(width)}x{int(height)}，校准 {saved[0]}x{saved[1]}；仍按原始像素点击")
        page.mouse.click(x, y); self.log(f"定位点击成功：{target_id} -> absolute_position ({x:.1f}, {y:.1f})")

    def dump_diagnostics(self, page, target_id, attempts=None):
        out = self.diagnostics_dir / f"{time.strftime('%Y%m%d_%H%M%S')}_{re.sub(r'[^A-Za-z0-9_.-]+', '_', target_id)}"; out.mkdir(parents=True, exist_ok=True)
        try: page.screenshot(path=str(out / "screenshot.png"), full_page=True)
        except Exception: pass
        try: (out / "page.html").write_text(page.content(), encoding="utf-8")
        except Exception: pass
        atomic_write_text(out / "runtime.json", json.dumps({"target_id": target_id, "url": str(getattr(page, "url", "") or ""), "attempts": attempts or [], "config": self._target(target_id)}, ensure_ascii=False, indent=2) + "\n")
        self.log(f"定位失败诊断已保存：{out}"); return out

    def _target(self, tid):
        target = self.store.load()["targets"].get(tid)
        if not isinstance(target, dict): raise KeyError(f"未知定位目标：{tid}")
        return target

    def _locator(self, page, s):
        typ = s["type"]
        if typ == "role": return page.get_by_role(str(s.get("role") or "button"), name=re.compile(str(s.get("name_regex") or ".+"), re.I))
        if typ == "css": return page.locator(str(s.get("value") or ""))
        if typ == "xpath": return page.locator("xpath=" + str(s.get("value") or ""))
        return page.get_by_text(re.compile(str(s.get("value_regex") or s.get("value") or ".+"), re.I))

    @staticmethod
    def _first_visible(locator, timeout):
        try: count = locator.count()
        except Exception: count = 1
        for i in range(max(1, count)):
            item = locator.nth(i) if count > 1 else locator
            try:
                if item.is_visible(timeout=min(timeout, 1200)): return item
            except Exception: pass
        return None


def _selector_text(p):
    if str(p.get("id") or "").strip(): return "#" + _esc(str(p["id"]))
    tag = str(p.get("tag") or "*").lower(); attrs = p.get("attrs") if isinstance(p.get("attrs"), dict) else {}
    for key in ("data-testid", "aria-label", "title", "name"):
        value = str(attrs.get(key) or "").strip()
        if value: return f"{tag}[{key}='{value.replace(chr(39), chr(92) + chr(39))}']"
    classes = [x for x in str(p.get("className") or "").split() if x and not x.startswith("is-")]
    return tag + "".join("." + _esc(x) for x in classes[:4]) if classes else tag


def build_selector_for_element(payload):
    selector = _selector_text(payload)
    return CalibrationSelector(selector, payload) if isinstance(payload, dict) and payload.get("locatorMode") else selector


def _payload_from_target(target):
    if not isinstance(target, dict): return None
    for s in target.get("strategies") or []:
        payload = getattr(s.get("value"), "calibration_payload", None) if isinstance(s, dict) else None
        if isinstance(payload, dict): return deepcopy(payload)
    return None


def apply_calibration_payload(target, payload):
    updated = deepcopy(target); mode = normalize_locator_mode(payload.get("locatorMode")); updated["locator_mode"] = mode
    if mode == MODE_ABSOLUTE:
        updated["absolute_position"] = {"x": round(float(payload.get("x") or 0), 2), "y": round(float(payload.get("y") or 0), 2), "viewport_width": max(1, int(payload.get("viewportWidth") or 1)), "viewport_height": max(1, int(payload.get("viewportHeight") or 1)), "captured": True}
        p = updated["absolute_position"]; return updated, f"absolute_position ({p['x']:.1f}, {p['y']:.1f}) @ {p['viewport_width']}x{p['viewport_height']}"
    selector = _selector_text(payload); strategies = [{"type": "css", "value": selector, "enabled": True}]
    text = str(payload.get("text") or "").strip()
    if text: strategies.append({"type": "text", "value_regex": re.escape(text[:100]), "enabled": True})
    updated["strategies"] = strategies; return updated, f"strategies/{selector}"


def calibration_init_script(target_id):
    from automation_calibration_picker import calibration_picker_script
    return calibration_picker_script(target_id, MODE_STRATEGIES)


def _esc(value): return re.sub(r"([^A-Za-z0-9_-])", lambda m: "\\" + m.group(1), value)
