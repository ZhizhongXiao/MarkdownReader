# MarkdownReader 1.0.1 Windows x64 candidate

Status: **Candidate only — 35-item clean-Windows manual acceptance is pending.** This is not the published release.

## Build identity

- Built at: 2026-10-02 18:16:47 +08:00
- Source commit: `e084c57d9f026545cab91e8588d15cab59091046`
- Production renderer: v2
- Pinned vscode-office commit: `908258dafc827ce0475fe7671d414914fbd3867b`
- Python: 3.12.10
- PyInstaller: 6.22.3
- Embedded Node: v24.20.0 x64 (SHA-256 `5c976096e04e5c2c1f091938926234cc9fbebfe9787ddd149351b3b0ecc707b5`)
- npm: 11.19.0
- `uv.lock`: `97bc03b9ca0ab51baa5f02f7ee2e63bcd56ebfde2559a21524e339966e9db73b`
- `renderer/package-lock.json`: `d50e7313bd0740feec9aab841f09466f02795ff92ac8ae7561151f3a793b7c48`
- `node_renderer/package-lock.json`: `595677e3781d3cb14d1fc87bb7f3bae02b1fb3d27567c15019141b18cc31d607`

## Exact candidate artifacts

| File | SHA-256 |
|---|---|
| `MarkdownReader-1.0.1-win-x64.exe` | `f2bbc8930898b73067151bbf67e118c83f55f514fda9a1c5c5529fb0a1999dd0` |
| `MarkdownReader-1.0.1-portable-win-x64.zip` | `3b042e2175d78ab3d04a025c23c8d2a3e90d4d7601c75c42d603850de4a8ce4a` |

The files are under `output/candidate-1.0.1-e084c57/dist/`. `output/candidate-1.0.1-e084c57/dist/SHA256SUMS.txt` and `output/candidate-1.0.1-e084c57/dist/release-record-1.0.1.md` are generated from the same packaged files.

## Automated checks

- `renderer: npm ci; npm test` — PASS, 91 tests; npm audit reported 0 vulnerabilities.
- `packaging/validate_release.py --mode both --wait 20` — PASS for onefile and onedir; both launch smoke checks passed.
- Python static review — PASS, 5 changed Python files; syntax, Ruff, and Pyright each reported 0 errors.
- Focused release/version contracts — PASS, 58 tests.
- Full project suite — PASS, 802 passed, 1 skipped.
- Browser acceptance — PASS, 11 passed, 1 optional skip.
- `uv lock --check` — PASS.

## QA materials

The version-matched sample documents and operating guide are in `QA-materials/`; generated with `packaging/qa_prepare.py --output QA-materials --dist-dir dist`.

## Remaining acceptance

Run all 35 items in `docs/QA-CHECKLIST-1.0.1-v2.md` against the exact EXE and ZIP above on a clean Windows 11 machine. The checklist is intentionally unchecked until that run is actually completed.