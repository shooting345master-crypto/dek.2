# Deploying Falcon Fitness

Three ways to run this site, in order of how much they cost and how much they
give you. Read the comparison before you pick.

| | Termux (your phone) | Fly.io | Indian shared host |
|---|---|---|---|
| **Cost** | Free | ~₹0–400/mo | ~₹100–250/mo |
| **Reachable by the public** | No (Wi-Fi only) | Yes | Yes |
| **Survives your phone dying** | No | Yes | Yes |
| **Data centre** | Your desk | Mumbai (`bom`) | Mumbai / Delhi / Kolkata |
| **Setup effort** | Low | Medium | Medium |
| **Good for** | Development, testing, in-gym demo | A real public website | A real public website, India-based |

> **Honest note on "Kolkata region":** Fly.io does **not** have a Kolkata
> region. The closest are `bom` (Mumbai, ~1,650 km, 30–45 ms) and `del`
> (Delhi). For a gym site whose visitors are all in Kestopur, that latency is
> invisible — nobody notices 40 ms. If you specifically want a **Kolkata
> datacentre**, you need an Indian host: Hostinger, MilesWeb, BigRock or AWS
> `ap-south-1`. See section 4.

---

## 1. Run it on your phone (Termux)

Best for testing. Not reachable from outside your Wi-Fi.

```bash
pkg install python clang git -y
cd /sdcard/falcon-fitness/falcon-fitness
pip install -r requirements.txt
python app.py
```

Then open `http://127.0.0.1:5000` in Chrome on the same phone.

Full walkthrough: **ANDROID-TERMUX.md**

---

## 2. Deploy to Fly.io

### 2.1 Install the CLI

**On your phone (Termux)**

```bash
pkg install curl -y
curl -L https://fly.io/install.sh | sh
```

That installs `flyctl` into `~/.fly/bin`. Add it to your path *for this
session only* (the paste-safe way — no `$` or `~` needed):

```bash
export PATH="/data/data/com.termux/files/home/.fly/bin:/data/data/com.termux/files/usr/bin:/data/data/com.termux/files/usr/bin"
```

Simpler and permanent:

```bash
cd /data/data/com.termux/files/home
./.fly/bin/flyctl version
```

If that prints a version, you can call it as `./.fly/bin/flyctl` from your home
folder every time. That is the safest habit on Termux.

### 2.2 Log in and create the app

```bash
cd /sdcard/falcon-fitness/falcon-fitness
/data/data/com.termux/files/home/.fly/bin/flyctl auth signup
/data/data/com.termux/files/home/.fly/bin/flyctl launch --no-deploy --copy-config
```

`--copy-config` uses the `fly.toml` already in this folder, which is
configured for `bom` (Mumbai).

### 2.3 Create the volume — **do this before the first deploy**

```bash
/data/data/com.termux/files/home/.fly/bin/flyctl volumes create falcon_data --size 1 --region bom
```

Without this volume your enquiry database is wiped on every redeploy.

### 2.4 Set your email secrets (optional but recommended)

Without this, enquiries are saved on the server but nobody is told about them.

```bash
/data/data/com.termux/files/home/.fly/bin/flyctl secrets set \
  FALCON_SMTP_HOST=smtp.gmail.com \
  FALCON_SMTP_PORT=587 \
  FALCON_SMTP_USER=yourgym@gmail.com \
  FALCON_SMTP_PASS=your16charapppassword \
  FALCON_MAIL_FROM=yourgym@gmail.com \
  FALCON_MAIL_TO=yourgym@gmail.com \
  FALCON_IP_SALT=some-long-random-string \
  FALCON_ADMIN_EMAIL=dinoalvez42@gmail.com \
  FALCON_ADMIN_PASSWORD=choose-a-strong-password
```

`FALCON_ADMIN_PASSWORD` is optional — leave it out and the admin account is
created with the default `Falcon.fitness29`, which is written in the public
guide, so **set it for a live deployment**. After the first deploy, sign in at
`/admin/login`.

**Gmail needs an App Password, not your normal password.**
Google Account → Security → turn on 2-Step Verification → App passwords →
create one for "Mail" → paste the 16 characters with **no spaces**.

### 2.5 Deploy

```bash
/data/data/com.termux/files/home/.fly/bin/flyctl deploy
```

First deploy takes 3–6 minutes (it compiles the C++ engine inside the build).
You get a URL like `https://falcon-fitness.fly.dev`.

### 2.6 Check it actually works

```bash
/data/data/com.termux/files/home/.fly/bin/flyctl logs
curl https://falcon-fitness.fly.dev/healthz
```

You should see:

```json
{"ok": true, "engine": "c++", "email": "configured", "db": true}
```

If `"engine"` says `python-mirror`, the compile step failed and the site is
running on the slower Python fallback — it still works, but tell me and I'll
look at the build log.

### 2.7 Your custom domain

Buy `falconfitness.in` from any registrar, then:

```bash
/data/data/com.termux/files/home/.fly/bin/flyctl certs add falconfitness.in
```

Fly prints the DNS records to add at your registrar. HTTPS is automatic.

---

## 3. Deploy to Render (has a free tier)

1. Push this folder to a GitHub repo.
2. Render → **New** → **Blueprint** → pick the repo. It reads `render.yaml`.
3. In the dashboard, add the same `FALCON_*` environment variables from
   section 2.4.

Render's free tier has **no persistent disk**, so the SQLite file is lost on
every redeploy. For a real inbox, either add a paid disk or use Fly.io instead.

Region note: Render has no India region — `singapore` is the closest.

---

## 4. If you specifically want an Indian datacentre

Any host that gives you a Python app with a `requirements.txt` will work.

1. Pick a **VPS in Mumbai or Delhi** (Hostinger VPS, DigitalOcean BLR, AWS
   `ap-south-1`) — shared "unlimited" hosting plans often block the
   long-running worker this needs.
2. Install Python 3.11+, `g++`, `nginx`.
3. Upload the folder (without `data/`), then:

```bash
cd /var/www/falcon-fitness
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
g++ -O3 -std=c++17 -o bin/falcon-engine engine/main.cpp
.venv/bin/gunicorn --bind 127.0.0.1:8080 --workers 2 --threads 4 app:app
```

4. Put nginx in front of port 8080 and run Let's Encrypt for free HTTPS.
5. Wrap the gunicorn command in a `systemd` service so it restarts on reboot.

Ask me and I'll write the exact nginx and systemd files for whichever host
you choose.

---

## 5. Before you go live — the checklist

- [ ] `FALCON_SMTP_*` and `FALCON_MAIL_TO` set, and a test enquiry arrives
- [ ] `FALCON_IP_SALT` set to a long random value
- [ ] `FALCON_EXPORT_TOKEN` set (so you can download enquiries as CSV)
- [ ] Persistent volume created, so the database survives redeploys
- [ ] `/healthz` returns `"engine": "c++"` and `"db": true`
- [ ] Submit one real enquiry from your own phone on mobile data
- [ ] Opening hours filled in (`HOURS` block at the top of `static/js/app.js`)
- [ ] Privacy and Terms pages read through and the refund policy confirmed
- [ ] The two phone numbers ring the right people

---

## 6. Reading your enquiries

### If email is configured

You get an email titled **"New enquiry — <name>"** the moment someone
submits the form. Reply to it and it goes straight back to them.

### If email is NOT configured

Enquiries are still saved. Download them as a spreadsheet:

```
https://YOUR-SITE/api/leads/export.csv?token=YOUR_FALCON_EXPORT_TOKEN
```

Or read them directly on the server:

```bash
cd /sdcard/falcon-fitness/falcon-fitness
python3 -c "import sqlite3;[print(r) for r in sqlite3.connect('data/falcon.db').execute('SELECT name,phone,email,goal,created_at FROM leads ORDER BY id DESC')]"
```

**Do not leave email unconfigured for long.** An enquiry nobody sees is a lost
member.
