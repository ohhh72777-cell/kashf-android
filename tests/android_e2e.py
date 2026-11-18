"""End-to-end test of the installed APK on an Android emulator.

Drives the real app: real touches via `adb input tap`, real process kills, airplane mode,
hardware back key, rotation, and reads app state through the WebView's DevTools socket
(debug build only — the release build has debugging off).
"""
import json, os, re, subprocess, sys, time, urllib.request
import websocket

PKG = "com.tarekelborai.kashf"
OUT = sys.argv[1] if len(sys.argv) > 1 else "report"
os.makedirs(OUT, exist_ok=True)
R = []


def sh(c, timeout=120):
    return subprocess.run(c, shell=True, capture_output=True, text=True, timeout=timeout)


def adb(c, timeout=120):
    r = sh("adb " + c, timeout)
    return (r.stdout + r.stderr).strip()


def ok(name, cond, detail=""):
    R.append({"name": name, "ok": bool(cond), "detail": str(detail)[:400]})
    print(("PASS " if cond else "FAIL ") + name + (" — " + str(detail)[:200] if detail else ""), flush=True)


def shot(name):
    sh(f"adb exec-out screencap -p > {OUT}/{name}.png")


class Page:
    def __init__(self, timeout=60):
        t0 = time.time()
        last = ""
        while time.time() - t0 < timeout:
            pid = adb(f"shell pidof {PKG}").split()
            if pid:
                pid = pid[0]
                socks = adb("shell cat /proc/net/unix")
                if f"webview_devtools_remote_{pid}" in socks:
                    sh("adb forward --remove-all")
                    adb(f"forward tcp:9222 localabstract:webview_devtools_remote_{pid}")
                    try:
                        pages = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=5))
                        pg = [p for p in pages if p.get("type") == "page" and "localhost" in p.get("url", "")]
                        if pg:
                            self.ws = websocket.create_connection(pg[0]["webSocketDebuggerUrl"], timeout=30, suppress_origin=True)
                            self.i = 0
                            if self.wait("document.readyState==='complete'&&!!window.__kashf&&window.__kashf.S.ready", 30):
                                return
                    except Exception as e:
                        last = repr(e)
            time.sleep(1)
        raise RuntimeError("could not attach to the app WebView " + last)

    def ev(self, expr):
        self.i += 1
        self.ws.send(json.dumps({"id": self.i, "method": "Runtime.evaluate",
                                 "params": {"expression": expr, "awaitPromise": True, "returnByValue": True}}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == self.i:
                r = m.get("result", {})
                if "exceptionDetails" in r:
                    raise RuntimeError(json.dumps(r["exceptionDetails"])[:300])
                return r.get("result", {}).get("value")

    def wait(self, expr, t=15):
        t0 = time.time()
        while time.time() - t0 < t:
            try:
                if self.ev(expr):
                    return True
            except Exception:
                pass
            time.sleep(0.25)
        return False

    def click(self, sel):
        return self.ev(f"(()=>{{const e=document.querySelector({json.dumps(sel)});if(!e)return false;e.click();return true}})()")

    def tap(self, sel):
        """A real touch on the screen (not a JS click)."""
        r = self.ev(f"(()=>{{const e=document.querySelector({json.dumps(sel)});if(!e)return null;e.scrollIntoView({{block:'center'}});const b=e.getBoundingClientRect();return [b.x+b.width/2,b.y+b.height/2,devicePixelRatio]}})()")
        if not r:
            return False
        time.sleep(0.3)
        r = self.ev(f"(()=>{{const e=document.querySelector({json.dumps(sel)});const b=e.getBoundingClientRect();return [b.x+b.width/2,b.y+b.height/2,devicePixelRatio]}})()")
        adb(f"shell input tap {int(r[0] * r[2])} {int(r[1] * r[2])}")
        return True

    def pin(self, digits):
        for d in digits:
            self.click(f'.key[data-k="{d}"]')
            time.sleep(0.05)


def launch():
    out = adb(f"shell am start -W -n {PKG}/.MainActivity")
    m = re.search(r"TotalTime:\s*(\d+)", out)
    return int(m.group(1)) if m else None


def restart():
    adb(f"shell am force-stop {PKG}")
    time.sleep(1)
    launch()
    return Page()


def card_sel(i):
    return f'#agrid .card:nth-child({i})'


def run():
    fixture = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "claude-backup.json"), encoding="utf-8"))
    sdk = adb("shell getprop ro.build.version.sdk")
    abi = adb("shell getprop ro.product.cpu.abi")
    ok("device", True, f"Android API {sdk}, ABI {abi}")

    t = launch()
    p = Page()
    ok("app opens directly (no browser), cold start ms", t is not None, t)
    info = p.ev("({native:window.__kashf.NATIVE,plugins:Object.keys((window.Capacitor&&Capacitor.Plugins)||{}),w:innerWidth,h:innerHeight,ua:navigator.userAgent})")
    ok("running as native app, Capacitor plugins available", info["native"] and all(x in info["plugins"] for x in ("App", "Filesystem", "Share")), info["plugins"])
    ok("WebView version", True, re.search(r"Chrome/[\d.]+", info["ua"]).group(0) if re.search(r"Chrome/[\d.]+", info["ua"]) else info["ua"])
    full = p.ev("screen.height*devicePixelRatio")
    ok("full screen (no browser bar)", abs(info["h"] - p.ev("screen.height")) <= 2, f"viewport {info['w']}x{info['h']}, screen {p.ev('screen.width')}x{p.ev('screen.height')}")
    ok("starts in device-storage mode", "محفوظ على الجهاز" in p.ev("document.querySelector('#sync').textContent"))

    # --- set up a 40-student group (one-time typing, as the teacher would)
    p.click('[data-act="quickgroup"][data-n="أولى ثانوي"]')
    p.wait("!!document.querySelector('[data-act=bulk]')")
    p.click('[data-act="bulk"]')
    p.wait("!!document.querySelector('#bulkN')")
    names = [f"طالب تجربة {i}" for i in range(1, 41)]
    p.ev(f"document.querySelector('#bulkN').value={json.dumps(chr(10).join(names))}")
    p.ev("document.querySelector('.sheet form').requestSubmit()")
    p.click('[data-act="screen"][data-s="att"]')
    ok("group + 40 students created", p.wait("document.querySelectorAll('#agrid .card').length===40"))

    # --- real touches on cards
    for i in (1, 2, 3):
        p.tap(card_sel(i))
        time.sleep(0.4)
    on = p.ev("[1,2,3].map(i=>document.querySelector('#agrid .card:nth-child('+i+')').classList.contains('on'))")
    ok("real finger taps mark students present", all(on), on)
    shot("phone_attendance")

    # --- kill the app, reopen
    p = restart()
    p.wait("document.querySelectorAll('#agrid .card').length===40")
    on = p.ev("[1,2,3,4].map(i=>document.querySelector('#agrid .card:nth-child('+i+')').classList.contains('on'))")
    ok("attendance survives killing the app", on == [True, True, True, False], on)

    # --- no internet
    adb("shell cmd connectivity airplane-mode enable")
    time.sleep(2)
    p.tap(card_sel(4))
    time.sleep(0.5)
    ok("works in airplane mode", p.ev("document.querySelector('#agrid .card:nth-child(4)').classList.contains('on')"))
    p = restart()
    p.wait("document.querySelectorAll('#agrid .card').length===40")
    ok("airplane-mode change still there after restart", p.ev("document.querySelector('#agrid .card:nth-child(4)').classList.contains('on')"))
    adb("shell cmd connectivity airplane-mode disable")

    # --- finance with PIN
    p.click('[data-act="screen"][data-s="fin"]')
    p.wait("!!document.querySelector('[data-act=pinsetup]')")
    p.click('[data-act="pinsetup"]')
    p.wait("!!document.querySelector('.key')")
    p.pin("1357"); time.sleep(0.3); p.pin("1357")
    ok("PIN created, recovery code shown", p.wait("!!document.querySelector('.sheet .code')", 20))
    p.click('.sheet [data-act="close"]')
    p.click('[data-act="addmonth"][data-n="نوفمبر"]')
    p.wait("!!document.querySelector('[data-act=gfee]')")
    p.click('[data-act="gfee"]')
    for d in "250":
        p.click(f'.sheet .key[data-k="{d}"]')
    p.click('[data-act="amtsave"]')
    p.wait("!!document.querySelector('.pc')")
    p.tap(".pc")
    ok("payment recorded with a real tap", p.wait("!!document.querySelector('.pc.paid')"))
    shot("phone_finance")
    ls = p.ev("JSON.stringify(Object.assign({},localStorage))")
    leaks = [w for w in ('"a":250', "نوفمبر", '"1357"', ":1357") if w in ls]
    ok("no plain amounts / month names / PIN in app storage", not leaks, leaks)

    p = restart()
    p.click('[data-act="screen"][data-s="fin"]')
    p.wait("!!document.querySelector('.key')")
    ok("finance locked after restart, no amounts visible", p.ev("!document.querySelector('.pc')&&!document.querySelector('#view').textContent.includes('٢٥٠')"))
    p.pin("2468")
    ok("wrong PIN refused", p.wait("document.querySelector('#pperr').textContent.includes('غلط')", 20))
    p.pin("1357")
    ok("right PIN opens, payment intact", p.wait("!!document.querySelector('.pc.paid')", 20))

    # --- hardware back key
    p.click('[data-act="screen"][data-s="set"]')
    time.sleep(0.5)
    adb("shell input keyevent 4")
    ok("Back key returns to attendance", p.wait("document.querySelector('.tab[aria-current=page]').textContent.trim()==='الحضور'", 5))
    ok("leaving finance locked it again", p.ev("!window.__kashf.F.key"))

    # --- backup file
    p.click('[data-act="screen"][data-s="set"]')
    time.sleep(0.4)
    p.click('[data-act="export"]')
    time.sleep(4)
    focus = adb("shell dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'")
    docs = adb("shell ls /sdcard/Documents/")
    ok("backup: share sheet opened", "Chooser" in focus or "Resolver" in focus or "intentresolver" in focus.lower(), focus.splitlines()[0] if focus else "")
    shot("phone_share_sheet")
    ok("backup: file saved in Documents", "kashf-backup" in docs, docs[:200])
    adb("shell input keyevent 4")
    time.sleep(1)

    # --- board layout: 1920x1080 landscape
    adb("shell settings put system accelerometer_rotation 0")
    adb("shell wm size 1080x1920")
    adb("shell wm density 160")
    adb("shell settings put system user_rotation 1")
    time.sleep(3)
    p = restart()
    p.wait("document.querySelectorAll('#agrid .card').length===40")
    time.sleep(1)
    dim = p.ev("[innerWidth,innerHeight,(()=>{const v=document.querySelector('#view');return v.scrollHeight<=v.clientHeight+2})()]")
    ok("board size landscape 1920x1080: all 40 students on one screen", dim[0] > dim[1] and dim[2], dim)
    shot("board_landscape_attendance")
    p.click('[data-act="screen"][data-s="fin"]')
    p.wait("!!document.querySelector('.key')")
    p.pin("1357")
    p.wait("!!document.querySelector('.pc.paid')")
    shot("board_landscape_finance")
    p.click('[data-act="screen"][data-s="att"]')
    adb("shell wm size reset")
    adb("shell wm density reset")
    adb("shell settings put system user_rotation 0")
    time.sleep(3)
    p = restart()
    dim = p.ev("[innerWidth,innerHeight]")
    ok("phone portrait", dim[1] > dim[0], dim)
    shot("phone_portrait")

    # --- restore a backup made with the Claude (web) version on a clean install
    adb(f"shell pm clear {PKG}")
    launch()
    p = Page()
    p.ev(f"window.__kashf.importData({json.dumps(fixture, ensure_ascii=False)})")
    time.sleep(1.5)
    ids = p.ev("Object.keys(JSON.parse(localStorage.getItem('k2:l:core')).students).sort()")
    ok("web-version backup restored with the same student IDs", ids == sorted(fixture["docs"]["core"]["students"].keys()), ids)
    p = restart()
    p.click('[data-act="screen"][data-s="fin"]')
    p.wait("!!document.querySelector('.key')")
    p.pin("7777")
    ok("same PIN as the web version opens the restored finance", p.wait("!!document.querySelector('.pc.paid')", 20))


try:
    run()
except Exception as e:
    ok("test run completed", False, repr(e))
    shot("failure")
crash = adb("logcat -d -b crash")
ok("no app crash in logcat", PKG not in crash, crash[-300:])
json.dump(R, open(f"{OUT}/e2e.json", "w"), ensure_ascii=False, indent=1)
passed = sum(r["ok"] for r in R)
with open(f"{OUT}/e2e.md", "w") as f:
    f.write(f"# Android E2E: {passed}/{len(R)} passed\n\n")
    for r in R:
        f.write(f"- {'✅' if r['ok'] else '❌'} {r['name']}" + (f" — `{r['detail']}`" if r["detail"] else "") + "\n")
print(f"{passed}/{len(R)} passed")
sys.exit(0 if passed == len(R) else 1)
