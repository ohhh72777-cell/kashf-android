// Runs after `cap add android`: release signing, version from CI, full-screen activity.
// Fails loudly if the generated template ever changes shape.
import fs from "fs";
import path from "path";

const die = (m) => { console.error("patch-android: " + m); process.exit(1); };
const gradleFile = "android/app/build.gradle";
if (!fs.existsSync(gradleFile)) die("missing " + gradleFile);
let g = fs.readFileSync(gradleFile, "utf8");

if (!/versionCode\s+\d+/.test(g)) die("versionCode not found");
g = g.replace(/versionCode\s+\d+/, 'versionCode Integer.parseInt(System.getenv("VERSION_CODE") ?: "1")');
if (!/versionName\s+"[^"]*"/.test(g)) die("versionName not found");
g = g.replace(/versionName\s+"[^"]*"/, 'versionName(System.getenv("VERSION_NAME") ?: "1.0.0")');

if (!/^android\s*\{/m.test(g)) die("android block not found");
g = g.replace(/^android\s*\{/m, `android {
    signingConfigs {
        release {
            // The keystore file is in the repo but encrypted (PKCS12); its password lives only
            // in the KEYSTORE_PASSWORD GitHub secret and with the owner.
            if (System.getenv("KEYSTORE_PASSWORD")) {
                storeFile file("../../signing/kashf-release.p12")
                storeType "pkcs12"
                storePassword System.getenv("KEYSTORE_PASSWORD")
                keyAlias "kashf"
                keyPassword System.getenv("KEYSTORE_PASSWORD")
            }
        }
    }`);
if (!/buildTypes\s*\{\s*release\s*\{/.test(g)) die("release buildType not found");
g = g.replace(/buildTypes\s*\{\s*release\s*\{/, (m) => m + `
            if (System.getenv("KEYSTORE_PASSWORD")) { signingConfig signingConfigs.release }`);
fs.writeFileSync(gradleFile, g);

// Full-screen (immersive) activity: no status/navigation bar, swipe from the edge shows them briefly.
const find = (dir) => {
  for (const f of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, f.name);
    if (f.isDirectory()) { const r = find(p); if (r) return r; }
    else if (f.name === "MainActivity.java") return p;
  }
  return null;
};
const act = find("android/app/src/main/java");
if (!act) die("MainActivity.java not found");
const pkg = (fs.readFileSync(act, "utf8").match(/^package\s+([\w.]+);/m) || [])[1];
if (!pkg) die("package line not found");
fs.writeFileSync(act, `package ${pkg};

import android.os.Bundle;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        hideSystemBars();
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) hideSystemBars();
    }

    private void hideSystemBars() {
        WindowCompat.setDecorFitsSystemWindows(getWindow(), false);
        WindowInsetsControllerCompat c = WindowCompat.getInsetsController(getWindow(), getWindow().getDecorView());
        c.hide(WindowInsetsCompat.Type.systemBars());
        c.setSystemBarsBehavior(WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
    }
}
`);
console.log("patch-android: ok (" + pkg + ")");
