# Deploy (Kaggle / demo)

**Azure (live):** **[AZURE.md](./AZURE.md)** — `https://geneguidelines.genequest.org`, gałąź **`production`**, auto-deploy przez `.github/workflows/deploy-azure.yml`.

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

## Quick demo via Cloudflare (`trycloudflare.com`)

For a temporary public URL without DNS:

```bash
# Stack must listen on host :80 (deploy overlay maps 80:80)
docker compose -f docker-compose.yml -f docker-compose.deploy.yml up -d --build
/tmp/cloudflared tunnel --url http://127.0.0.1:80
```

Use the printed `https://….trycloudflare.com` URL. Limitations:

- **No uptime guarantee** — URL changes every time you restart `cloudflared`.
- **`context canceled` in cloudflared logs** — usually the browser or Cloudflare edge closed a request (timeouts, tab refresh, or many parallel polls). Harmless if the site still loads.
- **`connection refused` on `127.0.0.1:80`** — the **frontend** container is down. Run `docker compose ps`; bring the stack up with `up -d`, not only `restart backend`.
- **During `restart backend`** — expect brief 502/reset errors; wait until `curl -s http://127.0.0.1:8000/health` works **inside** the backend container, and `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/health` on the host returns `200`.
- **`restart` does not rebuild images** — after `git pull`, run `docker compose … up -d --build` so new code (e.g. PubMed pm-1 fixes) is actually in the container.

For jury demos, prefer the VPS IP with basic auth (`http://user:pass@145.x.x.x/`) or a **named** Cloudflare Tunnel; quick tunnels are poor for long SSE streams.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Blank / black page, no UI | HTTP Basic Auth — Arc often skips the prompt on raw IPs. Use `http://demo:PASSWORD@YOUR_HOST:5173/` or Chrome/Safari; confirm `deploy/htpasswd` exists |
| 401 on start research | Remove `GENEGUIDELINES_API_KEY` from `.env` |
| Infinite 401 loop | Check `deploy/htpasswd` exists and is mounted |
| API works without login | Missing `docker-compose.deploy.yml` overlay |
| Empty DB after restart | Used `down -v`; restore from backup |
| cloudflared spam `context canceled` on `/api/agent/run/…` | Overlapping long polls through the tunnel; rebuild frontend after pull (shorter poll timeout + one poll at a time). Ignore if UI updates every ~2s |
| Research stuck / OpenAI 429 on pm-1 | Rebuild backend; ensure `PUBMED_PM1_DETERMINISTIC_RETRIEVAL` is not `0` in `.env` |

## Later (not this deploy)

- Postgres instead of SQLite
- Clerk (or similar) instead of htpasswd
