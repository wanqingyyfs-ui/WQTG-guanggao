from __future__ import annotations

import json, re, time
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable
from automation_atomic_io import atomic_write_text


def _target(category, description, *strategies, timeout=10000):
    return {"category": category, "description": description, "timeout_ms": timeout, "strategies": list(strategies)}

def _role(role, regex): return {"type":"role","role":role,"name_regex":regex,"enabled":True}
def _css(value): return {"type":"css","value":value,"enabled":True}
def _text(regex): return {"type":"text","value_regex":regex,"enabled":True}
def _xy(x,y): return {"type":"relative_coordinate","x_ratio":x,"y_ratio":y,"enabled":False}

DEFAULT_CONFIG = {
 "schema_version":1,
 "viewport":{"width":1200,"height":900,"device_scale_factor":1.0,"browser_zoom":1.0},
 "targets":{
  "telegram.login.use_phone":_target("Telegram 登录","使用手机号登录",_role("button","phone|手机号|telephone"),_text("log in by phone|使用手机号登录|手机号登录"),_css("button.btn-primary"),_xy(.5,.72),timeout=8000),
  "telegram.login.next":_target("Telegram 登录","手机号输入后的下一步",_role("button","next|continue|继续|下一步"),_text("^next$|^continue$|^下一步$|^继续$"),_css("button.btn-primary"),_xy(.5,.76)),
  "telegram.login.phone_confirm":_target("Telegram 登录","确认手机号弹窗",_role("button","yes|ok|confirm|是|确定|确认"),_css(".popup button.btn-primary,.modal button.btn-primary"),_xy(.64,.61),timeout=5000),
  "telegram.main.menu":_target("Telegram 主界面","左上角主菜单",_role("button","menu|菜单"),_css("button.btn-menu,.sidebar-header button.btn-icon,button[aria-label*='menu' i]"),_xy(.025,.038),timeout=8000),
  "telegram.settings.open":_target("账号资料","打开设置",_role("menuitem","settings|设置"),_text("^settings$|^设置$"),_css("[data-menu-id='settings'],.btn-menu-item"),_xy(.12,.36),timeout=8000),
  "telegram.profile.edit":_target("账号资料","右上角编辑资料按钮",_role("button","edit|编辑"),_css("button.btn-icon.rp,button[aria-label*='edit' i]"),_xy(.965,.06)),
  "telegram.profile.avatar":_target("账号资料","头像上传区域",_css(".avatar.avatar-120,.avatar-120,input[type='file'][accept*='image']"),_role("button","photo|avatar|头像|照片"),_xy(.5,.2)),
  "telegram.photo.editor_save":_target("账号资料","头像裁剪确认",_role("button","done|save|apply|完成|保存|确定"),_css(".media-editor__finish-button,.media-editor button.btn-primary"),_xy(.9517,.9356),timeout=15000),
  "telegram.profile.save":_target("账号资料","资料保存按钮",_role("button","save|done|保存|完成"),_css("button.btn-circle.btn-corner.rp.is-visible,button.btn-primary"),_xy(.9517,.9356),timeout=15000),
  "telegram.folder.add":_target("分组文件夹","添加或加入文件夹",_role("button","add folder|add|join|apply|save|done|ok|添加文件夹|添加|加入|保存|完成|确定"),_css(".popup button.btn-primary,.modal button.btn-primary,button.btn-primary"),_xy(.5,.84),timeout=30000),
  "mytelegram.api_tools":_target("my.telegram.org","API Development Tools",_role("link","api development tools"),_text("api development tools"),_css("a[href*='apps']"),_xy(.5,.46),timeout=12000),
  "mytelegram.app.create":_target("my.telegram.org","创建应用按钮",_role("button","create application|create app|save|创建|保存"),_css("button.btn-primary,input[type='submit']"),_xy(.5,.86),timeout=12000),
 }
}

class LocatorConfigStore:
    def __init__(self, path): self.config_path=Path(path).expanduser().resolve()
    def load(self):
        data=deepcopy(DEFAULT_CONFIG)
        if self.config_path.exists():
            try:
                raw=json.loads(self.config_path.read_text(encoding="utf-8"))
                if isinstance(raw,dict): data=self._merge(data,raw)
            except Exception: pass
        data=self.validate(data)
        if not self.config_path.exists(): self.save(data)
        return data
    def save(self,data):
        data=self.validate(data); atomic_write_text(self.config_path,json.dumps(data,ensure_ascii=False,indent=2)+"\n"); return data
    def save_target(self,target_id,target):
        data=self.load()
        if target_id not in data["targets"]: raise KeyError(f"未知定位目标：{target_id}")
        data["targets"][target_id]=deepcopy(target); return self.save(data)
    def reset_target(self,target_id):
        if target_id not in DEFAULT_CONFIG["targets"]: raise KeyError(f"未知定位目标：{target_id}")
        data=self.load(); data["targets"][target_id]=deepcopy(DEFAULT_CONFIG["targets"][target_id]); return self.save(data)
    def validate(self,data):
        if not isinstance(data,dict) or not isinstance(data.get("targets"),dict): raise ValueError("定位配置缺少 targets")
        out=deepcopy(data); out["schema_version"]=int(out.get("schema_version") or 1)
        vp=out.get("viewport") if isinstance(out.get("viewport"),dict) else {}; vp["width"]=max(320,int(vp.get("width") or 1200)); vp["height"]=max(240,int(vp.get("height") or 900)); out["viewport"]=vp
        for tid,t in out["targets"].items():
            if not isinstance(t,dict): raise ValueError(f"定位目标必须是对象：{tid}")
            t["description"]=str(t.get("description") or tid); t["category"]=str(t.get("category") or "其他"); t["timeout_ms"]=max(250,min(120000,int(t.get("timeout_ms") or 8000)))
            if not isinstance(t.get("strategies"),list) or not t["strategies"]: raise ValueError(f"定位目标没有 strategies：{tid}")
            for s in t["strategies"]:
                if not isinstance(s,dict) or s.get("type") not in {"role","css","text","xpath","icon_text","relative_coordinate"}: raise ValueError(f"不支持的定位策略：{tid}/{s}")
                s["enabled"]=bool(s.get("enabled",True))
                if s["type"]=="relative_coordinate" and not (0<=float(s.get("x_ratio",0))<=1 and 0<=float(s.get("y_ratio",0))<=1): raise ValueError(f"相对坐标必须在 0~1：{tid}")
        return out
    @staticmethod
    def _merge(a,b):
        out=deepcopy(a)
        for k,v in b.items(): out[k]=LocatorConfigStore._merge(out[k],v) if isinstance(v,dict) and isinstance(out.get(k),dict) else deepcopy(v)
        return out

class LocatorEngine:
    def __init__(self,config_path,diagnostics_dir,log_func:Callable[[str],None]|None=None):
        self.store=LocatorConfigStore(config_path); self.diagnostics_dir=Path(diagnostics_dir).resolve(); self.log=log_func or (lambda m:None)
    def click(self,page,target_id,verify=None,diagnose_on_failure=True):
        target=self._target(target_id); attempts=[]
        for s in target["strategies"]:
            if not s.get("enabled",True): continue
            try:
                if s["type"]=="relative_coordinate":
                    vp=getattr(page,"viewport_size",None) or self.store.load()["viewport"]; page.mouse.click(float(vp["width"])*float(s.get("x_ratio",0)),float(vp["height"])*float(s.get("y_ratio",0)))
                else:
                    item=self._first_visible(self._locator(page,s),target["timeout_ms"])
                    if item is None: attempts.append({"strategy":s,"result":"not_visible"}); continue
                    try: item.scroll_into_view_if_needed(timeout=3000)
                    except Exception: pass
                    item.click(timeout=target["timeout_ms"])
                page.wait_for_timeout(250)
                if verify and not verify(): attempts.append({"strategy":s,"result":"verification_failed"}); continue
                self.log(f"定位点击成功：{target_id} -> {s['type']}"); return True
            except Exception as exc: attempts.append({"strategy":s,"result":"error","error":str(exc)})
        if diagnose_on_failure: self.dump_diagnostics(page,target_id,attempts)
        return False
    def resolve(self,page,target_id):
        t=self._target(target_id)
        for s in t["strategies"]:
            if s.get("enabled",True) and s["type"]!="relative_coordinate":
                item=self._first_visible(self._locator(page,s),t["timeout_ms"])
                if item is not None:return item
        return None
    def dump_diagnostics(self,page,target_id,attempts=None):
        out=self.diagnostics_dir/f"{time.strftime('%Y%m%d_%H%M%S')}_{re.sub(r'[^A-Za-z0-9_.-]+','_',target_id)}"; out.mkdir(parents=True,exist_ok=True)
        try: page.screenshot(path=str(out/"screenshot.png"),full_page=True)
        except Exception: pass
        try: (out/"page.html").write_text(page.content(),encoding="utf-8")
        except Exception: pass
        atomic_write_text(out/"runtime.json",json.dumps({"target_id":target_id,"url":str(getattr(page,"url","") or ""),"attempts":attempts or [],"config":self._target(target_id)},ensure_ascii=False,indent=2)+"\n"); self.log(f"定位失败诊断已保存：{out}"); return out
    def _target(self,tid):
        t=self.store.load()["targets"].get(tid)
        if not isinstance(t,dict): raise KeyError(f"未知定位目标：{tid}")
        return t
    def _locator(self,page,s):
        typ=s["type"]
        if typ=="role": return page.get_by_role(str(s.get("role") or "button"),name=re.compile(str(s.get("name_regex") or ".+"),re.I))
        if typ=="css": return page.locator(str(s.get("value") or ""))
        if typ=="xpath": return page.locator("xpath="+str(s.get("value") or ""))
        return page.get_by_text(re.compile(str(s.get("value_regex") or s.get("value") or ".+"),re.I))
    @staticmethod
    def _first_visible(locator,timeout):
        try: count=locator.count()
        except Exception: count=1
        for i in range(max(1,count)):
            item=locator.nth(i) if count>1 else locator
            try:
                if item.is_visible(timeout=min(timeout,1200)): return item
            except Exception: pass
        return None

def build_selector_for_element(p):
    if str(p.get("id") or "").strip(): return "#"+_esc(str(p["id"]))
    tag=str(p.get("tag") or "*").lower(); attrs=p.get("attrs") if isinstance(p.get("attrs"),dict) else {}
    for k in ("data-testid","aria-label","title","name"):
        v=str(attrs.get(k) or "").strip()
        if v:return f"{tag}[{k}='{v.replace(chr(39),chr(92)+chr(39))}']"
    c=[x for x in str(p.get("className") or "").split() if x and not x.startswith("is-")]
    return tag+"".join("."+_esc(x) for x in c[:4]) if c else tag

def calibration_init_script(target_id):
    tid=json.dumps(str(target_id))
    return """(()=>{if(window.__wqtgLocatorInstalled)return;window.__wqtgLocatorInstalled=true;document.addEventListener('click',async e=>{if(!(e.ctrlKey&&e.shiftKey))return;e.preventDefault();e.stopPropagation();const el=e.target instanceof Element?e.target.closest('button,a,input,[role],div'):null;if(!el)return;const r=el.getBoundingClientRect(),attrs={};for(const n of ['aria-label','title','name','data-testid','placeholder','role']){const v=el.getAttribute(n);if(v)attrs[n]=v}const p={targetId:TID,tag:el.tagName.toLowerCase(),id:el.id||'',className:typeof el.className==='string'?el.className:'',text:(el.innerText||el.textContent||'').trim().slice(0,200),attrs,xRatio:(r.left+r.width/2)/Math.max(1,innerWidth),yRatio:(r.top+r.height/2)/Math.max(1,innerHeight),url:location.href};try{await window.wqtgSaveLocator(p)}catch(x){console.error(x)}el.style.outline='3px solid #ff3366'},true)})()""".replace("TID",tid)
def _esc(v): return re.sub(r"([^A-Za-z0-9_-])",lambda m:"\\"+m.group(1),v)
