<#
.SYNOPSIS
    MarkdownReader - vscode-office 上游 pin 检查与更新工具（Windows / PowerShell 7）。

.DESCRIPTION
    只做三件事：报告当前 pin、按 upstream/pin.json 做结构校验、在明确给出 ref 时把子模块切到指定 commit。
    脚本不会自动提交、不会 push、不会切换用户分支、不会跟随 upstream main。

.PARAMETER Check
    默认行为：只读检查（存在性 / 脏工作区 / pin 一致性 / 结构校验）。

.PARAMETER Update
    显式更新到某个 ref（commit SHA、tag 或分支名）。更新后需人工更新 pin.json、跑完整测试并提交 gitlink。

.PARAMETER ExpectCommit
    断言当前 checkout 等于该 commit；不一致时以可读错误退出。

.PARAMETER RepoRoot
    仓库根目录，默认取脚本所在目录的父目录。测试用它可以指向临时目录，以验证错误路径。
#>
[CmdletBinding()]
param(
    [switch]$Check,
    [string]$Update = "",
    [string]$ExpectCommit = "",
    [string]$RepoRoot = ""
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$message) { Write-Host ("[upstream] " + $message) }

function Fail([string]$message) {
    Write-Host ("[upstream] RESULT: ERROR: " + $message) -ForegroundColor Red
    exit 1
}

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}
$RepoRoot = [System.IO.Path]::GetFullPath($RepoRoot)

$gitModulesPath = Join-Path $RepoRoot ".gitmodules"
$pinPath = Join-Path $RepoRoot "upstream" "pin.json"
$submodulePath = Join-Path $RepoRoot "upstream" "vscode-office"

Write-Step ("repo root: " + $RepoRoot)

if (-not (Test-Path -LiteralPath $gitModulesPath)) {
    Fail ".gitmodules 不存在；请先执行：git submodule add https://github.com/cweijan/vscode-office.git upstream/vscode-office"
}
$gitModules = Get-Content -LiteralPath $gitModulesPath -Raw
if ($gitModules -notmatch "upstream/vscode-office") {
    Fail ".gitmodules 中没有 upstream/vscode-office 条目"
}
if (-not (Test-Path -LiteralPath $pinPath)) {
    Fail "缺少 pin 记录 upstream/pin.json"
}
$pin = Get-Content -LiteralPath $pinPath -Raw | ConvertFrom-Json
if (-not (Test-Path -LiteralPath $submodulePath)) {
    Fail "upstream/vscode-office 不存在；请执行：git submodule update --init --recursive"
}
if (-not (Test-Path -LiteralPath (Join-Path $submodulePath ".git"))) {
    Fail "upstream/vscode-office 不是已初始化的 git 工作区；请执行：git submodule update --init --recursive"
}

$dirty = @(git -C $submodulePath status --porcelain)
if ($LASTEXITCODE -ne 0) { Fail "无法读取上游工作区状态（git status 失败）" }
if ($dirty.Count -gt 0) {
    Fail ("上游工作区被修改，MarkdownReader 不修改上游源码。改动：" + ($dirty -join " | "))
}

$currentCommit = (git -C $submodulePath rev-parse HEAD).Trim()
$commitDate = (git -C $submodulePath show -s --format=%cI HEAD).Trim()
$commitSubject = (git -C $submodulePath show -s --format=%s HEAD).Trim()

Write-Step ("pinned commit : " + $pin.pinned_commit)
Write-Step ("current commit: " + $currentCommit)
Write-Step ("commit date   : " + $commitDate + "  (" + $commitSubject + ")")

if ($currentCommit -ne $pin.pinned_commit) {
    Fail ("checkout 与 upstream/pin.json 不一致：" + $currentCommit + " != " + $pin.pinned_commit + "；请确认这是有意的更新并同步 pin 记录")
}

if (-not [string]::IsNullOrWhiteSpace($ExpectCommit)) {
    if ($currentCommit -ne $ExpectCommit) {
        Fail ("期望 commit " + $ExpectCommit + "，实际 " + $currentCommit)
    }
    Write-Step "ExpectCommit 校验通过"
}

$packageJsonPath = Join-Path $submodulePath "package.json"
foreach ($relative in $pin.verify.paths) {
    $full = Join-Path $submodulePath ($relative -replace "/", "\\")
    if (-not (Test-Path -LiteralPath $full)) {
        Fail ("pin.json 记录的上游路径不存在：" + $relative)
    }
}
$package = Get-Content -LiteralPath $packageJsonPath -Raw | ConvertFrom-Json
foreach ($property in $pin.verify.dependencies.PSObject.Properties) {
    $name = $property.Name
    $expected = [string]$property.Value
    $actual = $package.dependencies.PSObject.Properties[$name]
    if (-not $actual) {
        Fail ("pin.json 记录依赖 " + $name + "，但上游 package.json 中没有它")
    }
    if ([string]$actual.Value -ne $expected) {
        Fail ("依赖版本漂移：" + $name + " 期望 " + $expected + "，实际 " + $actual.Value)
    }
}
foreach ($name in $pin.verify.absent_dependencies) {
    if ($package.dependencies.PSObject.Properties[$name]) {
        Fail ("pin.json 记录 " + $name + " 在该 commit 中不存在，但上游现在有了它：需要显式复核")
    }
}
$depCount = @($pin.verify.dependencies.PSObject.Properties).Count
Write-Step ("结构校验通过：" + @($pin.verify.paths).Count + " 条路径 / " + $depCount + " 项依赖 / " + @($pin.verify.absent_dependencies).Count + " 项确认不存在")

if (-not [string]::IsNullOrWhiteSpace($Update)) {
    Write-Step ("更新到 ref: " + $Update)
    $resolved = (git -C $submodulePath rev-parse --verify ($Update + "^{commit}") 2>$null)
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($resolved)) {
        Write-Step "本地无法解析该 ref，尝试 fetch origin"
        git -C $submodulePath fetch --no-tags origin | Out-Host
        $resolved = (git -C $submodulePath rev-parse --verify ($Update + "^{commit}") 2>$null)
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($resolved)) {
            Fail ("无法把 " + $Update + " 解析成 commit；请给出完整 SHA，或已 fetch 的 tag/分支名")
        }
    }
    $resolved = $resolved.Trim()
    git -C $submodulePath checkout --detach $resolved | Out-Host
    if ($LASTEXITCODE -ne 0) { Fail "checkout 失败" }
    $newCommit = (git -C $submodulePath rev-parse HEAD).Trim()
    Write-Step ("已 checkout：" + $newCommit)
    Write-Host ""
    Write-Host "后续必须人工完成（脚本不会自动做）：" -ForegroundColor Yellow
    Write-Host "  1) 更新 upstream/pin.json：commit / commit_date / commit_subject / package_version / 能力证据"
    Write-Host "  2) 跑完整测试：uv run pytest -q    以及   uv run pytest -q --runxfail tests/test_markdown_compat_target.py"
    Write-Host "  3) 检查 git diff --submodule=diff 并提交新的 gitlink"
    Write-Host "  4) 不要直接跟随 upstream main：只在明确评估后更新"
} else {
    Write-Step "只读检查完成，未做任何修改"
}

Write-Step "本脚本不会自动提交、不会 push、不会切换用户分支、不会跟随 upstream main。"
Write-Step "RESULT: OK"
exit 0
