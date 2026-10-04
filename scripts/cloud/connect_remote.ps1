<#
.SYNOPSIS
  Connect this laptop to a remote llama-server (for example the rented T4) and expose it to the unmodified
  visualintel CLI / camera demo through a local Ollama-protocol facade.

.DESCRIPTION
  Starts (1) an SSH tunnel  127.0.0.1:<LlamaPort> -> remote 127.0.0.1:8080  (key based, no agent forwarding), and
  (2) scripts/cloud/ollama_facade.py on 127.0.0.1:<FacadePort>. Both listen on loopback only. The process ids are
  written to outputs/remote-stack.pids.json so -Stop ends exactly these processes and nothing else.

  Frames sent through this stack leave your machine. The facade is opt-in: nothing uses it unless you set
    $env:VISUALINTEL_OLLAMA_URL = "http://127.0.0.1:<FacadePort>"
  in the shell that runs visualintel. Close that shell or remove the variable to go back to local Ollama.

.EXAMPLE
  .\scripts\cloud\connect_remote.ps1 -HostName 43.153.154.91 -KeyPath $env:USERPROFILE\.ssh\vi_cloud
  $env:VISUALINTEL_OLLAMA_URL = "http://127.0.0.1:21435"
  .\.venv\Scripts\python.exe -m visualintel scene .\outputs\testkit-cloud\videos\nasa-crew4-science.mp4 --at 100
  .\scripts\cloud\connect_remote.ps1 -Stop
#>
param(
    [string]$HostName,
    [string]$KeyPath,
    [string]$User = "ubuntu",
    [int]$SshPort = 22,
    [int]$LlamaPort = 28080,
    [int]$FacadePort = 21435,
    [switch]$Stop
)
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$pidFile = Join-Path $root "outputs\remote-stack.pids.json"
$logDir = Join-Path $root "outputs\remote-stack"

if ($Stop) {
    if (-not (Test-Path $pidFile)) { "No pid file ($pidFile); nothing to stop."; return }
    $recorded = Get-Content $pidFile -Raw | ConvertFrom-Json
    foreach ($name in "tunnel", "facade") {
        $id = $recorded.$name
        $proc = if ($id) { Get-Process -Id $id -ErrorAction SilentlyContinue } else { $null }
        if ($proc) { Stop-Process -Id $id -Force; "stopped $name (pid $id)" } else { "$name (pid $id) is not running" }
    }
    return
}

if (-not $HostName -or -not $KeyPath) { throw "Pass -HostName and -KeyPath (a dedicated key file), or -Stop." }
if (-not (Test-Path $KeyPath)) { throw "Key file not found: $KeyPath" }
if (Test-Path $pidFile) {
    # The record is kept after -Stop (never deleted); only a still-living recorded process blocks a new start.
    $previous = Get-Content $pidFile -Raw | ConvertFrom-Json
    foreach ($name in "tunnel", "facade") {
        $id = $previous.$name
        if ($id -and (Get-Process -Id $id -ErrorAction SilentlyContinue)) {
            throw "The $name from an earlier start is still running (pid $id). Run with -Stop first."
        }
    }
}
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$ssh = @("-N", "-L", "${LlamaPort}:127.0.0.1:8080", "-i", $KeyPath, "-o", "IdentitiesOnly=yes", "-o", "ForwardAgent=no",
         "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=30",
         "-p", $SshPort, "$User@$HostName")
$tunnel = Start-Process -FilePath ssh.exe -ArgumentList $ssh -WindowStyle Hidden -PassThru `
    -RedirectStandardError (Join-Path $logDir "tunnel.err.log")

$healthy = $false
for ($i = 0; $i -lt 20 -and -not $healthy; $i++) {
    Start-Sleep -Seconds 1
    if ($tunnel.HasExited) { break }
    try { $healthy = (Invoke-RestMethod "http://127.0.0.1:$LlamaPort/health" -TimeoutSec 3).status -eq "ok" } catch { }
}
if (-not $healthy) {
    if (-not $tunnel.HasExited) { Stop-Process -Id $tunnel.Id -Force }
    throw "The remote llama-server did not answer through the tunnel. See $logDir\tunnel.err.log"
}

$python = Join-Path $root ".venv\Scripts\python.exe"
$facade = Start-Process -FilePath $python -WindowStyle Hidden -PassThru `
    -ArgumentList @((Join-Path $root "scripts\cloud\ollama_facade.py"), "--upstream", "http://127.0.0.1:$LlamaPort",
                    "--port", $FacadePort) `
    -RedirectStandardOutput (Join-Path $logDir "facade.out.log") -RedirectStandardError (Join-Path $logDir "facade.err.log")
Start-Sleep -Seconds 2
$tags = Invoke-RestMethod "http://127.0.0.1:$FacadePort/api/tags" -TimeoutSec 5

@{ tunnel = $tunnel.Id; facade = $facade.Id; started = (Get-Date -Format s) } | ConvertTo-Json | Set-Content $pidFile -Encoding ascii
"remote llama-server : http://127.0.0.1:$LlamaPort   (tunnel pid $($tunnel.Id))"
"Ollama-style facade : http://127.0.0.1:$FacadePort   (pid $($facade.Id)), model $($tags.models[0].name)"
""
"To use it in THIS shell (frames then leave your machine):"
"  `$env:VISUALINTEL_OLLAMA_URL = `"http://127.0.0.1:$FacadePort`""
"To go back to local Ollama:  Remove-Item Env:VISUALINTEL_OLLAMA_URL"
"To stop the stack:           .\scripts\cloud\connect_remote.ps1 -Stop"
"Reminder: the rented instance keeps billing until you terminate it in the provider console."
