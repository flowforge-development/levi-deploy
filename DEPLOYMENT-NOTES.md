# Levi deployment notes

Updated: 2026-11-24

## What is running

- Repo: `/root/levi-deploy` (GitHub `flowforge-development/levi-deploy`; local commit `3404396` on top of upstream `e66aa28`)
- Container: `levi`, built from `Dockerfile`, `restart: always`, healthcheck every 60s
- Origin: `http://45.76.62.73:8777` (public)
- HTTPS front door: `https://levi-deploy.vercel.app` (Vercel project `connect-4866/levi-deploy`)
- Database: `levi.db`, 588,681,216 bytes, SHA-256
  `dc4fd7aad1a15636e981697f10f7cfc7e7c0ff863841bf4e83eb0365084159c0`, mounted
  read-only at `/data/levi.db`
- Container uses ~440 MB RAM; host has 3.8 GB. DB index/edge cache warms on first hit.

Vercel config lives outside the repo at `/root/levi-vercel/vercel.json`:

```json
{
  "rewrites": [
    { "source": "/(.*)", "destination": "http://45.76.62.73:8777/$1" }
  ]
}
```

Redeploy the proxy when the origin IP changes:

```bash
cd /root/levi-vercel
vercel deploy --prod --project levi-deploy --yes
```

Rebuild / restart the API after code changes:

```bash
cd /root/levi-deploy
docker compose up -d --build --force-recreate
docker compose ps
curl -s http://localhost:8777/doctor | python3 -m json.tool
```

## Verification

```bash
curl -s https://levi-deploy.vercel.app/health
curl -s "https://levi-deploy.vercel.app/verse?ref=Genesis%201:1"
curl -s "https://levi-deploy.vercel.app/interlinear?ref=John%201:1"
curl -s "https://levi-deploy.vercel.app/search?q=grace&limit=3"
curl -s "https://levi-deploy.vercel.app/query?ref=Romans%208:28&caps=text,interlinear,crossref"
curl -sI https://levi-deploy.vercel.app/health | grep -i access-control
```

## Desktop agent access

REST base URL: `https://levi-deploy.vercel.app`

Remote MCP (streamable HTTP, stateless): `https://levi-deploy.vercel.app/mcp`

- Clients with native HTTP MCP support: use the URL above.
- Claude Code: `claude mcp add --transport http levi https://levi-deploy.vercel.app/mcp`
- stdio-only clients (Claude Desktop JSON config, etc.):

```json
{
  "mcpServers": {
    "levi": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://levi-deploy.vercel.app/mcp"]
    }
  }
}
```

The remote endpoint exposes 18 read-only tools. `levi_backup` is withheld because
it writes files on the host. The official MCP Python SDK (`mcp` 2.3.0) was used to
verify initialize, tools/list, and tools/call through the Vercel URL.

## Fixes applied on top of upstream `e66aa28`

1. `/random` returned `{}`. `random_verse()` passed an internal id (`Ezra.2.5`)
   to `get_verse()`, which expects `Ezra 2:5`. It now selects book/chapter/verse
   and builds a human reference.
2. `HEAD` returned 501. Added `do_HEAD`, and `_send` now omits the body for HEAD.
   The README's CORS check (`curl -I`) works now.
3. `/sefaria` failed on the read-only DB when caching was attempted. It now
   returns fetched commentary under `texts` without caching when SQLite reports
   `attempt to write a readonly database`.
4. Added `POST /mcp` (JSON-RPC, stateless streamable HTTP) so a desktop MCP agent
   can use the DB over HTTPS. Batches, notifications (202), CORS preflight, and
   protocol-version echo are handled. `LEVI_API_KEY`, if ever set, is enforced on
   MCP POST too.
5. Cache policy hardened: `/health`, `/random`, `/sefaria`, `/doctor` and all
   error responses are `no-store`. Scripture reads stay publicly cacheable.

## Important constraints

- **No API key.** The API is intentionally public read-only. To lock it, set
  `LEVI_API_KEY` in `docker-compose.yml`, recreate the container, and send
  `Authorization: Bearer <key>` from the agent. The Vercel edge does not add auth
  headers; the key is checked at the origin, including direct-IP access.
- **Vercel -> origin is plain HTTP.** Fine for public scripture data; do not put
  secrets in query strings or headers on this path.
- **Git integration hazard.** The Vercel project is connected to the GitHub repo
  but the repo has no `vercel.json`. A push to `main` will trigger a Git
  deployment that replaces the proxy with a 404. Either disconnect the Git
  integration (`vercel git disconnect`) or add the rewrite above to the repo
  before pushing.
- **Database is pristine.** Do not call write paths against `/root/levi-deploy/levi.db`.
  `/sefaria` is safe now; `levi_backup` and the CLI write paths are not exposed
  remotely.
- `ufw` is active, but Docker publishes port 8777 past it. The origin is reachable
  directly at the public IP; this is expected.

## Useful checks

```bash
docker compose ps
docker logs levi --tail 20
docker stats --no-stream levi
systemctl is-enabled docker
git -C /root/levi-deploy status --short
sha256sum /root/levi-deploy/levi.db
```

If `levi.db` is ever replaced by a 134-byte pointer, restore it with:

```bash
cd /root/levi-deploy
git lfs install
git lfs pull
# or: rm levi.db && git checkout -- levi.db
```
