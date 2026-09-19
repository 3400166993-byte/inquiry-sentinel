$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = "C:\Users\Crystal\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}

$listening = netstat -ano | Select-String ":8501\s+.*LISTENING"
if (-not $listening) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $python
    $psi.WorkingDirectory = $root
    $psi.Arguments = "-m streamlit run app.py --server.headless true --server.port 8501 --browser.gatherUsageStats false"
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    [System.Diagnostics.Process]::Start($psi) | Out-Null
    Start-Sleep -Seconds 3
}

try {
    Start-Process "http://localhost:8501/" -ErrorAction Stop
} catch {
    Write-Host "Service started. Open http://localhost:8501/ in your browser."
}
