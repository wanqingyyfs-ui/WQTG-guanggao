from __future__ import annotations

import json, os, time
from pathlib import Path
from typing import Any, Callable

PICKER_VERSION = "2026-07-14.4"
PICKER_PANEL_ID = "__wqtg_locator_panel"
MODE_STRATEGIES = LOCATOR_MODE_STRATEGIES = "strategies"
MODE_ABSOLUTE = LOCATOR_MODE_ABSOLUTE = "absolute_position"


def _mode(value): return MODE_ABSOLUTE if str(value or "").strip().lower() == MODE_ABSOLUTE else MODE_STRATEGIES


def _configured_mode(target_id):
    raw = os.environ.get("WQTG_LOCATOR_CONFIG", "").strip()
    path = Path(raw).expanduser().resolve() if raw else Path(__file__).resolve().parent.parent / "data" / "automation_locators.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8")); return _mode(((data.get("targets") or {}).get(str(target_id)) or {}).get("locator_mode"))
    except Exception: return MODE_STRATEGIES


def calibration_picker_script(target_id: str, initial_mode: str = MODE_STRATEGIES) -> str:
    values = {"__TARGET__": json.dumps(str(target_id), ensure_ascii=False), "__VERSION__": json.dumps(PICKER_VERSION), "__PANEL__": json.dumps(PICKER_PANEL_ID), "__MODE__": json.dumps(_mode(initial_mode))}
    script = r"""
(()=>{
 const TARGET=__TARGET__,VERSION=__VERSION__,PANEL_ID=__PANEL__,STRATEGIES='strategies',ABSOLUTE='absolute_position',ACTIONABLE="button,a,input,textarea,select,label,[role='button'],[role='menuitem'],[role='link'],[tabindex]";
 const old=window.__wqtgLocatorPicker;if(old&&typeof old.destroy==='function'){try{old.destroy()}catch(_){}}
 let mode=__MODE__,armed=false,saving=false,last=0,panel,status,selector,button,marker,observer;
 const stop=e=>{if(!e)return;if(e.cancelable)e.preventDefault();e.stopPropagation();if(e.stopImmediatePropagation)e.stopImmediatePropagation()};
 const inside=e=>(typeof e.composedPath==='function'?e.composedPath():[]).some(n=>n&&n.nodeType===1&&(n.id===PANEL_ID||(n.closest&&n.closest(`#${PANEL_ID}`))));
 const label=()=>mode===ABSOLUTE?'绝对位置':'Strategies';
 const render=(message='',ok=false,bad=false)=>{ensure();if(!panel)return;status.textContent=message||(armed?`${label()} 拾取已开启：现在点击目标位置；Esc 取消`:'校准已就绪：先选择模式，再点击“开始拾取”');panel.style.background=ok?'rgba(18,128,72,.97)':bad?'rgba(176,42,42,.97)':'rgba(20,20,24,.96)';selector.value=mode;button.textContent=armed?'取消拾取':'开始拾取';button.style.background=armed?'#ffb020':'#fff'};
 const setMode=v=>{mode=v===ABSOLUTE?ABSOLUTE:STRATEGIES;armed=false;render()};
 const setArmed=v=>{armed=!!v;render()};
 const ready=reason=>{const p={targetId:TARGET,url:location.href,version:VERSION,locatorMode:mode,reason:reason||'installed',frame:window===window.top?'top':'child'};if(typeof window.wqtgLocatorReady==='function')Promise.resolve(window.wqtgLocatorReady(p)).catch(console.warn);return p};
 function ensure(){
  if(panel&&panel.isConnected)return panel;const parent=document.body||document.documentElement;if(!parent)return null;const stale=document.getElementById(PANEL_ID);if(stale)stale.remove();
  panel=document.createElement('div');panel.id=PANEL_ID;panel.dataset.wqtgLocatorUi='1';Object.assign(panel.style,{position:'fixed',top:'12px',left:'50%',transform:'translateX(-50%)',zIndex:'2147483647',display:'flex',alignItems:'center',gap:'9px',maxWidth:'calc(100vw - 24px)',padding:'9px 11px',borderRadius:'9px',background:'rgba(20,20,24,.96)',color:'#fff',font:'13px/1.4 sans-serif',boxShadow:'0 5px 22px rgba(0,0,0,.38)',pointerEvents:'auto',userSelect:'none'});
  status=document.createElement('span');Object.assign(status.style,{whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'});
  selector=document.createElement('select');selector.dataset.wqtgLocatorUi='1';Object.assign(selector.style,{border:'0',borderRadius:'7px',padding:'6px 8px',background:'#fff',color:'#111',fontWeight:'650',cursor:'pointer'});selector.innerHTML=`<option value="${STRATEGIES}">Strategies（元素特征）</option><option value="${ABSOLUTE}">绝对位置（像素坐标）</option>`;selector.value=mode;selector.addEventListener('change',e=>{e.stopPropagation();setMode(selector.value)},true);
  button=document.createElement('button');button.type='button';button.dataset.wqtgLocatorUi='1';Object.assign(button.style,{border:'0',borderRadius:'7px',padding:'6px 10px',cursor:'pointer',fontWeight:'700',whiteSpace:'nowrap',color:'#111'});button.addEventListener('pointerdown',stop,true);button.addEventListener('mousedown',stop,true);button.addEventListener('click',e=>{stop(e);setArmed(!armed)},true);
  panel.append(status,selector,button);parent.appendChild(panel);return panel
 }
 const element=e=>{const path=typeof e.composedPath==='function'?e.composedPath():[];for(const n of path){if(!n||n.nodeType!==1)continue;const x=n.matches&&n.matches(ACTIONABLE)?n:(n.closest?n.closest(ACTIONABLE):null);if(x&&!x.closest(`#${PANEL_ID}`))return x}const raw=e.target&&e.target.nodeType===1?e.target:null;return raw&&raw.closest?raw.closest(ACTIONABLE):null};
 const mark=(x,y,ok)=>{if(marker&&marker.isConnected)marker.remove();marker=document.createElement('div');marker.dataset.wqtgLocatorUi='1';Object.assign(marker.style,{position:'fixed',left:`${x}px`,top:`${y}px`,width:'18px',height:'18px',marginLeft:'-9px',marginTop:'-9px',border:`3px solid ${ok?'#ff3366':'#ffb020'}`,borderRadius:'50%',boxSizing:'border-box',zIndex:'2147483646',pointerEvents:'none',boxShadow:'0 0 0 2px rgba(255,255,255,.9)'});(document.body||document.documentElement).appendChild(marker)};
 const capture=async e=>{
  if(!(armed||(e.ctrlKey&&e.shiftKey))||inside(e))return;stop(e);const now=Date.now();if(saving||now-last<600)return;const el=element(e);if(mode===STRATEGIES&&!el){render('Strategies 模式未识别到可点击元素，请点击按钮本体后重试',false,true);return}
  saving=true;last=now;const x=Number(e.clientX||0),y=Number(e.clientY||0);if(mode===ABSOLUTE)mark(x,y,false);else el.style.setProperty('outline','3px dashed #ffb020','important');render(`正在保存 ${label()} 定位目标…`);
  const rect=el?el.getBoundingClientRect():null,attrs={};if(el)for(const name of ['aria-label','title','name','data-testid','placeholder','role']){const value=el.getAttribute(name);if(value)attrs[name]=value}
  const payload={targetId:TARGET,locatorMode:mode,tag:el?el.tagName.toLowerCase():'point',id:el?(el.id||''):'',className:el&&typeof el.className==='string'?el.className:'',text:el?(el.innerText||el.textContent||'').trim().slice(0,200):'',attrs,x,y,viewportWidth:Math.max(1,innerWidth),viewportHeight:Math.max(1,innerHeight),xRatio:rect?(rect.left+rect.width/2)/Math.max(1,innerWidth):x/Math.max(1,innerWidth),yRatio:rect?(rect.top+rect.height/2)/Math.max(1,innerHeight):y/Math.max(1,innerHeight),url:location.href};
  try{if(typeof window.wqtgSaveLocator!=='function')throw new Error('wqtgSaveLocator bridge is not available');await window.wqtgSaveLocator(payload);if(mode===ABSOLUTE)mark(x,y,true);else el.style.setProperty('outline','4px solid #ff3366','important');armed=false;render(`${label()} 定位目标已保存，可以关闭浏览器`,true,false)}catch(err){console.error('[WQTG locator save]',err);render(`保存失败：${String(err)}`,false,true)}finally{saving=false}
 };
 const keys=e=>{if(e.key==='F8'||e.code==='F8'){stop(e);setArmed(!armed)}else if(e.key==='Escape'&&armed){stop(e);setArmed(false)}};
 const names=['pointerdown','mousedown','click'];for(const n of names){window.addEventListener(n,capture,{capture:true,passive:false});document.addEventListener(n,capture,{capture:true,passive:false})}window.addEventListener('keydown',keys,true);document.addEventListener('keydown',keys,true);
 observer=new MutationObserver(()=>{if(!document.getElementById(PANEL_ID)){ensure();render()}});if(document.documentElement)observer.observe(document.documentElement,{childList:true,subtree:true});
 const api={version:VERSION,ensurePanel:ensure,reportReady:ready,setMode,arm:()=>setArmed(true),disarm:()=>setArmed(false),status:()=>({installed:true,armed,saving,locatorMode:mode,version:VERSION}),destroy:()=>{for(const n of names){window.removeEventListener(n,capture,true);document.removeEventListener(n,capture,true)}window.removeEventListener('keydown',keys,true);document.removeEventListener('keydown',keys,true);if(observer)observer.disconnect();if(panel&&panel.isConnected)panel.remove();if(marker&&marker.isConnected)marker.remove()}};
 window.__wqtgLocatorPicker=api;ensure();render();ready('installed');return{installed:true,reused:false,locatorMode:mode,version:VERSION}
})()
"""
    for key, value in values.items(): script = script.replace(key, value)
    return script


class CalibrationPickerInstaller:
    def __init__(self, target_id: str, save_locator: Callable[[dict[str, Any]], None], initial_mode: str | None = None, log_func: Callable[[str], None] | None = None):
        self.target_id = str(target_id); self.initial_mode = _configured_mode(self.target_id) if initial_mode is None else _mode(initial_mode); self.save_locator = save_locator; self.log = log_func or (lambda m: print(m, flush=True)); self.script = calibration_picker_script(self.target_id, self.initial_mode); self._registered_pages = set(); self._ready_keys = set(); self._save_bridge = lambda payload: self.save_locator(payload); self._ready_bridge = lambda payload=None: self._on_ready(payload)

    def configure_context(self, context):
        context.expose_function("wqtgSaveLocator", self._save_bridge); context.expose_function("wqtgLocatorReady", self._ready_bridge); context.add_init_script(self.script)
        if hasattr(context, "on"): context.on("page", self.register_page)
        for page in list(context.pages): self.register_page(page)

    def register_page(self, page):
        key = id(page)
        if key in self._registered_pages: return
        self._registered_pages.add(key)
        def install(*_args):
            try: self.ensure_page(page, quiet=True)
            except Exception as exc: self.log(f"定位拾取器页面注入重试失败：{exc}")
        if hasattr(page, "on"): page.on("domcontentloaded", install); page.on("load", install)

    def ensure_page(self, page, *, quiet=False, attempts=12):
        if not hasattr(page, "evaluate"): return True
        error = ""
        for _ in range(max(1, int(attempts))):
            try:
                if hasattr(page, "is_closed") and page.is_closed(): return False
                result = page.evaluate(self.script); ready = bool(page.evaluate("Boolean(window.__wqtgLocatorPicker && document.getElementById('__wqtg_locator_panel'))"))
                if ready:
                    if not quiet: self.log("定位拾取器已注入当前页面，可在顶部切换 Strategies/绝对位置。")
                    return True
                error = f"脚本返回但未检测到面板：{result!r}"
            except Exception as exc: error = str(exc)
            try: page.wait_for_timeout(250)
            except Exception: time.sleep(.25)
        if not quiet: self.log(f"定位拾取器注入失败：{error or 'unknown'}")
        return False

    def _on_ready(self, payload=None):
        data = dict(payload or {}); key = (str(data.get("url") or ""), str(data.get("frame") or ""))
        if key in self._ready_keys: return
        self._ready_keys.add(key); self.log("定位拾取器已就绪" + (f"：{key[0]}" if key[0] else "") + "。顶部可选择 Strategies 或绝对位置，再点击“开始拾取”。")
