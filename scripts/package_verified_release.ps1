$ErrorActionPreference = 'Stop'
$releaseRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $releaseRoot
$releaseStage = Join-Path $releaseRoot 'output/delivery-source'
if (Test-Path -LiteralPath $releaseStage) { throw 'Preserve existing delivery. Choose a new staging directory.' }
$utf8 = [Text.UTF8Encoding]::new($false)
$sourceFiles = @(git -c core.quotepath=false ls-files)
$sourceRecords = @()
foreach ($relative in $sourceFiles) {
    if ($relative -match '(^|/)(\.git|\.venv|\.tmp|node_modules|output|dist)(/|$)|\.(db|sqlite|sqlite3|pem|key)$' -or ($relative -match '(^|/)\.env($|\.)' -and $relative -notmatch '\.example$')) { throw "Private/runtime path included: $relative" }
    $original = Join-Path $releaseRoot $relative
    $file = Get-Item -LiteralPath $original
    if ($file.Extension -in '.py','.ts','.tsx','.js','.mjs','.md','.json','.yaml','.yml','.ps1','.sh','.example','.txt','.ini','.html','.css') {
        if ([IO.File]::ReadAllText($original) -match '(?i)\bsk-[a-z0-9_-]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bAKIA[A-Z0-9]{16}\b') { throw "Possible credential in $relative" }
    }
    $destination = Join-Path $releaseStage $relative
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination))
    [IO.File]::Copy($original, $destination, $false)
    $sourceRecords += @{path=$relative; bytes=$file.Length; sha256=(Get-FileHash -LiteralPath $original).Hash}
}
$manifest = @{input_zip_sha256='B31F0D34F44FA8931B70F3A7BF0996D331A41C81ED8ED33BD3714192CF721BB4'; baseline_commit='b76fcfe'; delivery_commit=(git rev-parse HEAD); files=$sourceRecords}
[IO.File]::WriteAllText((Join-Path $releaseStage 'SOURCE_MANIFEST.json'), ($manifest | ConvertTo-Json -Depth 8), $utf8)
$patch = (git -c core.quotepath=false diff b76fcfe HEAD --binary --no-ext-diff --no-color) -join "`n"
[IO.File]::WriteAllText((Join-Path $releaseStage 'CHANGES_FROM_USER_ZIP.patch'), $patch, $utf8)
Add-Type -AssemblyName System.IO.Compression.FileSystem
$sourceZip = Join-Path $releaseRoot 'output/考核系统-20261014-验收修复-完整源码.zip'
$evidenceZip = Join-Path $releaseRoot 'output/考核系统-20261014-测试与视觉证据.zip'
[IO.Compression.ZipFile]::CreateFromDirectory($releaseStage, $sourceZip, [IO.Compression.CompressionLevel]::Optimal, $false)
$evidenceStage = Join-Path $releaseRoot 'output/delivery-evidence'
if (Test-Path -LiteralPath $evidenceStage) { throw 'Preserve existing evidence staging.' }
[void][IO.Directory]::CreateDirectory($evidenceStage)
Copy-Item -LiteralPath (Join-Path $releaseRoot 'output/acceptance') -Destination $evidenceStage -Recurse
Copy-Item -LiteralPath (Join-Path $releaseRoot 'output/playwright') -Destination $evidenceStage -Recurse
Copy-Item -LiteralPath (Join-Path $releaseRoot 'docs/RELEASE_ACCEPTANCE_20261014.md') -Destination $evidenceStage
Copy-Item -LiteralPath (Join-Path $releaseRoot 'docs/DEPLOY_ROLLBACK_20261014.md') -Destination $evidenceStage
[IO.Compression.ZipFile]::CreateFromDirectory($evidenceStage, $evidenceZip, [IO.Compression.CompressionLevel]::Optimal, $false)
$archive = [IO.Compression.ZipFile]::OpenRead($sourceZip)
try {
    foreach ($record in $sourceRecords) {
        $entry = $archive.GetEntry($record.path)
        if ($null -eq $entry -or $entry.Length -ne $record.bytes) { throw "Missing source entry $($record.path)" }
        $stream = $entry.Open(); $sha = [Security.Cryptography.SHA256]::Create()
        try { $actual = [Convert]::ToHexString($sha.ComputeHash($stream)) } finally { $sha.Dispose(); $stream.Dispose() }
        if ($actual -ne $record.sha256) { throw "Source mismatch $($record.path)" }
    }
} finally { $archive.Dispose() }
Get-Item -LiteralPath $sourceZip,$evidenceZip | Select-Object FullName,Length
Get-FileHash -LiteralPath $sourceZip,$evidenceZip | Select-Object Path,Hash
