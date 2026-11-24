# LEVI DEPLOY — exact instructions for the cloud agent

You are provisioning the Levi scripture API on a fresh machine. You have ONE job:
run it and verify it. Do not improve anything. Do not edit the database. Do not
invent flags. Copy the commands exactly, in order, and after each step check that
you see the expected output. If a step's expected output does not appear, STOP,
and paste the last 5 lines you got back to the operator. Never proceed past a
failed step.

---

## Step 0 — before you begin (read once)

1. Everything you need is in this repository, including the database (`levi.db`,
   ~589 MB, stored with Git LFS). You do NOT need to download any other file.
2. There is **NO api key**. This is a public read-only scripture API. No secret
   belongs in this repository or in your commands.
3. This is a server with no desktop. You will use a terminal only.

## Step 1 — install Git LFS + clone this repository

```bash
git clone --depth 1 https://github.com/flowforge-development/levi-deploy.git
cd levi-deploy
sudo apt-get update
sudo apt-get install -y git-lfs
git lfs install
git lfs pull
```

**Check the database is really here:**

```bash
ls -la levi.db
```

**Expected:** a line showing `levi.db` with size around `589000000` bytes. If it
is small (< a few MB) or missing, STOP and paste `git lfs pull` output to the operator.

## Step 2 — install Docker

```bash
sudo apt-get install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
docker version
```

**Expected:** prints a "Client" section and a "Server" section, no error.
If "permission denied", prefix every docker command with `sudo` from now on.

## Step 3 — build and start the container

```bash
docker compose up -d --build
sleep 6
docker compose ps
```

**Expected:** a service named `levi` with status `running` / `Up`. If `Exited` or
`Restarting`, STOP and paste `docker logs levi` to the operator.

## Step 4 — verify the API (run all five, in order; note there is NO key header)

```bash
curl -s http://localhost:8777/health
```

**Expected:** `{"ok": true, "one_api": "scripture-only"}`

```bash
curl -s "http://localhost:8777/verse?ref=Genesis%201:1" | head -c 200
```

**Expected:** JSON starting with `{"id": "Genesis.1.1"` and containing
`"kjv_text": "In the beginning God created the heaven and the earth."`

```bash
curl -s "http://localhost:8777/interlinear?ref=John%201:1" | head -c 200
```

**Expected:** JSON with `"lang": "grc"` and a `"words"` array.

```bash
curl -s "http://localhost:8777/search?q=grace" | head -c 200
```

**Expected:** JSON containing verse results (not an error string).

```bash
curl -s "http://localhost:8777/query?ref=Romans%208:28&caps=text,interlinear,crossref" | head -c 300
```

**Expected:** JSON with `"ref": "Romans 8:28"` and `"text"` and `"interlinear"` keys.

## Step 5 — verify CORS (browsers will call this cross-origin)

```bash
curl -s -I -H "Origin: https://example.com" "http://localhost:8777/health" | grep -i access-control
```

**Expected:** a line containing `Access-Control-Allow-Origin: *`

## Step 6 — report success

When all checks match, paste this exact line to the operator:

```
LEVI LIVE — health ok, verse ok, interlinear ok, search ok, query ok, cors ok.
```

Also paste the machine's public IP (`curl -s ifconfig.me`).

## Optional Step 7 — HTTPS (SKIP unless the operator gives you a domain)

Browsers on an https site cannot call this http endpoint directly. This step is
only done when the operator provides a real domain name. If they do not, SKIP it.

```bash
sudo apt-get install -y caddy
# operator supplies the domain; run as root:
caddy reverse-proxy --from <DOMAIN> --to localhost:8777
```

**Expected:** it prints that it is serving https on `<DOMAIN>`. Then report the
domain to the operator.

---

## If anything fails

- **"levi.db too small"** → Git LFS did not fetch. Run `git lfs install && git lfs pull` again, then `git lfs fsck`.
- **"docker: permission denied"** → use `sudo` in front of every docker command.
- **container exits** → `docker logs levi`, paste the LAST 10 lines to the operator, and change nothing else.

Do not attempt any fix other than the ones listed above. Report, don't improvise.