# GeneGuidelines — Documentation

Living clinical guidelines for rare genetic diseases, generated and kept current by a controlled AI workflow over PubMed evidence. Built by the **GeneQuest Foundation**.

## Contents

| File | Topic |
|------|-------|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | System overview: flow engine, executors, MCP integration, SSE traces, structured output |
| [`ROADMAP.md`](ROADMAP.md) | Executive engineering roadmap — what's clean, what's debt, three-phase migration plan, OSS library horizon |
| [`ENGINEERING_VISION.md`](ENGINEERING_VISION.md) | Full technical vision (~3000 lines): current-state synthesis, patterns for new components, GG → Research Canvas migration map, quality tooling roadmap, risks |
| [`adr/001-dual-frontend-subdomain-deploy.md`](adr/001-dual-frontend-subdomain-deploy.md) | Why we run `frontend-public` and `frontend-admin` separately |
| [`../backend/README.md`](../backend/README.md) | Backend folder layout — current state vs target module-first structure |

For setup, environment variables, and dev commands, start at the repo-root [`README.md`](../README.md) and [`CLAUDE.md`](../CLAUDE.md).
