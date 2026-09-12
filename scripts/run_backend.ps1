Set-Location 'D:\PitWall\PitWall-RAG'
Write-Host 'PitWall Backend Process' -ForegroundColor Green
& '.\venv\Scripts\python.exe' -m uvicorn api.main:app --port 8000 2>&1 | Tee-Object -FilePath 'backend.log' -Append
