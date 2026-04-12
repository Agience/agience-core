# Self-hosting guide

Status: **Reference**
Date: 2026-04-01

This guide covers deploying Agience on a single VM or VPS with your own domain. It uses the recommended operator path: prebuilt images, the [`agience-home`](https://github.com/agience/agience-home) starter repo, and Caddy for TLS.

---

## Architecture overview

One server runs:

- Reverse proxy with automatic TLS (Caddy — included in the compose stack)
- Frontend container (React UI)
- Backend container (FastAPI)
- Databases: ArangoDB, OpenSearch
- Object storage: MinIO (S3-compatible, included) or AWS S3 + CloudFront

### Subdomain layout

| Subdomain | Purpose |
|---|---|
| `app.yourdomain.com` | React UI |
| `api.yourdomain.com` | FastAPI backend |
| `content.yourdomain.com` | MinIO / S3 object storage |
| `stream.yourdomain.com` | Astra streaming service (optional) |

---

## 1. Prerequisites

### Server

- Linux VM — Ubuntu 22.04 LTS or later recommended
- Minimum: 4 vCPU, 8 GB RAM (OpenSearch and ArangoDB both need headroom)
- Recommended EC2 equivalent: `t3.large` or larger
- Disk: 60–100 GB (gp3 on AWS; any fast block storage elsewhere)
- Docker and Docker Compose installed

### Domain

- A domain you control
- DNS A records for `app`, `api`, and `content` subdomains pointing to your VM's public IP (add `stream` if you use live streaming)

### Ports

Open these inbound on your firewall or security group:

| Port | Protocol | Purpose |
|---|---|---|
| 80 | TCP | ACME HTTP challenge (Caddy uses this for certificate issuance) |
| 443 | TCP | HTTPS |
| 22 | TCP | SSH (restrict to your IP) |

Keep these ports **private** (loopback / Docker network only — do not expose publicly):

| Port | Service |
|---|---|
| 8081 | Backend API |
| 8529 | ArangoDB |
| 9200, 9600 | OpenSearch |

### OpenSearch kernel setting

OpenSearch requires a higher virtual memory limit than the default Linux kernel allows. Run this on the host before starting the stack:

```bash
sudo sysctl -w vm.max_map_count=262144
```

To make it permanent, add the following line to `/etc/sysctl.conf`:

```
vm.max_map_count=262144
```

---

## 2. Google OAuth setup

Agience uses Google as its primary OAuth provider. The backend is the OAuth client — the frontend does not need a registered redirect URI.

1. Open [Google Cloud Console](https://console.cloud.google.com/) and navigate to **APIs & Services > Credentials**.
2. Click **Create credentials > OAuth 2.0 Client ID**.
3. Set the application type to **Web application**.
4. Under **Authorized redirect URIs**, add:
   ```
   https://api.yourdomain.com/auth/callback
   ```
5. Save and copy the **Client ID** and **Client Secret** — you will need them in the next step.

---

## 3. Environment configuration

The deployment starter includes a `.env.example`. Copy it and fill in the values below.

```bash
cp .env.example .env
```

### Core auth and access

| Variable | Description |
|---|---|
| `ALLOWED_EMAILS` | Comma-separated list of emails allowed to log in, e.g. `you@example.com` |
| `ALLOWED_DOMAINS` | Alternative to `ALLOWED_EMAILS` — allow an entire domain, e.g. `example.com` |

Use either `ALLOWED_EMAILS` or `ALLOWED_DOMAINS`, not both. These are your access gate — set at least one.

### Google OAuth

| Variable | Value |
|---|---|
| `GOOGLE_OAUTH_CLIENT_ID` | Client ID from Google Console |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Client Secret from Google Console |
| `GOOGLE_OAUTH_REDIRECT_URI` | `https://api.yourdomain.com/auth/callback` |

### URL wiring

These values drive CORS policy, OAuth redirect validation, and frontend API routing. They must match your actual public domains exactly.

| Variable | Value |
|---|---|
| `FRONTEND_URI` | `https://app.yourdomain.com` |
| `BACKEND_URI` | `https://api.yourdomain.com` |
| `VITE_BACKEND_URI` | `https://api.yourdomain.com` |
| `VITE_CLIENT_ID` | `agience-client` |

The `VITE_*` variables are injected into the running frontend container at startup — they are not baked into the published image.

### Databases

| Variable | Value |
|---|---|
| `ARANGO_ROOT_PASSWORD` | Strong random password |
| `OPENSEARCH_INITIAL_ADMIN_PASSWORD` | Strong random password |
| `OPENSEARCH_USERNAME` | `admin` |
| `OPENSEARCH_PASSWORD` | Same value as `OPENSEARCH_INITIAL_ADMIN_PASSWORD` |

### OpenAI

| Variable | Value |
|---|---|
| `OPENAI_API_KEY` | Your OpenAI API key (required for embeddings and LLM features) |

### Content storage — MinIO (recommended for self-hosting)

The host starter includes a MinIO container for fully self-contained object storage. The backend needs an internal URL (Docker network) and the browser needs a public URL — these are different values.

| Variable | Value |
|---|---|
| `MINIO_ROOT_USER` | `agience` |
| `MINIO_ROOT_PASSWORD` | Strong random password |
| `CONTENT_BUCKET` | `agience-content` |
| `CONTENT_URI` | `https://content.yourdomain.com` |
| `AWS_ACCESS_KEY_ID` | Same as `MINIO_ROOT_USER` |
| `AWS_SECRET_ACCESS_KEY` | Same as `MINIO_ROOT_PASSWORD` |
| `AWS_REGION` | `us-east-1` (MinIO ignores this value; boto3 requires one) |
| `AWS_ENDPOINT_URL_INTERNAL` | `http://content:9000` |
| `AWS_ENDPOINT_URL_PUBLIC` | `https://content.yourdomain.com` |

### Reverse proxy domains (Caddy)

| Variable | Value |
|---|---|
| `DOMAIN` | `app.yourdomain.com` |
| `API_DOMAIN` | `api.yourdomain.com` |

---

## 4. Deploy with Docker Compose

The recommended path is to use the deployment starter directly. It pulls prebuilt images — no source checkout required.

```bash
# 1. Clone the host starter repo
git clone https://github.com/agience/agience-home.git /srv/agience
cd /srv/agience

# 2. Create your .env from the example
cp .env.example .env
# Fill in all values from section 3 above

# 3. Create the keys directory
mkdir -p keys

# 4. Pull images and start
docker compose pull
docker compose up -d
```

On first start, the backend initialises all database schemas automatically. This takes 30–60 seconds. The stack is ready when the backend health endpoint responds (see section 7).

---

## 5. Configure the reverse proxy (Caddy)

Caddy is included in the host starter's compose stack and handles TLS automatically via Let's Encrypt. If your DNS A records are set correctly and ports 80 and 443 are open, no manual certificate management is needed.

The starter includes a `Caddyfile` pre-configured to route `app.*` to the frontend container and `api.*` to the backend container. The `DOMAIN` and `API_DOMAIN` variables in `.env` are read by the Caddyfile at startup.

To expose the content endpoint (`content.yourdomain.com`), extend the Caddyfile with a proxy block pointing to the MinIO container on port 9000.

### Alternative: Nginx

If you prefer Nginx over Caddy, install it alongside Certbot and use the following configuration. This is not the recommended path, but it remains supported.

Install dependencies:

```bash
sudo apt-get update
sudo apt-get install -y nginx certbot python3-certbot-nginx
```

Create `/etc/nginx/sites-available/api.yourdomain.com`:

```nginx
server {
  server_name api.yourdomain.com;

  location / {
    proxy_pass http://127.0.0.1:8081;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 3600;
  }
}
```

Create `/etc/nginx/sites-available/app.yourdomain.com`:

```nginx
server {
  server_name app.yourdomain.com;

  root /var/www/agience/app/dist;
  index index.html;

  location / {
    try_files $uri $uri/ /index.html;
  }
}
```

Enable sites and obtain TLS certificates:

```bash
sudo ln -s /etc/nginx/sites-available/api.yourdomain.com /etc/nginx/sites-enabled/
sudo ln -s /etc/nginx/sites-available/app.yourdomain.com /etc/nginx/sites-enabled/
sudo certbot --nginx -d api.yourdomain.com -d app.yourdomain.com
sudo nginx -t && sudo systemctl reload nginx
```

---

## 6. DNS and TLS

### DNS records

Create A records (or AAAA for IPv6) at your DNS provider:

| Record | Points to |
|---|---|
| `app.yourdomain.com` | VM public IP |
| `api.yourdomain.com` | VM public IP |
| `content.yourdomain.com` | VM public IP |
| `stream.yourdomain.com` | VM public IP (optional) |

DNS propagation typically takes a few minutes with a short TTL, but can take up to 24–48 hours at some providers. Caddy will not successfully obtain a certificate until DNS resolves to your server.

### TLS certificate issuance (Caddy)

Caddy uses the ACME HTTP-01 challenge. When the stack starts, Caddy contacts Let's Encrypt over port 80 to prove ownership of each domain in `DOMAIN` and `API_DOMAIN`, then stores the certificates in a Docker volume. Renewal is automatic.

If certificate issuance fails, check:

- Port 80 is open inbound on the firewall
- DNS A records are already propagated and resolve to the correct IP
- The `DOMAIN` and `API_DOMAIN` values in `.env` exactly match the DNS records

---

## 7. First-run verification

Once the stack is up and DNS is propagated, run through these checks:

| Check | What to do |
|---|---|
| Backend health | Open `https://api.yourdomain.com/version` — expect a JSON version response |
| API docs | Open `https://api.yourdomain.com/docs` — expect the Swagger UI |
| App loads | Open `https://app.yourdomain.com/` — expect the Agience login page |
| Login flow | Click login → redirected to Google → returns to the app |
| Upload test | Upload a small file inside the app — validates S3/MinIO presigned URL flow |

All five checks should pass before considering the deployment healthy.

---

## 8. Troubleshooting

### "Invalid redirect_uri" on login

The OAuth redirect allowlist is built from `FRONTEND_URI` and `BACKEND_URI`. Any mismatch — including a trailing slash or wrong protocol — will cause this error.

- Confirm `FRONTEND_URI=https://app.yourdomain.com` (no trailing slash)
- Confirm `BACKEND_URI=https://api.yourdomain.com` (no trailing slash)
- Confirm `VITE_BACKEND_URI` matches `BACKEND_URI`

### Google OAuth error: "redirect_uri_mismatch"

- Confirm that `https://api.yourdomain.com/auth/callback` is listed under **Authorized redirect URIs** in Google Cloud Console
- Confirm `GOOGLE_OAUTH_REDIRECT_URI` in `.env` matches exactly

### WebSockets not connecting / live updates broken

This symptom usually appears when Nginx strips the upgrade headers.

- Confirm the Nginx `api.*` config includes `proxy_set_header Upgrade $http_upgrade` and `proxy_set_header Connection "upgrade"`
- Confirm the proxy does not strip query parameters — the WebSocket auth token is passed as `?token=...`

### Uploads fail

- Confirm MinIO (or S3) credentials in `.env` are correct
- Confirm the bucket exists (`agience-content` or whatever you set in `CONTENT_BUCKET`)
- Confirm `AWS_ENDPOINT_URL_PUBLIC` is a URL the browser can reach (presigned URLs use this hostname)
- If using MinIO, confirm `content.yourdomain.com` resolves and the Caddy or Nginx proxy is routing to port 9000

### OpenSearch crashes on startup

Run the kernel tuning command on the host:

```bash
sudo sysctl -w vm.max_map_count=262144
```

Then add `vm.max_map_count=262144` to `/etc/sysctl.conf` so it survives a reboot.

### Backend is slow to start

On first boot, the backend initialises ArangoDB schemas and waits for all services to become healthy. Allow 60-90 seconds. Check `docker compose logs backend` if it does not come up.

### Upgrading to AWS S3 + CloudFront

If you later move from MinIO to AWS-native storage:

- Remove or ignore the MinIO container
- Set `CONTENT_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_REGION`
- Set `CONTENT_URI` to your CloudFront distribution domain
- Remove `AWS_ENDPOINT_URL_INTERNAL` and `AWS_ENDPOINT_URL_PUBLIC`

CloudFront provides global edge caching, origin shielding, and signed URL features. In self-host mode with MinIO, browser caching handles private content adequately for single-operator use. Add Cloudflare in front of `content.*` if edge performance matters.

---

## See also

- [Deploy to EC2](deploy-ec2.md) — step-by-step for AWS-specific setup including IAM, security groups, and EBS
- [Admin setup](admin-setup.md) — first-login provisioning, seed data, and operator configuration
- [Local development](../getting-started/local-development.md) — running the stack locally for development and testing
