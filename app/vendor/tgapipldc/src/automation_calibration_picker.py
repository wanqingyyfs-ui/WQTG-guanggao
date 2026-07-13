from __future__ import annotations

import json
import time
from typing import Any, Callable


PICKER_VERSION = "2026-07-14.3"
PICKER_PANEL_ID = "__wqtg_locator_panel"


def calibration_picker_script(target_id: str) -> str:
    """Return an idempotent in-page element picker with visible controls."""

    target_json = json.dumps(str(target_id), ensure_ascii=False)
    version_json = json.dumps(PICKER_VERSION)
    panel_json = json.dumps(PICKER_PANEL_ID)
    script = r"""
(() => {
  const TARGET_ID = __TARGET_ID__;
  const VERSION = __VERSION__;
  const PANEL_ID = __PANEL_ID__;
  const ACTIONABLE = "button,a,input,textarea,select,label,[role='button'],[role='menuitem'],[role='link'],[tabindex]";

  const previous = window.__wqtgLocatorPicker;
  if (previous && previous.version === VERSION) {
    previous.ensurePanel();
    previous.reportReady('reused');
    return {installed: true, reused: true, version: VERSION};
  }
  if (previous && typeof previous.destroy === 'function') {
    try { previous.destroy(); } catch (_) {}
  }

  let armed = false;
  let saving = false;
  let lastCaptureAt = 0;
  let panel = null;
  let statusNode = null;
  let armButton = null;
  let observer = null;

  const stopEvent = (event) => {
    if (!event) return;
    if (event.cancelable) event.preventDefault();
    event.stopPropagation();
    if (typeof event.stopImmediatePropagation === 'function') {
      event.stopImmediatePropagation();
    }
  };

  const isInsidePanel = (event) => {
    const path = typeof event.composedPath === 'function' ? event.composedPath() : [];
    return path.some((node) => node && node.nodeType === 1 && (
      node.id === PANEL_ID || (typeof node.closest === 'function' && node.closest(`#${PANEL_ID}`))
    ));
  };

  const render = (message = '', success = false, failure = false) => {
    ensurePanel();
    if (!panel || !statusNode || !armButton) return;
    statusNode.textContent = message || (
      armed
        ? '拾取已开启：现在点击目标按钮；Esc 取消'
        : '校准已就绪：点击“开始拾取”，再点击目标按钮'
    );
    panel.style.background = success
      ? 'rgba(18, 128, 72, .97)'
      : failure
        ? 'rgba(176, 42, 42, .97)'
        : 'rgba(20, 20, 24, .96)';
    armButton.textContent = armed ? '取消拾取' : '开始拾取';
    armButton.style.background = armed ? '#ffb020' : '#ffffff';
    armButton.style.color = '#111111';
  };

  const setArmed = (value) => {
    armed = Boolean(value);
    render();
  };

  const reportReady = (reason = 'installed') => {
    const payload = {
      targetId: TARGET_ID,
      url: location.href,
      version: VERSION,
      reason,
      frame: window === window.top ? 'top' : 'child'
    };
    if (typeof window.wqtgLocatorReady === 'function') {
      Promise.resolve(window.wqtgLocatorReady(payload)).catch((error) => {
        console.warn('[WQTG locator ready]', error);
      });
    }
    return payload;
  };

  function ensurePanel() {
    if (panel && panel.isConnected) return panel;
    const parent = document.body || document.documentElement;
    if (!parent) return null;

    const stale = document.getElementById(PANEL_ID);
    if (stale) stale.remove();

    panel = document.createElement('div');
    panel.id = PANEL_ID;
    panel.setAttribute('data-wqtg-locator-ui', '1');
    Object.assign(panel.style, {
      position: 'fixed',
      top: '12px',
      left: '50%',
      transform: 'translateX(-50%)',
      zIndex: '2147483647',
      display: 'flex',
      alignItems: 'center',
      gap: '10px',
      maxWidth: 'calc(100vw - 24px)',
      padding: '9px 11px',
      borderRadius: '9px',
      background: 'rgba(20, 20, 24, .96)',
      color: '#ffffff',
      font: '13px/1.4 -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif',
      boxShadow: '0 5px 22px rgba(0, 0, 0, .38)',
      pointerEvents: 'auto',
      userSelect: 'none'
    });

    statusNode = document.createElement('span');
    statusNode.style.whiteSpace = 'nowrap';
    statusNode.style.overflow = 'hidden';
    statusNode.style.textOverflow = 'ellipsis';

    armButton = document.createElement('button');
    armButton.type = 'button';
    armButton.setAttribute('data-wqtg-locator-ui', '1');
    Object.assign(armButton.style, {
      border: '0',
      borderRadius: '7px',
      padding: '6px 10px',
      cursor: 'pointer',
      fontWeight: '700',
      whiteSpace: 'nowrap'
    });

    const toggle = (event) => {
      stopEvent(event);
      setArmed(!armed);
    };
    armButton.addEventListener('pointerdown', stopEvent, true);
    armButton.addEventListener('mousedown', stopEvent, true);
    armButton.addEventListener('click', toggle, true);

    panel.append(statusNode, armButton);
    parent.appendChild(panel);
    return panel;
  }

  const elementFromEvent = (event) => {
    const path = typeof event.composedPath === 'function' ? event.composedPath() : [];
    for (const node of path) {
      if (!node || node.nodeType !== 1) continue;
      const element = node.matches && node.matches(ACTIONABLE)
        ? node
        : (typeof node.closest === 'function' ? node.closest(ACTIONABLE) : null);
      if (element && !element.closest(`#${PANEL_ID}`)) return element;
    }
    const raw = event.target && event.target.nodeType === 1 ? event.target : null;
    return raw && typeof raw.closest === 'function' ? raw.closest(ACTIONABLE) : null;
  };

  const capture = async (event) => {
    const requested = armed || (event.ctrlKey && event.shiftKey);
    if (!requested || isInsidePanel(event)) return;

    stopEvent(event);
    const now = Date.now();
    if (saving || now - lastCaptureAt < 600) return;

    const element = elementFromEvent(event);
    if (!element) {
      render('未识别到可点击元素，请点击按钮本体后重试', false, true);
      return;
    }

    saving = true;
    lastCaptureAt = now;
    element.style.setProperty('outline', '3px dashed #ffb020', 'important');
    render('正在保存定位目标…');

    const rect = element.getBoundingClientRect();
    const attrs = {};
    for (const name of ['aria-label', 'title', 'name', 'data-testid', 'placeholder', 'role']) {
      const value = element.getAttribute(name);
      if (value) attrs[name] = value;
    }
    const payload = {
      targetId: TARGET_ID,
      tag: element.tagName.toLowerCase(),
      id: element.id || '',
      className: typeof element.className === 'string' ? element.className : '',
      text: (element.innerText || element.textContent || '').trim().slice(0, 200),
      attrs,
      xRatio: (rect.left + rect.width / 2) / Math.max(1, innerWidth),
      yRatio: (rect.top + rect.height / 2) / Math.max(1, innerHeight),
      url: location.href
    };

    try {
      if (typeof window.wqtgSaveLocator !== 'function') {
        throw new Error('wqtgSaveLocator bridge is not available');
      }
      await window.wqtgSaveLocator(payload);
      element.style.setProperty('outline', '4px solid #ff3366', 'important');
      armed = false;
      render('定位目标已保存，可以关闭浏览器', true, false);
    } catch (error) {
      console.error('[WQTG locator save]', error);
      render(`保存失败：${String(error)}`, false, true);
    } finally {
      saving = false;
    }
  };

  const keyHandler = (event) => {
    if (event.key === 'F8' || event.code === 'F8') {
      stopEvent(event);
      setArmed(!armed);
    } else if (event.key === 'Escape' && armed) {
      stopEvent(event);
      setArmed(false);
    }
  };

  const eventNames = ['pointerdown', 'mousedown', 'click'];
  for (const name of eventNames) {
    window.addEventListener(name, capture, {capture: true, passive: false});
    document.addEventListener(name, capture, {capture: true, passive: false});
  }
  window.addEventListener('keydown', keyHandler, true);
  document.addEventListener('keydown', keyHandler, true);

  observer = new MutationObserver(() => {
    if (!document.getElementById(PANEL_ID)) {
      ensurePanel();
      render();
    }
  });
  if (document.documentElement) {
    observer.observe(document.documentElement, {childList: true, subtree: true});
  }

  const api = {
    version: VERSION,
    ensurePanel,
    reportReady,
    arm: () => setArmed(true),
    disarm: () => setArmed(false),
    status: () => ({installed: true, armed, saving, version: VERSION}),
    destroy: () => {
      for (const name of eventNames) {
        window.removeEventListener(name, capture, true);
        document.removeEventListener(name, capture, true);
      }
      window.removeEventListener('keydown', keyHandler, true);
      document.removeEventListener('keydown', keyHandler, true);
      if (observer) observer.disconnect();
      if (panel && panel.isConnected) panel.remove();
    }
  };
  window.__wqtgLocatorPicker = api;

  ensurePanel();
  render();
  reportReady('installed');
  return {installed: true, reused: false, version: VERSION};
})()
"""
    return (
        script.replace("__TARGET_ID__", target_json)
        .replace("__VERSION__", version_json)
        .replace("__PANEL_ID__", panel_json)
    )


class CalibrationPickerInstaller:
    """Install the picker for both restored persistent pages and future pages."""

    def __init__(
        self,
        target_id: str,
        save_locator: Callable[[dict[str, Any]], None],
        log_func: Callable[[str], None] | None = None,
    ) -> None:
        self.target_id = str(target_id)
        self.save_locator = save_locator
        self.log = log_func or (lambda message: print(message, flush=True))
        self.script = calibration_picker_script(self.target_id)
        self._registered_pages: set[int] = set()
        self._ready_keys: set[tuple[str, str]] = set()

    def configure_context(self, context) -> None:
        context.expose_function("wqtgSaveLocator", self.save_locator)
        context.expose_function("wqtgLocatorReady", self._on_ready)
        context.add_init_script(self.script)
        if hasattr(context, "on"):
            context.on("page", self.register_page)
        for page in list(context.pages):
            self.register_page(page)

    def register_page(self, page) -> None:
        page_key = id(page)
        if page_key in self._registered_pages:
            return
        self._registered_pages.add(page_key)

        def install_after_navigation(*_args) -> None:
            try:
                self.ensure_page(page, quiet=True)
            except Exception as exc:
                self.log(f"定位拾取器页面注入重试失败：{exc}")

        if hasattr(page, "on"):
            page.on("domcontentloaded", install_after_navigation)
            page.on("load", install_after_navigation)

    def ensure_page(self, page, *, quiet: bool = False, attempts: int = 12) -> bool:
        if not hasattr(page, "evaluate"):
            return True
        last_error = ""
        for _ in range(max(1, int(attempts))):
            try:
                if hasattr(page, "is_closed") and page.is_closed():
                    return False
                result = page.evaluate(self.script)
                ready = bool(page.evaluate(
                    "Boolean(window.__wqtgLocatorPicker && "
                    "document.getElementById('__wqtg_locator_panel'))"
                ))
                if ready:
                    if not quiet:
                        self.log("定位拾取器已注入当前页面，顶部应出现 WQTG 校准条。")
                    return True
                last_error = f"脚本返回但未检测到面板：{result!r}"
            except Exception as exc:
                last_error = str(exc)
            try:
                page.wait_for_timeout(250)
            except Exception:
                time.sleep(0.25)
        if not quiet:
            self.log(f"定位拾取器注入失败：{last_error or 'unknown'}")
        return False

    def _on_ready(self, payload: dict[str, Any] | None = None) -> None:
        data = dict(payload or {})
        url = str(data.get("url") or "")
        frame = str(data.get("frame") or "")
        key = (url, frame)
        if key in self._ready_keys:
            return
        self._ready_keys.add(key)
        self.log(
            "定位拾取器已就绪"
            + (f"：{url}" if url else "")
            + "。使用顶部“开始拾取”按钮最可靠，也可按 F8。"
        )
