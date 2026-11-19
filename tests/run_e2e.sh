#!/usr/bin/env bash
# Runs inside the emulator job. 1) install + launch the RELEASE apk exactly as a user would,
# 2) reinstall the DEBUG build (same code, DevTools enabled) and run the scripted test.
set -u
PKG=com.tarekelborai.kashf
mkdir -p report
adb wait-for-device
adb shell settings put global window_animation_scale 0 || true
# the one-time system notice 'Viewing full screen' would cover the first taps
adb shell settings put secure immersive_mode_confirmations confirmed || true
{
  echo "## Install test"
  if [ -f out/kashf.apk ]; then APK=out/kashf.apk; KIND=release; else APK=out/kashf-debug.apk; KIND="debug (release not signed: KEYSTORE_PASSWORD secret missing)"; fi
  echo "- apk: $KIND"
  echo "- install: $(adb install -r "$APK" 2>&1 | tail -1)"
  echo "- launch: $(adb shell am start -W -n $PKG/.MainActivity 2>&1 | grep -E 'Status|TotalTime' | tr '\n' ' ')"
  sleep 8
  echo "- process running: $(adb shell pidof $PKG || echo NO)"
  echo "- installed versionName: $(adb shell dumpsys package $PKG | grep -m1 versionName | xargs)"
} | tee report/install.md
adb exec-out screencap -p > report/release_launch.png
adb logcat -d -b crash > report/crash-release.txt || true
adb uninstall $PKG >/dev/null 2>&1 || true
adb install -r out/kashf-debug.apk
adb logcat -c || true
python3 tests/android_e2e.py report; RC=$?
python3 tests/upgrade_e2e.py report || RC=1
adb logcat -d -v time > report/logcat-full.txt 2>/dev/null || true
grep -E "kashf|chromium|Capacitor|ActivityManager|AndroidRuntime|WebView|lowmemory|libc|DEBUG" report/logcat-full.txt | tail -3000 > report/logcat.txt || true
rm -f report/logcat-full.txt
exit $RC
