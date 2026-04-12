# Deploy to AWS EC2 (Minimal Effort)

Status: **Reference**
Date: 2026-04-01

This is the simplest path to get Agience running on an EC2 VM with your own domain.

---

## Recommended minimal architecture (single instance)

One EC2 instance runs:

- Caddy (TLS termination + reverse proxy)
- Frontend container
- Backend stack (ArangoDB, OpenSearch, API)
- MinIO (S3-compatible content storage)

Domains (recommended):

- `app.yourdomain.com` → UI
- `api.yourdomain.com` → FastAPI
- `content.yourdomain.com` → MinIO S3 endpoint (used by presigned URLs)

---

## 1) Create the EC2 instance

- Instance type: `t3.large` is a reasonable starting point (OpenSearch + multiple DBs on one box needs RAM)
- Disk: 60–100GB gp3 to start
- OS: Ubuntu 22.04 LTS or 24.04 LTS
- Attach an Elastic IP (optional but recommended)

### Security Group

Inbound:
- 80/tcp (HTTP, used for ACME challenge → Caddy redirects to 443)
- 443/tcp (HTTPS)

Optional (lock down to your IP if you want admin access):
- 22/tcp (SSH)

Do **not** expose DB/search ports publicly.

---

## 2) DNS

Create A records pointing to the instance public IP:

- `app` → EC2 IP
- `api` → EC2 IP
- `content` → EC2 IP

---

## 3) Install Docker on the instance

SSH into the instance and install Docker + Compose plugin.

(You can use your preferred method; the key requirement is `docker compose` works.)

### OpenSearch prerequisite (important)

OpenSearch commonly requires a higher Linux virtual memory map limit.

If the `search` container fails early, set on the EC2 host:

- `sudo sysctl -w vm.max_map_count=262144`

To persist across reboots, add to `/etc/sysctl.conf`.

---

## 4) Put the app on the server

Two minimal options:

### Preferred path: deployment-only host repo

- clone the [`agience-home`](https://github.com/agience/agience-home) starter repo onto the instance
- place a real `.env` alongside it
- run `docker compose pull && docker compose up -d`

### Alternative path: clone this repo on the server

This is still possible for experimentation, but it is no longer the preferred self-host story.

---

## 5) Create the `.env` on the instance

Start from `.env.example` and fill in the required values.

Minimum values for self-host (example):

- Domains:
  - `DOMAIN=app.yourdomain.com`
  - `API_DOMAIN=api.yourdomain.com`

- OAuth:
  - `GOOGLE_OAUTH_CLIENT_ID=...`
  - `GOOGLE_OAUTH_CLIENT_SECRET=...`
  - `GOOGLE_OAUTH_REDIRECT_URI=https://api.yourdomain.com/auth/callback`

- CORS / allowlists:
  - `FRONTEND_URI=https://app.yourdomain.com`
  - `BACKEND_URI=https://api.yourdomain.com`
  - `ALLOWED_EMAILS=you@example.com` (or `ALLOWED_DOMAINS=example.com`)

- Frontend runtime config:
  - `VITE_BACKEND_URI=https://api.yourdomain.com`
  - `VITE_CLIENT_ID=agience-client`

These values are read by the running frontend container at startup. They are not build args for the published frontend image.

- Secrets:
  - `ARANGO_ROOT_PASSWORD=...`
  - `OPENSEARCH_INITIAL_ADMIN_PASSWORD=...`
  - `OPENSEARCH_USERNAME=admin`
  - `OPENSEARCH_PASSWORD=<same as OPENSEARCH_INITIAL_ADMIN_PASSWORD>`

- Content (MinIO):
  - `MINIO_ROOT_USER=agience`
  - `MINIO_ROOT_PASSWORD=...`
  - `CONTENT_BUCKET=agience-content`
  - `CONTENT_URI=https://content.yourdomain.com`
  - `AWS_ACCESS_KEY_ID=<same as MINIO_ROOT_USER>`
  - `AWS_SECRET_ACCESS_KEY=<same as MINIO_ROOT_PASSWORD>`
  - `AWS_REGION=us-east-1`
  - `AWS_ENDPOINT_URL_INTERNAL=http://content:9000`
  - `AWS_ENDPOINT_URL_PUBLIC=https://content.yourdomain.com`

---

## 6) Start the stack

On the instance, from the host repo:

- `docker compose pull`
- `docker compose up -d`

---

## 7) Verify

- `https://api.yourdomain.com/version`
- `https://api.yourdomain.com/docs`
- `https://app.yourdomain.com/` (login should complete)
- Upload a small file (validates MinIO + presigned URLs)

---

## Migrating to AWS-native content (S3 + CloudFront)

The default EC2 path uses MinIO for fully self-contained object storage. If you later want to move to AWS-native S3 and CloudFront, the changes are confined to environment variables:

- Remove or disable the MinIO container
- Set `CONTENT_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`
- Set `CONTENT_URI` to your CloudFront distribution domain
- Remove `AWS_ENDPOINT_URL_INTERNAL` and `AWS_ENDPOINT_URL_PUBLIC`

CloudFront provides global edge caching and origin shielding. For most single-operator self-hosted installs MinIO is sufficient.
