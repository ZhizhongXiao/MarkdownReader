<#
.SYNOPSIS
    Vendored Mermaid browser runtime 的显式更新工具（Phase 5B）。

.DESCRIPTION
    普通 `npm run build` 绝不联网、也绝不更新 runtime：它只校验
    renderer/vendor/mermaid/<version>/ 里已提交的产物（版本、字节数、SHA-256）。
    本脚本是唯一会访问网络的入口，只在主动升级 Mermaid runtime 时运行。

    产物来源是 mermaid 官方 npm 包自带的正式 browser 构建 dist/mermaid.min.js（UMD），
    而不是自行用 bundler 拼装 —— 这样既拿到的就是上游发布的制品，也不会把 mermaid 的
    依赖树带进 renderer 的构建。

.PARAMETER Version
    精确版本（不是范围）。必须与 upstream/vscode-office 声明的 mermaid 范围一致
    （当前 pin 的上游声明 ^11.15.0）。

.PARAMETER ExpectSha256
    期望的产物 SHA-256（十六进制）。升级时用于确认产物未变；首次引入时用于锁定。

.EXAMPLE
    pwsh tools/update_mermaid_runtime.ps1 -Version 11.15.0
#>

param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$ExpectSha256 = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$vendorDir = Join-Path $repoRoot "renderer\vendor\mermaid\$Version"
$artifactName = "mermaid.min.js"
$tarballMember = "package/dist/$artifactName"
$licenseMember = "package/LICENSE"
$utf8 = New-Object System.Text.UTF8Encoding($false)

Write-Output "[mermaid] 更新 target: $Version"

# 1) 唯一的联网步骤：把精确版本装成 tarball（不安装依赖树，只取制品）。
$tempDir = Join-Path $env:TEMP ("mr-mermaid-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
try {
    Push-Location $tempDir
    $packed = (& npm pack "mermaid@$Version" --silent 2>&1 | Select-Object -Last 1)
    Pop-Location
    $tarball = Join-Path $tempDir ([string]$packed).Trim()
    if (-not (Test-Path $tarball)) {
        throw "npm pack 未产出 tarball：$packed"
    }

    # 2) 只提取运行期制品与许可证；其余（sourcemap、ESM、d.ts）刻意不带进仓库。
    & tar -xzf $tarball -C $tempDir $tarballMember $licenseMember
    if ($LASTEXITCODE -ne 0) {
        throw "解包失败：$tarballMember / $licenseMember"
    }

    $artifactPath = Join-Path $tempDir ($tarballMember -replace "/", "\")
    $licensePath = Join-Path $tempDir ($licenseMember -replace "/", "\")
    if (-not (Test-Path $artifactPath)) { throw "npm 包内缺少正式 browser 产物：$tarballMember" }
    if (-not (Test-Path $licensePath)) { throw "npm 包内缺少许可证：$licenseMember" }

    # 3) 计算并校验 SHA-256（升级时可用 -ExpectSha256 显式确认没有变化）。
    $sha256 = (Get-FileHash -Path $artifactPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $bytes = (Get-Item $artifactPath).Length
    if ($ExpectSha256 -and ($sha256 -ne $ExpectSha256.ToLowerInvariant())) {
        throw "产物 SHA-256 不匹配：期望 $ExpectSha256，实际 $sha256"
    }

    # 4) 记录来源：tarball 的 sha1 由 registry metadata 给出，便于审计这次取的是哪一个包。
    $tarballUrl = (& npm view "mermaid@$Version" dist.tarball 2>&1 | Select-Object -Last 1).Trim()
    $tarballSha1 = (& npm view "mermaid@$Version" dist.shasum 2>&1 | Select-Object -Last 1).Trim()

    # 5) 落盘：产物 + 许可证 + metadata（LF 换行，UTF-8 无 BOM）。
    $existing = Join-Path $vendorDir "metadata.json"
    $hadMetadata = Test-Path $existing
    New-Item -ItemType Directory -Path $vendorDir -Force | Out-Null
    Copy-Item -Path $artifactPath -Destination (Join-Path $vendorDir $artifactName) -Force
    Copy-Item -Path $licensePath -Destination (Join-Path $vendorDir "LICENSE") -Force

    $metadata = [ordered]@{
        name = "mermaid"
        version = $Version
        source = "npm"
        package = "mermaid@$Version"
        tarball = $tarballUrl
        tarball_sha1 = $tarballSha1
        artifact = "dist/$artifactName"
        artifact_sha256 = $sha256
        artifact_bytes = $bytes
        license = "MIT"
        license_file = "LICENSE"
        upstream_declaration = "upstream/vscode-office/package.json declares ^11.15.0 (Phase 2 pin 908258d)"
        retrieved = (Get-Date -Format "yyyy-MM-dd")
    }
    $json = ($metadata | ConvertTo-Json -Depth 4) -replace "`r`n", "`n"
    if (-not $json.EndsWith("`n")) { $json += "`n" }
    [System.IO.File]::WriteAllText((Join-Path $vendorDir "metadata.json"), $json, $utf8)

    Write-Output "[mermaid] artifact   : $artifactName  $bytes bytes"
    Write-Output "[mermaid] sha256     : $sha256"
    Write-Output "[mermaid] tarball    : $tarballUrl  (sha1 $tarballSha1)"
    Write-Output "[mermaid] written to : renderer/vendor/mermaid/$Version/ (metadata.json, LICENSE)"
    if ($hadMetadata) { Write-Output "[mermaid] 注意：这是覆盖更新，请在提交说明里写清 from/to。" }
    Write-Output "[mermaid] RESULT OK"
}
finally {
    Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}
