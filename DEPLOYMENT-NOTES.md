# Levi deployment notes

Updated: 2026-11-24

## What is running

- Repo: `/root/levi-deploy` (GitHub `flowforge-development/levi-deploy`; local commits on top of upstream `e66aa28`)
- Container: `levi`, built from `Dockerfile`, `restart: always`, healthcheck every 60s.
  Published only on `127.0.0.1:8777`.
- Caddy (systemd, enabled at boot): terminates TLS on `:80`/`:443` and proxies to
  `127.0.0.1:8777`. Config: `/etc/caddy/Caddyfile` (also tracked as `Caddyfile`).
- TLS origin: `https://45-76-62-73.sslip.io` (Let's Encrypt, auto-renews)
- Front door: `https://levi-deploy.vercel.app` (Vercel project `connect-4866/levi-deploy`)
- Database: `levi.db`, 588,681,216 bytes, SHA-256
  `dc4fd7aad1a15636e981697f10f7cfc7e7c0ff863841bf4e83eb0365084159c0`, mounted
  read-only at `/data/levi.db`
- Auth: `LEVI_API_KEY` in `/root/levi-deploy/.env` (mode 600, gitignored). Required on
  every endpoint except `GET/HEAD /health` and CORS `OPTIONS`.
- Ritual integration values live in the `connect-4866/ritual` Vercel project
  (Production): `LEVI_API_URL`, `LEVI_MCP_URL`, `LEVI_API_KEY`. They take effect on
  Ritual's next deployment.

Request path: browser -> `https://levi-deploy.vercel.app` -> Vercel rewrite ->
`https://45-76-62-73.sslip.io` (Caddy TLS) -> `127.0.0.1:8777` (container).

`vercel.json` is committed in this repo, so a future Git deployment of this repo on
Vercel still produces a working proxy.

```json
{
  "rewrites": [
    { "source": "/(.*)", "destination": "https://45-76-62-73.sslip.io/$1" }
  ]
}
```

Redeploy the proxy when config changes or the edge cache must be cleared:

```bash
cd /root/levi-vercel
vercel deploy --prod --project levi-deploy --yes --force
```

Rebuild / restart the API after code or key changes:

```bash
cd /root/levi-deploy
docker compose up -d --build --force-recreate
docker compose ps
curl -s http://127.0.0.1:8777/health
```

Caddy:

```bash
systemctl status caddy
caddy validate --config /etc/caddy/Caddyfile
journalctl -u caddy -n 50
# after editing /root/levi-deploy/Caddyfile:
#   cp /root/levi-deploy/Caddyfile /etc/caddy/Caddyfile && systemctl reload caddy
```

If the VM's public IP changes, update the sslip.io hostname in `/root/levi-deploy/Caddyfile`,
`/etc/caddy/Caddyfile`, and `vercel.json`, then reload Caddy and redeploy Vercel.

## Authentication

```bash
KEY=$(cut -d= -f2- /root/levi-deploy/.env)
curl -H "Authorization: Bearer $KEY" https://levi-deploy.vercel.app/verse?ref=John%203:16
```

- The key is checked at the origin, so TLS-origin access and Vercel access both require it.
- Vercel forwards the `Authorization` header; verified with curl and the official MCP SDK.
- Authenticated GET responses use `Cache-Control: private` plus `Vary: Authorization`,
  so Vercel's shared edge cache cannot serve data to an unauthenticated caller.
- `401` responses are `no-store` and include `WWW-Authenticate: Bearer realm="levi"`.
- `/health` is intentionally public and `no-store` so Docker and uptime probes work.
- **Never ship the key in browser code.** It belongs only in Ritual's server routes
  (Next.js route handlers / server actions) or another trusted backend.

Rotate the key:

```bash
cd /root/levi-deploy
NEW="levi_sk_$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')"
printf 'LEVI_API_KEY=%s\n' "$NEW" > .env && chmod 600 .env
docker compose up -d --force-recreate
# update Ritual's Vercel secret, then redeploy Ritual:
# printf '%s' "$NEW" | vercel env add LEVI_API_KEY production --project ritual --type secret --force --yes
```

## Ritual integration

The Ritual browser app must call its own Next.js API routes. Those server routes call
Levi with the secret; the key never reaches the client.

```ts
// app/api/study/route.ts (server only)
const base = process.env.LEVI_API_URL!;
const key = process.env.LEVI_API_KEY!;

const res = await fetch(`${base}/study?q=${encodeURIComponent(query)}&limit=6`, {
  headers: { Authorization: `Bearer ${key}` },
});
const bundle = await res.json();
// bundle.sources -> citations / context panels
// bundle.prompt  -> send to Ritual's model as the grounded system context
```

For a chat loop, use `POST /mcp` with the same `Authorization` header and an MCP client
library, or call `/query`, `/verse`, `/context`, `/interlinear`, `/crossref` directly.
The MCP tool descriptions carry the "how to use it well" guidance; the `/study` prompt
carries the same rules in one string.

## Endpoints

All require `Authorization: Bearer <key>` except `/health`.

| Endpoint | Purpose |
|---|---|
| `GET /query?ref=Romans 8:28&caps=text,interlinear,crossref` | Combined verse payload |
| `GET /verse?ref=John 3:16` | Text, translations, words, cross-refs, topics |
| `GET /interlinear?ref=John 1:1` | Original-language tokens |
| `GET /context?ref=John 3:16` | Layered study context |
| `GET /search?q=grace&limit=20` | Full-text search |
| `GET /crossref?ref=Rom 8:28` | Cross-reference trails |
| `GET /word?q=H7307`, `/topic?q=grace`, `/commentary?ref=...` | Lexicon / topics / commentary |
| `GET /study?q=living water&limit=6` | Grounded sources + ready-to-use LLM prompt |
| `GET /study?ref=Romans 8:28` | Same, anchored to one passage |
| `GET /random`, `/stats`, `/books`, `/doctor` | Utilities (random is `no-store`) |
| `POST /mcp` | MCP streamable HTTP, stateless JSON-RPC |

The MCP endpoint exposes 18 read-only tools. `levi_backup` is withheld because it
writes files on the host. The official MCP Python SDK (`mcp` 2.3.0) was used to verify
initialize, tools/list, and tools/call through the Vercel URL with the key header.

## Desktop agent access

REST base URL: `https://levi-deploy.vercel.app`

Remote MCP (streamable HTTP, stateless): `https://levi-deploy.vercel.app/mcp`

Header for both: `Authorization: Bearer <LEVI_API_KEY>`

- Clients with native HTTP MCP support: use the URL above plus the header.
- Claude Code:

```bash
claude mcp add --transport http levi https://levi-deploy.vercel.app/mcp \
  --header "Authorization: Bearer $LEVI_API_KEY"
```

- stdio-only clients via `mcp-remote`:

```json
{
  "mcpServers": {
    "levi": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote",
        "https://levi-deploy.vercel.app/mcp",
        "--header", "Authorization: Bearer <LEVI_API_KEY>"
      ]
    }
  }
}
```

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
   protocol-version echo are handled.
5. Added `GET /study` (grounded sources + ready prompt) for Ritual's server-side AI.
6. Added bearer auth (`LEVI_API_KEY`) with constant-time comparison, `/health`
   exemption, `Vary: Authorization`, and private caching for authenticated data.
7. Cache policy hardened: `/health`, `/random`, `/sefaria`, `/doctor`, `/study`,
   all error responses, and MCP are `no-store`.
8. Hardened transport: Docker now binds `127.0.0.1:8777` only; Caddy terminates TLS
   on `:80`/`:443` (`45-76-62-73.sslip.io`, Let's Encrypt); the Vercel rewrite goes
   over HTTPS. The API key never crosses a plaintext public link.

## Important constraints

- **Single service key, not per-user keys.** Levi intentionally has no user model
  ("the brain lives in Ritual"). Ritual authenticates users and calls Levi with this
  one server-side key. If per-user quotas/revocation are needed later, add a key
  table or let Ritual sign short-lived JWTs; do not give each browser a static key.
- **Fresh clones need `.env`.** `docker-compose.yml` requires `LEVI_API_KEY` via
  `${LEVI_API_KEY:?...}`, so a clone without `.env` won't start. Create the file or
  export the variable before `docker compose up`.
- **IP change procedure.** If the public IP changes: update the sslip.io hostname in
  `/root/levi-deploy/Caddyfile`, `/etc/caddy/Caddyfile`, and `vercel.json`; reload
  Caddy; redeploy Vercel. Certificate issuance for the new name is automatic.
- **Database is pristine.** Do not call write paths against `/root/levi-deploy/levi.db`.
  `/sefaria` is safe now; `levi_backup` and the CLI write paths are not exposed
  remotely.
- `ufw` is active: 22, 80, 443 allowed. Port 8777 is not published externally; the
  only path to the container is through Caddy on loopback.

## Useful checks

```bash
docker compose ps
docker logs levi --tail 20
docker stats --no-stream levi
systemctl is-active caddy && systemctl is-enabled caddy
git -C /root/levi-deploy status --short
sha256sum /root/levi-deploy/levi.db
ss -ltnp | grep -E ':(80|443|8777)\b'
```

If `levi.db` is ever replaced by a 134-byte pointer, restore it with:

```bash
cd /root/levi-deploy
git lfs install
git lfs pull
# or: rm levi.db && git checkout -- levi.db
```
