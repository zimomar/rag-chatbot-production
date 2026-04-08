# Deployment Guide

## Setup (First Time Only)

### 1. Configure Deployment Credentials

Create a `.env.deploy` file in the project root:

```bash
cp .env.deploy.example .env.deploy
```

Edit `.env.deploy` with your server details:
```env
SERVER_IP=your.server.ip.here
SERVER_USER=root
APP_DIR=/app/repo
```

**⚠️ IMPORTANT:** Never commit `.env.deploy` to git! It's already in `.gitignore`.

### 2. Alternative: Environment Variables

Instead of `.env.deploy`, you can set environment variables:

**Windows (PowerShell):**
```powershell
$env:SERVER_IP = "your.server.ip"
$env:SERVER_USER = "root"
```

**Linux/Mac (Bash):**
```bash
export SERVER_IP="your.server.ip"
export SERVER_USER="root"
```

Add these to your shell profile (`~/.bashrc`, `~/.zshrc`, or PowerShell profile) to persist them.

---

## Quick Deploy

### Option 1: Manual Script (Recommended)

**Windows (PowerShell):**
```powershell
.\deploy.ps1
```

Or pass parameters directly:
```powershell
.\deploy.ps1 -ServerIP "your.ip" -ServerUser "root"
```

**Linux/Mac:**
```bash
chmod +x deploy.sh
./deploy.sh
```

The script will:
1. Verify SERVER_IP is configured
2. Prompt for a commit message (optional)
3. Push changes to git
4. SSH into the server
5. Pull latest changes
6. Rebuild and restart the application
7. Show service status

### Option 2: GitHub Actions (Automatic CI/CD)

**⚠️ Security Note:** Store sensitive values as GitHub Secrets, never in code!

1. **Setup Secrets** in GitHub repository settings (`Settings > Secrets and variables > Actions`):
   - `SERVER_IP`: Your server IP address
   - `SERVER_USER`: SSH username (e.g., `root`)
   - `SSH_PRIVATE_KEY`: Your SSH private key (contents of `~/.ssh/id_rsa` or similar)

2. **Automatic Deploy**: Push to `main` branch triggers automatic deployment

3. **Manual Deploy**: Go to `Actions > Deploy to Production > Run workflow`

### Option 3: Manual Commands

```bash
# 1. Push changes
git add .
git commit -m "Your message"
git push

# 2. SSH to server (use your actual server IP)
ssh $SERVER_USER@$SERVER_IP

# 3. Update and restart
cd /app/repo
git pull
docker compose down
docker compose up -d --build
docker compose ps
```

## Environment Variables

Make sure `.env` file exists on the server with required variables:
```env
OLLAMA_HOST=http://ollama:11434
OLLAMA_MODEL=mistral:7b-instruct-v0.3-q4_K_M
OLLAMA_EMBED_MODEL=nomic-embed-text
CHROMA_HOST=chromadb
CHROMA_PORT=8000
APP_PASSWORD=your_password
APP_API_KEY=your_api_key
```

## Verification

After deployment, check (replace with your server IP):
- UI: `http://$SERVER_IP:8501`
- API: `http://$SERVER_IP:8000/docs`
- Health: `http://$SERVER_IP:8000/health`

## Troubleshooting

**Check logs:**
```bash
ssh $SERVER_USER@$SERVER_IP
cd /app/repo
docker compose logs -f streamlit  # UI logs
docker compose logs -f api        # API logs
```

**Restart a specific service:**
```bash
docker compose restart streamlit
```

**Full reset:**
```bash
docker compose down -v
docker compose up -d --build
```

## Rollback

```bash
ssh root@178.104.106.94
cd /app/repo
git log --oneline -5  # Find commit to rollback to
git reset --hard <commit-hash>
docker compose up -d --build
```
