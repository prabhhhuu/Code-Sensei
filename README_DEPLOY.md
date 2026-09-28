# 🚀 Deployment Guide — AI Code Tutor (`cs_new`)

Flask + SQLite + Groq monolith. The challenge runner compiles/executes user code
with **Node.js, JDK (javac/java), gcc, g++**, so any host must provide those
toolchains — that's why this deploys as a **Docker image** on PaaS, or on a VM.

**Architecture facts that shape deployment**
- SQLite file DB → needs a **persistent volume** (`DATABASE_DIR=/data`).
- Groq API calls can take up to 90 s → gunicorn timeout is set to 120 s.
- `run_challenge_tests()` executes user code via `exec()` / subprocess →
  containerize it (done here) and don't share the container with anything else.

---

## Option 2 (recommended): Railway (~10 minutes, ~$5/mo)

### One-time prep
1. Create a GitHub repo and push the `cs_new` folder (`.gitignore` keeps
   `.env`, `ai_tutor.db`, `__pycache__` out).
2. Generate fresh secrets:
   ```bash
   python3 -c "import secrets; print(secrets.token_hex(32))"   # SECRET_KEY
   ```
   Get a Groq key at <https://console.groq.com/keys>. **Rotate the old key** —
   it sat in a local `.env` next to the code.

### Railway steps
1. <https://railway.app> → **New Project → Deploy from GitHub repo** → pick the repo.
   Railway auto-detects the `Dockerfile` (it's at `cs_new/Dockerfile`; if the
   repo root is `cs_new` itself, detection is automatic).
2. Service → **Variables** tab → add:
   | Variable | Value |
   |---|---|
   | `SECRET_KEY` | the generated hex string |
   | `GROQ_API_KEY` | your Groq key |
   | `DATABASE_DIR` | `/data` |
3. Service → **Settings → Volumes → New Volume** → mount path `/data`.
4. **Settings → Networking → Generate Domain** → you get
   `https://<app>.up.railway.app`. Done — every push to `main` redeploys.

### Verify it's alive
```bash
curl -s https://<app>.up.railway.app/login | head -5
```
Then register a user, run one AI analysis, and submit one challenge.

---

## 🆓 Free, no card: Render free tier (fastest zero-cost path)

Click-by-click, ~10 minutes, no credit card:

1. Push the repo to GitHub (see git steps in the Railway section below).
2. <https://dashboard.render.com> → sign in with GitHub → **New + → Web Service**.
3. Pick the repo. If your repo root is the *parent* folder, set **Docker Root
   Directory** = `cs_new`; if the repo root *is* `cs_new`, leave blank.
4. **Instance Type: Free** (512 MB RAM). **Region**: closest to you.
5. **Environment Variables** → add all three:
   | Key | Value |
   |---|---|
   | `SECRET_KEY` | generated via `python -c "import secrets; print(secrets.token_hex(32))"` |
   | `GROQ_API_KEY` | your key (rotate the old one — it lived in a local `.env`) |
   | `DATABASE_DIR` | `/tmp` (ephemeral) — see the disk warning below |
   | `WEB_CONCURRENCY` | `1` (fits javac/g++ into 512 MB) |
6. **Create Web Service** → first build takes ~5–8 min (compilers install) →
   live at `https://<app>.onrender.com`.

**Free-tier limits (know before you demo):**
- **Ephemeral disk** — `DATABASE_DIR=/tmp` means all accounts/history **wipe on
  every sleep, redeploy, or restart**. Render free has no persistent disk.
- **Spins down after ~15 min idle** → first visitor waits ~50 s for spin-up.
- 512 MB RAM: Java/C++ challenges *may* fail under concurrent load; Python/JS fine.
- Bandwidth 100 GB/mo — plenty for a demo.

**Verdict:** perfect for showcasing/class demos where data loss between visits
is acceptable. If users must keep accounts, use Oracle Always-Free (below) or a
paid plan (~$7/mo) that adds a persistent disk.

---

## 💰 Paid alternative: Railway (~$5/mo)

Full click-by-click steps are in **"Option 2 (recommended): Railway"** at the
top of this guide — same Dockerfile, same variables. What you gain over free
Render: **Volumes → New Volume → mount `/data`** makes the SQLite DB persist
across redeploys, no spin-downs, no 50 s cold starts.

---

## 🆓 Free forever: Oracle Cloud Always-Free VM (recommended zero-cost path)

Best free option: 4 ARM cores + 24 GB RAM across 2 instances (or 1× 2 OCPU/12 GB),
no expiry, data persists. Card needed **only for identity check** — never charged
on Always-Free resources.

1. **Sign up** — <https://oracle.com/cloud/free> → *Start for free*. Choose the home
   region closest to you (permanent). Verify email + card. Wait for provisioning.
2. **Create the VM** — Compute → Instances → Create Instance:
   - Image: **Ubuntu 22.04**
   - Shape: **VM.Standard.A1.Flex (Ampere ARM)**, 2 OCPU, **12 GB RAM** (Always Free)
   - SSH keys: download the **private key** and keep it safe
   - If you hit "Out of capacity": retry later / try another availability domain.
3. **Open web ports** — Instance details → Subnet → Security List → Add Ingress Rules:
   Source `0.0.0.0/0`, TCP **80** and **443**.
4. **SSH in** and follow the Option 1 runbook below verbatim:
   ```bash
   ssh -i <private-key> ubuntu@<PUBLIC_IP>
   ```
   (Upload code without git via: `scp -i <private-key> -r cs_new ubuntu@<PUBLIC_IP>:~/`)
5. Continue at **"Option 1 (DIY): Ubuntu VPS"** step 1. Everything else is identical.

---

## Option 1 (DIY): Ubuntu VPS — full copy-paste runbook

Works on AWS EC2, DigitalOcean, Hetzner, Oracle Cloud free tier.
**VM size: ≥ 2 GB RAM** (javac and g++ need headroom). Ports 22/80/443 open.

```bash
# 1. System + toolchains
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-venv python3-pip nginx git \
                    gcc g++ default-jdk curl
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - \
  && sudo apt install -y nodejs

# 2. Code
git clone <your-repo-url> ~/cs_new        # or: scp -r cs_new user@vm:~/

# 3. Python env
cd ~/cs_new/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 4. Secrets (fresh values — never copy the dev .env)
cat > .env <<'EOF'
SECRET_KEY=<generated-hex>
GROQ_API_KEY=<your-key>
EOF
chmod 600 .env

# 5. Smoke test (Ctrl+C after you see "Listening at: http://127.0.0.1:5000")
gunicorn -w 2 --threads 4 --timeout 120 -b 127.0.0.1:5000 app:app
```

**systemd service** — `/etc/systemd/system/cs-tutor.service`:
```ini
[Unit]
Description=AI Code Tutor (Flask/gunicorn)
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/cs_new/backend
Environment="PATH=/home/ubuntu/cs_new/backend/.venv/bin"
Environment="DATABASE_DIR=/home/ubuntu/cs_new/backend"
ExecStart=/home/ubuntu/cs_new/backend/.venv/bin/gunicorn \
  -w 2 --threads 4 --timeout 120 -b 127.0.0.1:5000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload && sudo systemctl enable --now cs-tutor
sudo systemctl status cs-tutor          # should be active (running)
```

**nginx reverse proxy** — `/etc/nginx/sites-available/cs-tutor`:
```nginx
server {
    listen 80;
    server_name your-domain.com;        # or the VM public IP

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;        # Groq calls take up to 90 s
    }
}
```
```bash
sudo ln -s /etc/nginx/sites-available/cs-tutor /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 6. HTTPS + firewall
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
sudo ufw allow OpenSSH && sudo ufw allow 80,443/tcp && sudo ufw enable
```

**Updates later:**
```bash
cd ~/cs_new && git pull
sudo systemctl restart cs-tutor
```

### Option 1 via Docker instead of venv/systemd
If you prefer the same image as PaaS:
```bash
sudo apt install -y docker.io docker-compose-v2
cd ~/cs_new
sudo docker build -t cs-tutor .
sudo docker run -d --name cs-tutor --restart always \
  -p 80:8000 \
  -e SECRET_KEY=<hex> -e GROQ_API_KEY=<key> -e DATABASE_DIR=/data \
  -v cs_tutor_data:/data cs-tutor
```

---

## Environment variables (summary)

| Var | Required | Notes |
|---|---|---|
| `SECRET_KEY` | ✅ | Flask session signing; generate fresh per environment |
| `GROQ_API_KEY` | ✅ | AI features; rotate the previously local one |
| `HF_TOKEN` | optional | read by `config.py`, currently unused |
| `DATABASE_DIR` | PaaS only | point at the mounted volume (`/data`); unset = `backend/` |
| `WEB_CONCURRENCY` | low-RAM hosts | set `1` on Render free (512 MB); default is 2 |

## Post-deploy checklist
- [ ] Register + login works over HTTPS
- [ ] One AI analysis succeeds (validates `GROQ_API_KEY`)
- [ ] One Python challenge submission passes (validates DB write)
- [ ] One JS challenge runs (validates Node in image)
- [ ] Redeploy → data still there (validates volume mount)

## Known risks (fix soon)
1. **`exec()` of user Python runs inside the Flask process** — a malicious user
   could read the DB and env vars. Mitigate by moving test execution to an
   external sandbox (Judge0 / Piston) or at minimum keep single-tenant use.
2. SQLite = single-writer; fine for a class project, not for concurrent scale.
3. CSRF protection is not enabled on the Flask forms (Flask-WTF would fix it).
