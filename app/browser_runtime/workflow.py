from __future__ import annotations

import time
from pathlib import Path
from typing import Any

def _pick_element(page: Any, x: float, y: float) -> dict[str, Any]:
    return page.evaluate(
        """
        ({x,y}) => {
          const el = document.elementFromPoint(x,y);
          if (!el) return null;
          const cssPath = node => {
            if (node.id) return `#${CSS.escape(node.id)}`;
            const parts = [];
            while (node && node.nodeType === Node.ELEMENT_NODE && node !== document.body) {
              let part = node.tagName.toLowerCase();
              const classes = [...node.classList].slice(0,3).map(c => `.${CSS.escape(c)}`).join('');
              if (classes) part += classes;
              const parent = node.parentElement;
              if (parent) {
                const peers = [...parent.children].filter(c => c.tagName === node.tagName);
                if (peers.length > 1) part += `:nth-of-type(${peers.indexOf(node)+1})`;
              }
              parts.unshift(part);
              node = parent;
            }
            return parts.join(' > ');
          };
          const rect = el.getBoundingClientRect();
          return {
            tag: el.tagName.toLowerCase(),
            text: (el.innerText || el.textContent || '').trim().slice(0,500),
            role: el.getAttribute('role'),
            ariaLabel: el.getAttribute('aria-label'),
            placeholder: el.getAttribute('placeholder'),
            css: cssPath(el),
            bounds: {x:rect.x,y:rect.y,width:rect.width,height:rect.height}
          };
        }
        """,
        {"x": x, "y": y},
    ) or {}

def _strategy_locator(page: Any, strategies: list[dict[str, Any]], timeout_ms: int) -> Any:
    last_error: Exception | None = None
    for strategy in strategies:
        kind = str(strategy.get("type") or "").lower()
        value = strategy.get("value")
        try:
            if kind == "css":
                locator = page.locator(str(value)).first
            elif kind == "text":
                locator = page.get_by_text(str(value), exact=bool(strategy.get("exact", True))).first
            elif kind == "role":
                locator = page.get_by_role(
                    str(strategy.get("role") or "button"),
                    name=str(value) if value is not None else None,
                    exact=bool(strategy.get("exact", True)),
                ).first
            elif kind in {"coordinates", "coordinate"}:
                return {"x": float(strategy["x"]), "y": float(strategy["y"])}
            else:
                continue
            locator.wait_for(state="visible", timeout=timeout_ms)
            return locator
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"All locator strategies failed: {last_error}")

def _execute_workflow(page: Any, steps: list[dict[str, Any]], profile_dir: Path) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for index, step in enumerate(steps):
        step_key = str(step.get("step_key") or f"step-{index+1}")
        step_type = str(step.get("step_type") or "")
        payload = dict(step.get("payload") or {})
        action = str(payload.get("action") or "").lower()
        if not action:
            if step_type == "profile.avatar":
                action = "upload"
            elif step_type in {"profile.name", "profile.username", "profile.bio"}:
                action = "fill"
            elif step_type == "profile.folder":
                action = "click"
            else:
                action = step_type.split(".")[-1]
        timeout_ms = int(payload.get("timeout_ms") or 12000)
        try:
            if action == "navigate":
                page.goto(str(payload["url"]), wait_until="domcontentloaded", timeout=60000)
            elif action == "wait":
                page.wait_for_timeout(int(payload.get("milliseconds") or 1000))
            else:
                target = _strategy_locator(page, list(payload.get("strategies") or []), timeout_ms)
                if isinstance(target, dict):
                    page.mouse.click(target["x"], target["y"])
                elif action == "click":
                    target.click()
                elif action == "fill":
                    target.fill(str(payload.get("value") or ""))
                elif action == "type":
                    target.click()
                    page.keyboard.type(str(payload.get("value") or ""))
                elif action == "press":
                    target.press(str(payload.get("key") or "Enter"))
                elif action == "upload":
                    files = payload.get("files") or [payload.get("file")]
                    paths = [str(Path(item).resolve()) for item in files if item]
                    if not paths or any(not Path(item).is_file() for item in paths):
                        raise RuntimeError("Workflow upload file is missing")
                    target.set_input_files(paths)
                else:
                    raise RuntimeError(f"Unsupported workflow action: {action}")
            results.append({"step_key": step_key, "status": "success"})
        except Exception as exc:
            screenshot_dir = profile_dir / "screenshots"
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            screenshot = screenshot_dir / f"workflow-failed-{int(time.time())}-{index+1}.png"
            try:
                page.screenshot(path=str(screenshot), type="png")
            except Exception:
                screenshot = None
            results.append(
                {
                    "step_key": step_key,
                    "status": "failed",
                    "error": str(exc),
                    "screenshot": str(screenshot) if screenshot else None,
                }
            )
            if bool(payload.get("stop_on_error", True)):
                return {"status": "failed", "steps": results}
    return {"status": "success", "steps": results}
