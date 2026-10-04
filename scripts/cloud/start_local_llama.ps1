<#
.SYNOPSIS
  Start / stop a local llama.cpp server (Intel Iris Xe via SYCL) on 127.0.0.1:<Port>, the local counterpart of the
  remote T4 service. Uses the files already under outputs\assets (llama.cpp b11146 SYCL build + MiniCPM-V 4.6 GGUFs);
  nothing is downloaded. Loopback only. -Stop ends only the process this script started (pid file).

  Memory note: the server holds roughly 1.5-2 GB while running, which matters on a 16 GB machine that is already
  short of free RAM. Stop it when you are not using it.

.EXAMPLE
  .\scripts\cloud\start_local_llama.ps1
  .\scripts\cloud\start_local_llama.ps1 -Stop
#>
param([int]$Port = 18937, [switch]$Stop)
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$pidFile = Join-Path $root "outputs\local-llama.pid.json"
$logDir = Join-Path $root "outputs\remote-stack"

if ($Stop) {
    if (-not (Test-Path $pidFile)) { "No pid file; nothing to stop."; return }
    $id = (Get-Content $pidFile -Raw | ConvertFrom-Json).pid
    if ($id -and (Get-Process -Id $id -ErrorAction SilentlyContinue)) { Stop-Process -Id $id -Force; "stopped local llama-server (pid $id)" }
    else { "local llama-server (pid $id) is not running" }
    return
}

if (Test-Path $pidFile) {
    $id = (Get-Content $pidFile -Raw | ConvertFrom-Json).pid
    if ($id -and (Get-Process -Id $id -ErrorAction SilentlyContinue)) { throw "Already running (pid $id). Use -Stop first." }
}
$assets = Join-Path $root "outputs\assets"
$server = Join-Path $assets "llama-b11146-sycl\llama-server.exe"
$model = Join-Path $assets "minicpm-v4.6-gguf\MiniCPM-V-4.6-Q4_K_M.gguf"
$mmproj = Join-Path $assets "minicpm-v4.6-gguf\mmproj-MiniCPM-V-4.6-Q8_0.gguf"
foreach ($f in $server, $model, $mmproj) { if (-not (Test-Path $f)) { throw "Missing $f (copied there earlier by the benchmark work)" } }
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$env:ONEAPI_DEVICE_SELECTOR = "opencl:gpu"   # the OpenCL device path was the one that worked on this machine
try {
    $proc = Start-Process -FilePath $server -WindowStyle Hidden -PassThru `
        -ArgumentList @("-m", $model, "--mmproj", $mmproj, "-ngl", "99", "--host", "127.0.0.1", "--port", $Port,
                        "-c", "2048", "--parallel", "1", "--no-cache-prompt", "--reasoning", "off", "--jinja") `
        -RedirectStandardOutput (Join-Path $logDir "local-llama.out.log") -RedirectStandardError (Join-Path $logDir "local-llama.err.log")
} finally { Remove-Item Env:ONEAPI_DEVICE_SELECTOR -ErrorAction SilentlyContinue }

$ok = $false
for ($i = 0; $i -lt 90 -and -not $ok; $i++) {
    Start-Sleep -Seconds 1
    if ($proc.HasExited) { break }
    try { $ok = (Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 2).status -eq "ok" } catch { }
}
if (-not $ok) { throw "Local llama-server did not become healthy; see $logDir\local-llama.err.log" }
@{ pid = $proc.Id; port = $Port; started = (Get-Date -Format s) } | ConvertTo-Json | Set-Content $pidFile -Encoding ascii
"local llama-server : http://127.0.0.1:$Port  (pid $($proc.Id))"
"stop it with       : .\scripts\cloud\start_local_llama.ps1 -Stop"
