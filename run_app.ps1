$ErrorActionPreference = "Stop"

$python = "python"
if (Test-Path "C:\Users\Crystal\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe") {
    $python = "C:\Users\Crystal\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
}

& $python -m streamlit run app.py --server.headless true --server.port 8501 --browser.gatherUsageStats false
