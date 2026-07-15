from __future__ import annotations

import json
import re
from typing import Any

def _extract_ip(text: str) -> str | None:
    try:
        payload = json.loads(text)
        raw = str(payload.get("ip") or payload.get("origin") or "")
    except json.JSONDecodeError:
        raw = text
    match = re.search(r"(?:\d{1,3}\.){3}\d{1,3}|[0-9a-fA-F:]{3,}", raw)
    return match.group(0) if match else None

def _runtime_snapshot(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """
        async () => {
          const canvas = document.createElement('canvas');
          canvas.width = 240; canvas.height = 60;
          const ctx = canvas.getContext('2d');
          ctx.textBaseline = 'top'; ctx.font = '16px Arial';
          ctx.fillText('WQTG runtime fingerprint', 4, 4);
          const gl = document.createElement('canvas').getContext('webgl');
          const dbg = gl && gl.getExtension('WEBGL_debug_renderer_info');
          let audio = null;
          try {
            const Offline = window.OfflineAudioContext || window.webkitOfflineAudioContext;
            if (Offline) {
              const ac = new Offline(1, 44100, 44100);
              const osc = ac.createOscillator();
              const comp = ac.createDynamicsCompressor();
              osc.connect(comp); comp.connect(ac.destination); osc.start(0);
              const rendered = await ac.startRendering();
              let sum = 0;
              const data = rendered.getChannelData(0);
              for (let i=0; i<Math.min(data.length, 5000); i+=100) sum += Math.abs(data[i]);
              audio = Number(sum.toFixed(8));
            }
          } catch (_) {}
          return {
            navigator: {
              userAgent: navigator.userAgent,
              platform: navigator.platform,
              language: navigator.language,
              languages: navigator.languages,
              hardwareConcurrency: navigator.hardwareConcurrency,
              deviceMemory: navigator.deviceMemory || null,
              maxTouchPoints: navigator.maxTouchPoints,
              cookieEnabled: navigator.cookieEnabled,
              webdriver: navigator.webdriver,
              vendor: navigator.vendor,
              productSub: navigator.productSub
            },
            screen: {
              width: screen.width, height: screen.height,
              availWidth: screen.availWidth, availHeight: screen.availHeight,
              colorDepth: screen.colorDepth, pixelDepth: screen.pixelDepth,
              devicePixelRatio: devicePixelRatio
            },
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
            locale: Intl.DateTimeFormat().resolvedOptions().locale,
            canvas: canvas.toDataURL(),
            webgl: gl ? {
              vendor: dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR),
              renderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER),
              version: gl.getParameter(gl.VERSION),
              shadingLanguageVersion: gl.getParameter(gl.SHADING_LANGUAGE_VERSION)
            } : null,
            audio,
            fonts: await (async () => {
              const candidates = ['Arial','Calibri','Cambria','Consolas','Courier New','Georgia','Segoe UI','Tahoma','Times New Roman','Verdana'];
              if (!document.fonts || !document.fonts.check) return [];
              return candidates.filter(font => document.fonts.check(`12px "${font}"`));
            })()
          };
        }
        """
    )

def _webrtc_safe(page: Any, expected_ip: str | None) -> bool:
    candidates = page.evaluate(
        """
        () => new Promise(resolve => {
          const found = [];
          const pc = new RTCPeerConnection({iceServers:[{urls:'stun:stun.l.google.com:19302'}]});
          pc.createDataChannel('x');
          pc.onicecandidate = ev => {
            if (!ev.candidate) { pc.close(); resolve(found); return; }
            found.push(ev.candidate.candidate);
          };
          pc.createOffer().then(o => pc.setLocalDescription(o));
          setTimeout(() => { try { pc.close(); } catch(e) {} resolve(found); }, 3500);
        })
        """
    )
    for candidate in candidates or []:
        lowered = candidate.lower()
        if " typ host " in lowered or " typ srflx " in lowered:
            if expected_ip and expected_ip in candidate:
                continue
            return False
    return True
