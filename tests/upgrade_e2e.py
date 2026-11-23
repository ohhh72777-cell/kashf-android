"""Upgrade test on a real Android emulator: install the old app, put realistic data in it,
install the new app OVER it (adb install -r, no uninstall) and check that nothing was lost.

Part A — debug builds (old = v1.0.7 app code, new = this build, same debug key): the data is entered
          through the running old app and every stored item is compared before/after.
Part B — the published v1.0.7 release APK, then this release APK on top: the signing key must be
          accepted (no uninstall) and data created in the old release must still be there.
"""
import json, os, re, subprocess, sys, time, urllib.request
import websocket

PKG = "com.tarekelborai.kashf"
OUT = sys.argv[1] if len(sys.argv) > 1 else "report"
R = []
def sh(c, t=180): r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t); return (r.stdout + r.stderr).strip()
def adb(c, t=180): return sh("adb " + c, t)
def ok(n, c, d=""):
    R.append({"name": n, "ok": bool(c), "detail": str(d)[:400]}); print(("PASS " if c else "FAIL ") + n + (" — " + str(d)[:200] if d else ""), flush=True)
def launch(): adb(f"shell am start -W -n {PKG}/.MainActivity"); time.sleep(3)

class Page:
    def __init__(self, timeout=60):
        t0 = time.time()
        while time.time() - t0 < timeout:
            pid = adb(f"shell pidof {PKG}").split()
            if pid and f"webview_devtools_remote_{pid[0]}" in adb("shell cat /proc/net/unix"):
                sh("adb forward --remove-all"); adb(f"forward tcp:9222 localabstract:webview_devtools_remote_{pid[0]}")
                try:
                    pg = [p for p in json.load(urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=5)) if p.get("type") == "page" and "localhost" in p.get("url", "")]
                    if pg:
                        self.ws = websocket.create_connection(pg[0]["webSocketDebuggerUrl"], timeout=60, suppress_origin=True); self.i = 0
                        if self.wait("!!window.__kashf&&window.__kashf.S.ready", 30): return
                except Exception: pass
            time.sleep(1)
        raise RuntimeError("cannot attach to the app")
    def ev(self, e):
        self.i += 1; self.ws.send(json.dumps({"id": self.i, "method": "Runtime.evaluate", "params": {"expression": e, "awaitPromise": True, "returnByValue": True}}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == self.i:
                r = m.get("result", {})
                if "exceptionDetails" in r: raise RuntimeError(json.dumps(r["exceptionDetails"])[:300])
                return r.get("result", {}).get("value")
    def wait(self, e, t=20):
        t0 = time.time()
        while time.time() - t0 < t:
            try:
                if self.ev(e): return True
            except Exception: pass
            time.sleep(.25)
        return False
    def click(self, sel): return self.ev(f"(()=>{{const e=document.querySelector({json.dumps(sel)});if(!e)return false;e.click();return true}})()")
    def pin(self, p):
        for d in p: self.click(f'.key[data-k="{d}"]'); time.sleep(.05)

STORE = "JSON.stringify(Object.fromEntries(Object.keys(localStorage).sort().map(k=>[k,localStorage.getItem(k)])))"
FILES = "(async()=>{const F=Capacitor.Plugins.Filesystem;const o={};for(const [dir,p] of [['DATA','kashf-store'],['DATA','auto-backups'],['DOCUMENTS','Kashf']]){try{o[dir+'/'+p]=(await F.readdir({path:p,directory:dir})).files.map(f=>f.name||f).sort()}catch(e){o[dir+'/'+p]=null}}return JSON.stringify(o)})()"

def part_a():
    data = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "upgrade-dataset.json"), encoding="utf-8"))
    adb(f"uninstall {PKG}"); out = adb("install out/kashf-old-debug.apk")
    ok("A: old app (v1.0.7 code) installed", "Success" in out, out[-80:])
    launch(); p = Page()
    ok("A: old app is v1.0.7", p.ev("Capacitor.Plugins.App.getInfo().then(i=>i.version)") == "1.0.7")
    p.ev(f"window.__kashf.importData({json.dumps({'app':'kashf','docs':data}, ensure_ascii=False)})"); time.sleep(2)
    p.click('[data-act="screen"][data-s="att"]'); time.sleep(.5)
    for i in (1, 3, 5): p.click(f"#agrid .card:nth-child({i})"); time.sleep(.5)
    ON = "[...document.querySelectorAll('#agrid .card')].filter(c=>c.classList.contains('on')).map(c=>c.dataset.id).sort().join(',')"
    on_before = p.ev(ON)
    p.click('[data-act="screen"][data-s="fin"]'); p.wait("!!document.querySelector('[data-act=pinsetup]')"); p.click('[data-act="pinsetup"]')
    p.wait("!!document.querySelector('.key')"); p.pin("2580"); time.sleep(.3); p.pin("2580")
    p.wait("!!document.querySelector('.sheet .code')", 30); p.click('.sheet [data-act="close"]')
    p.click('[data-act="addmonth"][data-n="نوفمبر"]'); time.sleep(.4); p.click('[data-act="gfee"]')
    for d in "200": p.click(f'.sheet .key[data-k="{d}"]')
    p.click('[data-act="amtsave"]'); time.sleep(.4)
    for i in range(1, 9): p.click(f".mrow:nth-child({i+1}) .pc"); time.sleep(.25)
    p.wait("document.querySelectorAll('.pc.paid').length===8")
    # compare the students x months rows (names, fees, every payment cell), not the whole screen:
    # the screen layout around the list may change between versions, the data must not
    FIN = "[...document.querySelectorAll('#fwrap .mrow:not(.mhead)')].map(r=>r.innerText.replace(/\\s+/g,' ').trim()).join('\\n')"
    fin_before = p.ev(FIN)
    p.click('[data-act="screen"][data-s="set"]'); time.sleep(.3); p.click('[data-act="size"][data-v="l"]'); p.click('[data-act="lockleave"]'); time.sleep(2)
    before = json.loads(p.ev(STORE)); files_before = json.loads(p.ev(FILES))
    ok("A: realistic data in the old app (6 groups, 199 students, PIN, payments)", len(json.loads(before["k2:l:core"])["students"]) == 199 and "k2:l:keys" in before and fin_before.count("٢٠٠") > 0)
    # ---- install the new version OVER the old one ----
    out = adb("install -r out/kashf-debug.apk")
    ok("A: new version installed over the old one (no uninstall)", "Success" in out, out[-80:])
    launch(); p = Page(); time.sleep(4)
    ok("A: running the new version", p.ev("Capacitor.Plugins.App.getInfo().then(i=>i.version)") != "1.0.7", p.ev("Capacitor.Plugins.App.getInfo().then(i=>i.version)"))
    after = json.loads(p.ev(STORE)); files_after = json.loads(p.ev(FILES))
    missing = [k for k in before if k not in after]; changed = [k for k in before if k in after and before[k] != after[k]]
    added = sorted(set(after) - set(before))
    ok("A: every stored item still there", not missing, missing)
    ok("A: no stored item changed by the update", not changed, changed)
    ok("A: only the safety records were added", set(added) <= {"k2:appver", "k2:autobk"}, added)
    ok("A: kill-safe copies of the data still on disk", set(files_before["DATA/kashf-store"]) <= set(files_after["DATA/kashf-store"] or []))
    ab = json.loads(after.get("k2:autobk", "{}"))
    ok("A: automatic copy made before the update was used", bool(ab.get("name")) and ab["name"] in (files_after["DATA/auto-backups"] or []) and ab["name"] in (files_after["DOCUMENTS/Kashf"] or []), ab)
    ok("A: copy is visible to the user in Documents/Kashf", ab.get("name", "?") in adb("shell ls /sdcard/Documents/Kashf/"))
    p.click('[data-act="screen"][data-s="att"]'); time.sleep(.5)
    ok("A: register shows the 43-group with today's marks exactly as left", p.wait("document.querySelectorAll('#agrid .card').length===42") and p.ev(ON) == on_before)
    p.click('[data-act="screen"][data-s="fin"]'); p.wait("!!document.querySelector('.key')"); p.pin("2580")
    ok("A: same PIN opens finance, payments and totals identical", p.wait("document.querySelectorAll('.pc.paid').length===8", 30) and p.ev(FIN) == fin_before)
    p.click('[data-act="screen"][data-s="set"]')
    ok("A: settings kept", p.ev("document.documentElement.dataset.size") == "l")
    adb("exec-out screencap -p > " + OUT + "/upgrade_after.png")

def shot(name):
    sh(f"adb exec-out screencap -p > {OUT}/{name}.png"); return f"{OUT}/{name}.png"
def diff(a, b):
    from PIL import Image, ImageChops, ImageStat
    x, y = Image.open(a).convert("L"), Image.open(b).convert("L")
    if x.size != y.size: y = y.resize(x.size)
    return sum(ImageStat.Stat(ImageChops.difference(x, y)).mean)
QUICK = '[data-act="quickgroup"][data-n="أولى ثانوي"]'
TAPXY = f"(()=>{{const e=document.querySelector({json.dumps(QUICK)});const b=e.getBoundingClientRect();return [Math.round((b.x+b.width/2)*devicePixelRatio),Math.round((b.y+b.height/2)*devicePixelRatio)]}})()"

def part_b():
    """Release builds cannot be inspected, so: tap position comes from the same old code in a debug
    build, and the screen after the update is compared with reference screens of the new code."""
    if not os.path.exists("out/kashf.apk"): ok("B: release APK present", False, "not signed in this run"); return
    # reference screens of the NEW code (debug build of the same code): empty app vs. app with one group
    adb(f"uninstall {PKG}"); adb("install out/kashf-debug.apk"); launch(); p = Page(); time.sleep(2)
    ref_empty = shot("ref_new_empty"); p.click(QUICK); time.sleep(1); p.click('[data-act="screen"][data-s="att"]'); time.sleep(2)
    adb(f"shell am force-stop {PKG}"); launch(); Page(); time.sleep(3); ref_group = shot("ref_new_one_group")
    # where the "أولى ثانوي" button is in the OLD code on this screen
    adb(f"uninstall {PKG}"); adb("install out/kashf-old-debug.apk"); launch(); p = Page(); time.sleep(2)
    x, y = p.ev(TAPXY)
    # the published v1.0.7 release, data made by tapping, then the new release installed on top
    adb(f"uninstall {PKG}"); out = adb("install out/kashf-v107-release.apk")
    ok("B: published v1.0.7 release installed", "Success" in out, out[-80:])
    launch(); time.sleep(4); b0 = shot("b_old_release_before")
    adb(f"shell input tap {x} {y}"); time.sleep(3); b1 = shot("b_old_release_with_group")
    ok("B: data created in the old release (tapped 'أولى ثانوي')", diff(b0, b1) > 3, round(diff(b0, b1), 1))
    adb(f"shell am force-stop {PKG}")
    out = adb("install -r out/kashf.apk")
    ok("B: new signed release installs OVER v1.0.7 (same key, no uninstall)", "Success" in out, out[-120:])
    launch(); time.sleep(6); after = shot("b_new_release_after_update")
    dg, de = diff(after, ref_group), diff(after, ref_empty)
    ok("B: after updating, the release shows the group made in the old release (matches 'one group', not 'empty app')", dg < de and dg < 4, f"diff to 'one group' {dg:.1f}, to 'empty' {de:.1f}")
    ok("B: installed version", True, adb(f"shell dumpsys package {PKG} | grep -m1 versionName"))

for part in (part_a, part_b):
    try: part()
    except Exception as e: ok(part.__name__ + " completed", False, repr(e))
json.dump(R, open(f"{OUT}/upgrade.json", "w"), ensure_ascii=False, indent=1)
with open(f"{OUT}/upgrade.md", "w") as f:
    f.write(f"# Upgrade test: {sum(r['ok'] for r in R)}/{len(R)} passed\n\n" + "".join(f"- {'✅' if r['ok'] else '❌'} {r['name']}" + (f" — `{r['detail']}`" if r['detail'] else "") + "\n" for r in R))
print(f"{sum(r['ok'] for r in R)}/{len(R)} passed"); sys.exit(0 if all(r["ok"] for r in R) else 1)
