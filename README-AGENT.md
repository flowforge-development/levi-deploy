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
   ~589 MB, stored with Git LFS). You do NOT need to download any other file
   from anywhere.
2. One secret is NOT in this repository: the **API key**. The operator will give
   it to you as a string. You will put it into a file named `.env` in Step 3.
3. This is a server with no desktop. You will use a terminal only.

## Step 1 — install Git LFS + clone this repository

```bash
git clone --depth 1 https://github.com/flowforge-development/levi-deploy.git
cd levi-deploy
curl -s https://packagecloud.io/install/repositories/github/git-lfs/script.deb.sh | sudo bash
sudo apt-get install -y git-lfs
git lfs install
git lfs pull
```

**Expected output (last line):** something ending in `smudge` success, or a list
of files. **Then check the database is really here:**

```bash
ls -la levi.db
```

**Expected:** a line showing `levi.db` with size around `589000000` (about
589,000,000 bytes). If `levi.db` is small (< a few MB) or missing, STOP and
paste `git lfs pull` output to the operator.

## Step 2 — install Docker

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
```

**Check:**

```bash
docker version
```

**Expected:** it prints a "Client" section and a "Server" section without an
error. If you see "permission denied", run `sudo usermod -aG docker $USER`,
logout/in as root is fine: continue with `sudo docker` everywhere if needed.

## Step 3 — set the API key

The operator gave you a key string. Create the env file (replace `PASTE_THE_KEY`
with the string, no quotes, no spaces):

```bash
echo 'LEVI_API_KEY=PASTE_THE_KEY' > .env
cat .env
```

**Check:** `cat .env` shows one line, `LEVI_API_KEY=` followed by your key.

## Step 4 — build and start the container

```bash
docker compose up -d --build
sleep 6
docker compose ps
```

**Expected:** `docker compose ps` shows a service named `levi` with status
`running` (or `Up`). If it says `Exited` or `Restarting`, STOP and paste
`docker logs levi` to the operator.

## Step 5 — verify the API (run all five, in order)

```bash
curl -s http://localhost:8777/health
```

**Expected:** `{"ok": true, "one_api": "scripture-only"}`

```bash
curl -s -H "Authorization: Bearer PASTE_THE_KEY" "http://localhost:8777/verse?ref=Genesis%201:1" | head -c 200
```

**Expected:** JSON starting with `{"id": "Genesis.1.1"` and containing
`"kjv_text": "In the beginning God created the heaven and the earth."`

```bash
curl -s -H "Authorization: Bearer PASTE_THE_KEY" "http://localhost:8777/interlinear?ref=John%201:1" | head -c 200
```

**Expected:** JSON with `"lang": "grc"` and a `"words"` array.

```bash
curl -s -H "Authorization: Bearer PASTE_THE_KEY" "http://localhost:8777/search?q=grace" | head -c 200
```

**Expected:** JSON containing a `"results"` or verse list (not an error string).

```bash
curl -s -H "Authorization: Bearer PASTE_THE_KEY" "http://localhost:8777/query?ref=Romans%208:28&caps=text,interlinear,crossref" | head -c 300
```

**Expected:** JSON with `"ref": "Romans 8:28"` and at least `"text"` and
`"interlinear"` keys.

## Step 6 — report success

When all five curl checks match, paste this exact line to the operator:

```
LEVI LIVE — health ok, verse ok, interlinear ok, search ok, query ok.
```

Also paste the machine's public IP address (`curl -s ifconfig.me`).

---

## If anything fails

- **"levi.db too small"** → Git LFS did not fetch. Run `git lfs install && git lfs pull` again, then `git lfs fsck`.
- **"docker: permission denied"** → use `sudo` in front of every docker command.
- **health returns 401 or empty** → you forgot the API key header or the `.env`; re-read Step 3 and Step 5.
- **container exits** → `docker logs levi`, paste the LAST 10 lines to the operator, and change nothing else.

Do not attempt any fix other than the ones listed above. Report, don't improvise.