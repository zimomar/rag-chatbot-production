# PowerShell deployment script for RAG Chatbot
param(
    [string]$ServerIP = $env:SERVER_IP,
    [string]$ServerUser = $env:SERVER_USER ?? "root",
    [string]$AppDir = $env:APP_DIR ?? "/app/repo"
)

# Validate required parameters
if ([string]::IsNullOrEmpty($ServerIP)) {
    Write-Host "❌ ERROR: SERVER_IP is not set" -ForegroundColor Red
    Write-Host "   Option 1: Set environment variable: `$env:SERVER_IP = 'your.server.ip'" -ForegroundColor Yellow
    Write-Host "   Option 2: Pass as parameter: .\deploy.ps1 -ServerIP 'your.server.ip'" -ForegroundColor Yellow
    Write-Host "   Option 3: Create .env.local file (see .env.local.example)" -ForegroundColor Yellow
    exit 1
}

Write-Host "🚀 Deploying to $ServerUser@$ServerIP..." -ForegroundColor Cyan

# Step 1: Git operations
Write-Host "`n📤 Preparing git changes..." -ForegroundColor Yellow
git add .
git status --short

$commitMsg = Read-Host "Enter commit message (or press Enter to skip commit)"

if ($commitMsg) {
    git commit -m $commitMsg
    git push
    Write-Host "✅ Changes pushed to git" -ForegroundColor Green
} else {
    Write-Host "⏭️  Skipping git commit" -ForegroundColor Gray
}

# Step 2: Deploy to server
Write-Host "`n🔄 Deploying to server..." -ForegroundColor Yellow

$sshCommand = @"
cd $AppDir && \
echo '📥 Pulling latest changes...' && \
git pull && \
echo '🔨 Rebuilding and restarting application...' && \
docker compose down && \
docker compose up -d --build && \
echo '⏳ Waiting for services to start...' && \
sleep 5 && \
echo '📊 Service status:' && \
docker compose ps && \
echo '✅ Deployment complete!'
"@

ssh "$ServerUser@$ServerIP" $sshCommand

Write-Host "`n🎉 Deployment finished successfully!" -ForegroundColor Green
Write-Host "`n📱 Application URLs:" -ForegroundColor Cyan
Write-Host "   Streamlit UI: http://$ServerIP:8501" -ForegroundColor White
Write-Host "   FastAPI Docs: http://$ServerIP:8000/docs" -ForegroundColor White
