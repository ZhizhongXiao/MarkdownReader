<#
.SYNOPSIS
    Phase 5B 的 opt-in 浏览器验收：离线打开含 Mermaid 的 HTML，并断言 runtime 真的生成 SVG。

.DESCRIPTION
    默认 pytest 不依赖浏览器（平台工具缺失不得阻塞提交），因此浏览器验收是显式入口。
    流程：确认 renderer/dist 已构建 → 必要时 npm ci → node --test（tests/browser）。

    测试内部会拦截并记录所有非 file:// 请求，因此「离线可显示」是被强制验证的，
    而不是靠假设。

.PARAMETER Channel
    浏览器 channel，默认 msedge（用系统已装的 Edge，不下载浏览器）。
    可选 chrome；chromium 需先 `npx playwright install chromium`。

.PARAMETER ExtraPage
    额外用真实浏览器离线打开一份「Python assembler 装配出的 HTML」（Phase 5D 的窄集成 smoke）。
    页面由 `uv run python tools/assemble_document.py --out <file>` 生成；
    不传该参数时对应用例整条跳过，默认 5 项验收不变。

.EXAMPLE
    pwsh tools/run_browser_acceptance.ps1
    pwsh tools/run_browser_acceptance.ps1 -Channel chromium
    pwsh tools/run_browser_acceptance.ps1 -ExtraPage build/smoke.html
#>

param([string]$Channel = "msedge", [string]$ExtraPage = "")

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$artifact = Join-Path $repoRoot "renderer\dist\renderer.cjs"
if (-not (Test-Path $artifact)) {
    throw "缺少 $artifact ：先执行 cd renderer; npm ci; npm run build"
}

# 相对调用者当前目录解析，必须在 Push-Location 之前完成。
$extraPagePath = ""
if ($ExtraPage) {
    $extraPagePath = (Resolve-Path $ExtraPage).Path
}

$browserDirectory = Join-Path $repoRoot "tests\browser"
Push-Location $browserDirectory
try {
    if (-not (Test-Path (Join-Path $browserDirectory "node_modules"))) {
        Write-Output "[browser] 首次运行：npm ci（这一步需要网络，只装 playwright 驱动，不下载浏览器）"
        npm ci
        if ($LASTEXITCODE -ne 0) { throw "npm ci 失败（exit $LASTEXITCODE）" }
    }

    $env:MR_BROWSER_CHANNEL = $Channel
    Write-Output "[browser] channel = $Channel"

    if ($extraPagePath) {
        $env:MR_EXTRA_PAGE = $extraPagePath
        Write-Output "[browser] extra page = $extraPagePath"
    }
    else {
        Remove-Item Env:\MR_EXTRA_PAGE -ErrorAction SilentlyContinue
    }

    $specs = Get-ChildItem -Filter "*.test.mjs" | ForEach-Object { $_.Name }
    node --test --test-reporter spec $specs
    if ($LASTEXITCODE -ne 0) { throw "浏览器验收失败（exit $LASTEXITCODE）" }

    Write-Output "[browser] RESULT OK"
}
finally {
    Pop-Location
}
