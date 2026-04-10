# Deployment Guide - Interactive Compliance Graph Visualization

## Architecture Overview

The application consists of two main components:
1. **Frontend**: Next.js application (port 3000)
2. **Backend**: FastAPI application (port 8000)

## Prerequisites

- Node.js v20+ (for Next.js frontend)
- Python 3.11+ (for FastAPI backend)
- Nginx (for reverse proxy)
- PM2 (optional, for process management)
- Docker (for Ollama + ChromaDB, already configured)

## Backend Setup (Already Running)

The FastAPI backend is already configured and should be running via Docker Compose:

```bash
cd /path/to/rag-chatbot-production
docker-compose up -d
```

Verify backend is running:
```bash
curl http://localhost:8000/health
```

## Frontend Setup

### 1. Install Dependencies

```bash
cd frontend
npm install
```

### 2. Build for Production

```bash
npm run build
```

### 3. Start Production Server

**Option A: Using npm directly**
```bash
npm run start
```

**Option B: Using PM2 (recommended)**
```bash
npm install -g pm2
pm2 start npm --name "compliance-viz-frontend" -- start
pm2 save
pm2 startup  # Follow instructions to enable auto-start
```

### 4. Development Mode

For local development:
```bash
npm run dev
```

## Nginx Configuration

### 1. Install Nginx

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install nginx

# macOS
brew install nginx
```

### 2. Configure Reverse Proxy

Copy the nginx configuration:
```bash
sudo cp nginx-compliance-viz.conf /etc/nginx/sites-available/compliance-viz
sudo ln -s /etc/nginx/sites-available/compliance-viz /etc/nginx/sites-enabled/
```

Edit the configuration to replace `your-domain.com` with your actual domain:
```bash
sudo nano /etc/nginx/sites-available/compliance-viz
```

### 3. Test and Reload Nginx

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## Health Checks

The application exposes health check endpoints:

- **Backend**: `http://localhost:8000/health`
- **Frontend**: `http://localhost:3000` (Next.js built-in)
- **Nginx proxied**: `http://your-domain.com/health`

## PM2 Process Management (Recommended)

### Install PM2

```bash
npm install -g pm2
```

### Create PM2 Ecosystem File

Create `ecosystem.config.js` in the project root:

```javascript
module.exports = {
  apps: [
    {
      name: 'compliance-viz-frontend',
      cwd: './frontend',
      script: 'npm',
      args: 'start',
      env: {
        NODE_ENV: 'production',
        PORT: 3000
      }
    }
  ]
};
```

### Manage Processes

```bash
# Start all processes
pm2 start ecosystem.config.js

# View status
pm2 status

# View logs
pm2 logs

# Restart
pm2 restart all

# Stop
pm2 stop all

# Save configuration
pm2 save

# Setup auto-start on boot
pm2 startup
```

## Environment Variables

### Frontend (.env.local)

```bash
# Not strictly needed if using next.config.js rewrites
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Backend (.env)

Already configured in the main project. Key variables:
- `OLLAMA_HOST`: Ollama API endpoint
- `CHROMA_URL`: ChromaDB endpoint
- `OLLAMA_MODEL`: LLM model for analysis
- `APP_API_KEY`: Optional API authentication

## Monitoring

### Application Logs

**Frontend (PM2)**:
```bash
pm2 logs compliance-viz-frontend
```

**Backend**:
```bash
docker-compose logs -f api
```

**Nginx**:
```bash
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log
```

### Performance Monitoring

For 100-node graphs, monitor:
- Frontend rendering time: Target <100ms for filter operations
- Backend graph extraction: ~30-60s depending on document size
- Memory usage: ~500MB for Next.js, ~2GB for FastAPI + Ollama

## Troubleshooting

### Frontend won't start

```bash
cd frontend
rm -rf .next node_modules
npm install
npm run build
npm start
```

### API requests fail (CORS)

Check that `next.config.js` rewrites are configured:
```javascript
async rewrites() {
  return [
    {
      source: '/api/:path*',
      destination: 'http://localhost:8000/:path*',
    },
  ]
}
```

### Graph rendering issues

Ensure `react-force-graph-2d` is properly installed:
```bash
npm install react-force-graph-2d
```

### Large DAT documents timeout

Increase nginx timeouts in `nginx-compliance-viz.conf`:
```nginx
proxy_read_timeout 600s;
```

## Production Checklist

- [ ] Backend health check returns `200 OK`
- [ ] Frontend builds without errors (`npm run build`)
- [ ] Nginx configuration tested (`sudo nginx -t`)
- [ ] PM2 processes running (`pm2 status`)
- [ ] Health endpoints accessible via domain
- [ ] Upload and graph extraction tested end-to-end
- [ ] SSL/TLS configured (use certbot for Let's Encrypt)

## SSL/TLS Configuration (Production)

For HTTPS in production:

```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal is configured by default
# Verify with:
sudo certbot renew --dry-run
```

## Scaling Considerations

For larger deployments:
- Consider deploying Ollama on separate GPU server
- Use Redis for caching compliance scores
- Implement rate limiting in nginx
- Add load balancer if running multiple frontend instances

## Support

For issues or questions, refer to:
- Backend: `/src/api/main.py`
- Frontend: `/frontend/app/page.tsx`
- Graph logic: `/frontend/components/ComplianceGraph.tsx`
