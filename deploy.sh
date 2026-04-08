#!/bin/bash
set -e

# Configuration - Set these in your environment or .env file
if [ -z "$SERVER_IP" ]; then
    echo "❌ ERROR: SERVER_IP environment variable is not set"
    echo "   Set it with: export SERVER_IP=your.server.ip"
    echo "   Or create a .env.local file with: SERVER_IP=your.server.ip"
    exit 1
fi

SERVER_USER="${SERVER_USER:-root}"
APP_DIR="${APP_DIR:-/app/repo}"

echo "🚀 Deploying to $SERVER_USER@$SERVER_IP..."

# Step 1: Push changes to git
echo "📤 Pushing changes to git..."
git add .
git status --short
read -p "Enter commit message (or press Enter to skip commit): " COMMIT_MSG

if [ -n "$COMMIT_MSG" ]; then
    git commit -m "$COMMIT_MSG"
    git push
    echo "✅ Changes pushed to git"
else
    echo "⏭️  Skipping git commit"
fi

# Step 2: Deploy to server
echo ""
echo "🔄 Deploying to server..."
ssh "$SERVER_USER@$SERVER_IP" << 'ENDSSH'
cd /app/repo

echo "📥 Pulling latest changes..."
git pull

echo "🔨 Rebuilding and restarting application..."
docker compose down
docker compose up -d --build

echo ""
echo "⏳ Waiting for services to start..."
sleep 5

echo ""
echo "📊 Service status:"
docker compose ps

echo ""
echo "✅ Deployment complete!"
ENDSSH

echo ""
echo "🎉 Deployment finished successfully!"
echo ""
echo "📱 Application URLs:"
echo "   Streamlit UI: http://$SERVER_IP:8501"
echo "   FastAPI Docs: http://$SERVER_IP:8000/docs"
