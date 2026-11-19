# Upgrade test: 19/19 passed

- ✅ A: old app (v1.0.7 code) installed — `Performing Streamed Install
Success`
- ✅ A: old app is v1.0.7
- ✅ A: realistic data in the old app (6 groups, 199 students, PIN, payments)
- ✅ A: new version installed over the old one (no uninstall) — `Performing Streamed Install
Success`
- ✅ A: running the new version — `1.0.9`
- ✅ A: every stored item still there — `[]`
- ✅ A: no stored item changed by the update — `[]`
- ✅ A: only the safety records were added — `['k2:appver', 'k2:autobk']`
- ✅ A: kill-safe copies of the data still on disk
- ✅ A: automatic copy made before the update was used — `{'name': 'kashf-auto-before-v1.0.9-2026-11-19.json', 'at': 1795085303283, 'docs': 16, 'pub': True, 'from': None, 'to': '1.0.9'}`
- ✅ A: copy is visible to the user in Documents/Kashf
- ✅ A: register shows the 43-group with today's marks exactly as left
- ✅ A: same PIN opens finance, payments and totals identical
- ✅ A: settings kept
- ✅ B: published v1.0.7 release installed — `Performing Streamed Install
Success`
- ✅ B: data created in the old release (tapped 'أولى ثانوي') — `33.7`
- ✅ B: new signed release installs OVER v1.0.7 (same key, no uninstall) — `Performing Streamed Install
Success`
- ✅ B: after updating, the release shows the group made in the old release (matches 'one group', not 'empty app') — `diff to 'one group' 0.0, to 'empty' 14.1`
- ✅ B: installed version — `versionName=1.0.9`
