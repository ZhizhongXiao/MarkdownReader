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

.EXAMPLE
    pwsh tools/run_browser_acceptance.ps1
    pwsh tools/run_browser_acceptance.ps1 -Channel chromium
#>

param([string]$Channel = "msedge")

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$artifact = Join-Path $repoRoot "renderer\dist\renderer.cjs"
if (-not (Test-Path $artifact)) {
    throw "缺少 $artifact ：先执行 cd renderer; npm ci; npm run build"
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

    $specs = Get-ChildItem -Filter "*.test.mjs" | ForEach-Object { $_.Name }
    node --test --test-reporter spec $specs
    if ($LASTEXITCODE -ne 0) { throw "浏览器验收失败（exit $LASTEXITCODE）" }

    Write-Output "[browser] RESULT OK"
}
finally {
    Pop-Location
}
