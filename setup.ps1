param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$entry = Join-Path $PSScriptRoot 'manage.py'
$config = Join-Path $PSScriptRoot '.local\config.json'
if (!(Test-Path -LiteralPath $config)) {
    $dataDir = Read-Host 'Data folder outside this code folder (e.g. F:\RunningHubData)'
    $ffmpeg = Read-Host 'ffmpeg full path (Enter = ffmpeg on PATH)'
    $ffprobe = Read-Host 'ffprobe full path (Enter = ffprobe on PATH)'
    if (!$ffmpeg) { $ffmpeg = 'ffmpeg' }
    if (!$ffprobe) { $ffprobe = 'ffprobe' }
    & $Python $entry init --data-dir $dataDir --ffmpeg $ffmpeg --ffprobe $ffprobe
    if ($LASTEXITCODE -ne 0) { throw 'Initialization failed.' }
}
& $Python $entry doctor
if ($LASTEXITCODE -ne 0) { throw 'Resolve required environment checks before confirming.' }
$cfg = Get-Content -LiteralPath $config -Raw -Encoding UTF8 | ConvertFrom-Json
Start-Process -FilePath (Join-Path $cfg.data_dir '环境检查.html')
& $Python $entry confirm
if ($LASTEXITCODE -ne 0) { throw 'Not confirmed.' }
Write-Host 'Ready. Read-only preview: python manage.py dashboard'
