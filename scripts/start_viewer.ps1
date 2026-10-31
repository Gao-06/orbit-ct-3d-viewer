$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCommand) { throw 'Python 3 was not found on PATH.' }
$url = 'http://127.0.0.1:8765/index.html'
$ready = $false
try { $response = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 2; $ready = $response.StatusCode -eq 200 } catch {}
if (-not $ready) {
  $script = Join-Path $projectRoot 'scripts\serve_viewer.py'
  Start-Process -FilePath $pythonCommand.Source -ArgumentList @(('"' + $script + '"'), '--port', '8765') -WorkingDirectory $projectRoot -WindowStyle Hidden | Out-Null
  for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 200
    try { $response = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 1; if ($response.StatusCode -eq 200) { $ready = $true; break } } catch {}
  }
}
if (-not $ready) { throw 'Viewer server failed to start. Check that port 8765 is available.' }
Start-Process $url