# Deploy (Kaggle / demo)

Minimal stack: **Docker Compose + HTTP Basic Auth** on the whole site (public, admin, API). SQLite on the existing `sqlite-data` volume.

## Prerequisites

- VPS with Docker Compose v2 (Hetzner, DigitalOcean, etc.)
- Repo root `.env`: `cp backend/.env.example .env` then set **one** LLM profile, e.g.:
  - `MODEL_PROFILE=openrouter` and `OPENROUTER_API_KEY=sk-or-...`
  - `MODEL_PROFILE=production` and `OPENAI_API_KEY=sk-...`
  - `MODEL_PROFILE=vllm`, `LLM_API_KEY`, `LLM_BASE_URL` (on VPS use the real gateway URL; locally in Docker use `http://host.docker.internal:PORT/v1` instead of `127.0.0.1`)
- **Do not** set `GENEGUIDELINES_API_KEY` for this demo — otherwise `/api/pipeline/guideline-run` returns 401

## 1. Password file

On the server (install `apache2-utils` or use `htpasswd` from any Apache package):

```bash
htpasswd -c deploy/htpasswd demo
# More users (do not use -c again):
htpasswd deploy/htpasswd colleague
```

`deploy/htpasswd` is gitignored — share passwords out of band with reviewers.

## 2. Start

```bash
docker compose -f docker-compose.yml -f docker-compose.deploy.yml up -d --build
```

- Public site: host port **5173** → container :80  
- Admin: host port **5174** → container :81  
- Backend is **not** published on :8000 (API only via nginx `/api/`)

Local dev without auth:

```bash
docker compose up --build
```

## 3. HTTPS (on the VPS, not in this repo)

Point DNS at the server, then e.g. Caddy or Certbot in front of ports 5173/5174, or map 80/443 to those ports in your firewall/reverse proxy.

Open **only** 80/443 (or your proxy ports) — not 8000.

## 4. Data safety

- SQLite lives in Docker volume `sqlite-data` (`DB_PATH=/data/tickets.db`).
- **Never** run `docker compose down -v` on production (deletes the DB).
- Before upgrades: copy the volume or stop containers and backup `/var/lib/docker/volumes/.../sqlite-data`.

## 5. Smoke test (video / jury)

After browser login (basic auth prompt):

1. Open public site → pick a disease → **upload** a document (private context).
2. **Start research** → custom disease name → confirm run starts and trace/progress loads.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Blank / black page, no UI | HTTP Basic Auth — Arc often skips the prompt on raw IPs. Use `http://demo:PASSWORD@YOUR_HOST:5173/` or Chrome/Safari; confirm `deploy/htpasswd` exists |
| 401 on start research | Remove `GENEGUIDELINES_API_KEY` from `.env` |
| Infinite 401 loop | Check `deploy/htpasswd` exists and is mounted |
| API works without login | Missing `docker-compose.deploy.yml` overlay |
| Empty DB after restart | Used `down -v`; restore from backup |

## Later (not this deploy)

- Postgres instead of SQLite
- Clerk (or similar) instead of htpasswd
