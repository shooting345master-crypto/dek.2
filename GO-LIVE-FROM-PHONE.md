# GOING LIVE FROM YOUR PHONE

Deploying `fitn.co.in` + Falcon Fitness on a Hostinger KVM 1 **using only your Android phone**. No laptop needed at any point.

---

## First, the honest answer to "can I?"

**Yes — with one caveat you should know before you start.**

A Hostinger VPS is a Linux machine you reach over SSH. A phone cannot *be* that machine, but it is an excellent *remote control* for it. Android has free terminal apps that do SSH properly, including copy-paste and a real keyboard layout. Everything the laptop guide does, your phone can do.

**The caveat:** the hardest part of the laptop guide was typing long config files (the systemd unit, the Nginx site). On a phone that is genuinely miserable — wrong characters, lost lines, no undo. So **I removed that step entirely.** There is now a one-command installer on the server that writes both files for you. You type one line and answer four questions.

**What you need:**

| Item | Why |
|---|---|
| Your Android phone | everything happens here |
| A **Termux** app (free, from F-Droid) | the SSH terminal |
| Hostinger account | already have it |
| Your server IP + root password | emailed by Hostinger when the VPS is created |
| A credit/debit card or UPI | domain + VPS purchase |
| ~60 minutes, mostly waiting | installs are slow over mobile data |

**Two things do not work well on a phone and you should know why:**

1. **Uploading files** — 4.4 MB over a phone browser to a file manager is slow but fine. Part 4 covers it.
2. **Buying the VPS from the Hostinger app** is possible but the OS selection is easy to miss in the mobile layout. Part 1 tells you exactly which screen to look for.

---

## Part 1 — Buy the domain and the VPS (from the browser)

You already have the domain in your cart. Continue as you were:

1. Pay for **`fitn.co.in`** — ₹469 for year one. It is not reserved until paid.
2. **Then** buy **KVM 1**. On the mobile site, the operating system appears on the *second* screen of the VPS setup, under a heading like **"Operating System"** or **"Choose your OS"**. Set it to:

   **Ubuntu 24.04 LTS** (64-bit)

   > Do not accept a "Hostinger panel" or "CyberPanel" image. This guide — and the installer — assume plain Ubuntu.
3. **Location:** India / Mumbai if available.
4. Hostinger emails you two things: the **server IP** (like `145.14.x.x`) and the **root password**. Copy them into a notes app. On mobile, the email app makes it fiddly to switch back and forth — save them first.

⚠️ **Do the `.co.in` KYC the same day.** NIXI (the Indian registry) needs your PAN or Aadhaar verified. Hostinger emails a link. If you skip it, the domain gets suspended even though it is paid.

---

## Part 2 — Point the domain at the server (browser)

Same as the laptop guide, still in the browser:

**Hostinger → Domains → fitn.co.in → DNS / Nameservers → DNS records**

Edit the existing `A` record for `@` (do not add a second one) to your server IP, and add a second for `www`:

| Type | Name | Points to |
|---|---|---|
| A | `@` | your server IP |
| A | `www` | your server IP |

Do this early — DNS takes 15 minutes to a few hours, and you can keep working while it propagates.

---

## Part 3 — Install Termux and connect

### 3.1 Install Termux

**Get it from F-Droid, not the Play Store.**

- F-Droid: `https://f-droid.org/packages/com.termux/`
- Or open F-Droid, search **Termux**, install.

> **Why not the Play Store?** The Play Store build was abandoned years ago and its package repositories are broken — `pkg install` fails with 404s. The F-Droid build is the maintained one. This single choice saves you twenty minutes of confusion.

### 3.2 Prepare it for typing

Open Termux. It shows a black screen with a `$` prompt. First, make it usable on a phone:

1. **Swipe from the left edge** → drag out the side drawer → **More… → Style →** pick a bigger font.
2. **Extra keys row:** long-press anywhere on the keyboard row → **Extra keys**. You now get `ESC`, `TAB`, `/`, `-`, `|` buttons — you will need every one of them.
3. **Copy-paste:** long-press on the screen → **Paste**. To copy text *out* of Termux, long-press → **More → Select text**.

### 3.3 Install SSH and connect

Type this (or paste it) in Termux, pressing Enter after each line:

```
pkg update -y
```
```
pkg install -y openssh
```

Now connect — replace the IP with yours:

```
ssh root@YOUR_SERVER_IP
```

- First time it asks **"Are you sure you want to continue connecting?"** → type `yes` and Enter.
- It then asks for the **root password**. Paste it (long-press → Paste). **Nothing will appear as you type or paste** — no dots, no stars. That is normal and alarming the first time. Press Enter.

You will see a prompt ending in `#`. You are now root on your server, from your phone.

> **Practical phone tip:** turn on **Do Not Disturb**, and in Termux settings enable **"Acquire wakelock"** so Android does not kill your session halfway through an install. If the session does drop, just reconnect with the same `ssh` command — the server kept working.

### 3.4 While you are here, make a second user

Do this now — it is four short lines, and it makes the server much safer. Run each separately:

```
apt update && apt upgrade -y
```
```
adduser falcon
```

It asks for a new password (pick a strong one, save it) and some name fields — press Enter through the name fields.

```
usermod -aG sudo falcon
```
```
rsync --archive --chown=falcon:falcon /root/.ssh /home/falcon
```

Then open the firewall:

```
ufw allow OpenSSH
```
```
ufw allow 'Nginx Full'
```
```
ufw --force enable
```

**Test it before going further.** Log out (`exit`) and reconnect as the new user:

```
ssh falcon@YOUR_SERVER_IP
```

If that works, lock the root door (`exit` back to Termux, reconnect as root, then):

```
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
```
```
systemctl restart ssh
```

From now on you log in as `falcon`, not `root`.

---

## Part 4 — Get the zip onto the server

This is the one step where a phone needs a moment of thought. Choose **one** of these.

### Option A — Hostinger File Manager (easiest on a phone)

1. In your phone browser, open **Hostinger hPanel → VPS → your server → File Manager** (sometimes called "Browser").
2. Navigate to `/home/falcon/`, create a folder `app`.
3. Upload `falcon-fitness.zip` from your phone's Downloads using the upload button (a paperclip or up-arrow).

**Do not unzip it in the file manager** — unzipping through a mobile panel can mangle permissions. Do it in the terminal:

```
cd /home/falcon/app
```
```
unzip -o falcon-fitness.zip
```

(If `unzip` is missing: `sudo apt install -y unzip`.)

### Option B — Upload from the phone directly to the server over SSH

In Termux, install a file picker and use `scp` from the phone to the server:

```
pkg install -y openssh
```
```
termux-setup-storage
```

Approve the storage prompt, then (this sends the file **from your phone** — note this runs in Termux, not on the server):

```
scp /sdcard/Download/falcon-fitness.zip falcon@YOUR_SERVER_IP:/home/falcon/app/
```

Before that, create the folder on the server (`mkdir -p /home/falcon/app`).

### Option C — Skip the zip entirely: let the server fetch it

If you would rather not move a file at all, ask me for a download link and then, on the server:

```
cd /home/falcon/app
```
```
curl -O https://THE-LINK-I-GIVE-YOU/falcon-fitness.zip
```
```
unzip -o falcon-fitness.zip
```

Whichever option you pick, confirm the file arrived and is the right size (~4.4 MB):

```
ls -lh /home/falcon/app/falcon-fitness.zip
```

---

## Part 5 — The one command that does everything

This is the part that replaces all the typing from the laptop guide.

On the server (you are `falcon`, in the `/home/falcon/app` folder):

```
cd /home/falcon/app/falcon-fitness
```

Install the few system packages first — one line:

```
sudo apt install -y python3 python3-venv python3-pip nginx g++ certbot python3-certbot-nginx
```

Takes 1–2 minutes on mobile data. Then:

```
sudo bash deploy/go-live.sh
```

**It asks you four questions.** Press Enter to accept each default shown in `[brackets]`:

| Question | What to answer |
|---|---|
| Your domain name | `fitn.co.in` |
| Admin email address | `dinoalvez42@gmail.com` |
| Linux user that will run the site | `falcon` |
| Choose the ADMIN PANEL password | your new strong password — **typing is hidden** |

Then it prints coloured ticks as it works, about 60–90 seconds:

```
▸ Creating the Python environment (this is the slow step, 1-3 min)
  ✓ Flask + Pillow + gunicorn installed
  ✓ C++ engine compiled natively on this server
▸ Writing .env
  ✓ .env written (readable only by falcon)
▸ Installing the background service
  ✓ falcon.service is running
▸ Installing the Nginx site for fitn.co.in
  ✓ Nginx config is valid
▸ Checking the app answers locally
  {"db":true,...,"engine":"c++","ok":true}
▸ Checking that fitn.co.in points at this server
  this server : 145.14.x.x
  fitn.co.in  : 145.14.x.x
  ✓ DNS is correct
▸ Requesting the certificate
  ✓ HTTPS enabled — https://fitn.co.in
```

**What it did for you** (so you know what you are trusting):

- created the Python environment and installed the dependencies
- compiled your C++ engine on the server itself
- wrote `.env` with `FALCON_HTTPS=1` and **random** salts for IP hashing and OTPs
- wrote and started `/etc/systemd/system/falcon.service` with the correct user and paths
- wrote `/etc/nginx/sites-available/falcon` with your domain and the required forwarding headers
- checked that Nginx accepts the config **before** reloading it
- checked whether your DNS points here, and only then asked about HTTPS
- verified the app answers on `127.0.0.1:8000` and which engine it is using

**It is safe to run twice.** Running it again: keeps your database, keeps your `.env` (including your password), and only updates the service and Nginx files. I tested exactly that — after a second run, the users and plans were untouched and the password was unchanged.

**If DNS is not ready yet,** it stops and tells you to run this later, instead of failing with a confusing certificate error:

```
sudo certbot --nginx -d fitn.co.in -d www.fitn.co.in
```

---

## Part 6 — Check it on the same phone you deployed from

Open a **new browser tab** (leave Termux running) and visit:

**`https://fitn.co.in`**

Then walk this list — it takes three minutes and it is the difference between "deployed" and "actually working":

- [ ] **Home page loads with the padlock**, no warning
- [ ] **Live badge** shows the correct state for the current time
- [ ] **Hours card** says `6:30 am – 11:00 pm`
- [ ] **Tap the menu button** (top right) — menu opens
- [ ] **Prices** are visible on the public page as designed
- [ ] **WhatsApp button** is green and opens WhatsApp with your number
- [ ] **`/register`** opens the registration form
- [ ] **`https://fitn.co.in/admin/login`** — sign in with the password you chose in Part 5
- [ ] **Sign out** from the mobile menu works
- [ ] Turn **Wi-Fi off** and reload — still works, so it really is public, not cached

**The single most important check:** if `FALCON_HTTPS=1` is set but you browse over `http://`, signing in silently does nothing. If login "does nothing", add the `s` to `https://` — that is the fix.

---

## Part 7 — Running the site from your phone day to day

You never need to touch the server for the site to stay up. Systemd restarts it on crash and on reboot. But when you want to look:

```
ssh falcon@YOUR_SERVER_IP
```

**The five commands that cover almost everything:**

```
sudo systemctl status falcon
```
```
sudo journalctl -u falcon -n 50 --no-pager
```
```
sudo systemctl restart falcon
```
```
sudo systemctl reload nginx
```
```
curl -s https://fitn.co.in/healthz
```

The last one is your one-glance health check — `"ok":true` and `"engine":"c++"` means everything is fine.

**A handy phone shortcut:** in Termux, long-press the screen → **More → Keep screen on**. And to save typing, Termux has history — swipe up on the keyboard row or press the volume-up+`C`, or just use the up-arrow key.

### Taking a backup from your phone

Run this on the server whenever you want a copy:

```
sudo bash /home/falcon/backup.sh
```

That script does not exist yet — the laptop guide's Part 11 creates it. On a phone, do this instead, which achieves the same thing in one line:

```
sqlite3 /home/falcon/app/falcon-fitness/data/falcon.db ".backup '/home/falcon/falcon-backup-$(date +%F).db'"
```

Then download it with the **Hostinger File Manager** (open `/home/falcon/`, tap the file, Download) or with `scp` in Termux:

```
scp falcon@YOUR_SERVER_IP:/home/falcon/falcon-backup-2026-11-05.db /sdcard/Download/
```

**Do this before every update, and once a month regardless.** That file is your entire gym — members, payments, receipts index, attendance. It cannot be re-downloaded from anywhere.

---

## Part 8 — Updating the site from your phone later

When I send you a new zip:

```
cd /home/falcon/app
```
```
sudo systemctl stop falcon
```
```
cp falcon-fitness/data/falcon.db ~/pre-update-$(date +%F).db
```
```
unzip -o falcon-fitness.zip
```
```
cd falcon-fitness
```
```
sudo bash deploy/go-live.sh
```

The installer is idempotent, so it re-installs the service and Nginx correctly and leaves your `.env` alone. Then reload the site and check `/healthz`.

> Tell me when you are about to update, and I will tell you whether the build changed anything that needs a migration step.

---

## When something goes wrong (phone edition)

| What you see | What it means | The fix |
|---|---|---|
| `pkg install` fails with 404 | Play Store Termux | Uninstall, get it from **F-Droid** |
| Password prompt accepts nothing | passphrases do not echo — you are fine | paste, press Enter |
| SSH "Connection refused" | server still booting, or port 22 blocked | wait 2 min; check the IP in hPanel |
| `Welcome to nginx!` | Nginx is up but the site is not enabled | re-run `sudo bash deploy/go-live.sh` |
| **502 Bad Gateway** | the app is not running | `sudo journalctl -u falcon -n 40` |
| Certbot fails | DNS not pointing at the server yet | wait, then `sudo certbot --nginx -d fitn.co.in -d www.fitn.co.in` |
| Login does nothing, no error | `FALCON_HTTPS=1` but you are on `http://` | use `https://` |
| Installer says *"app.py not found"* | you are in the wrong folder | `cd /home/falcon/app/falcon-fitness` first |
| Installer says *"Run this with sudo"* | missing `sudo` | `sudo bash deploy/go-live.sh` |
| Session dies mid-install | Android killed Termux | reconnect, re-run — it resumes safely |
| Everything worked, then died after a reboot | service not enabled | `sudo systemctl enable falcon` |

**Your universal first move for anything:** `sudo journalctl -u falcon -n 50 --no-pager`. It is the site's own diary and it usually names the problem outright.

---

## Should you do this on a phone at all?

**Honest opinion: yes for this deployment, no as a long-term habit.**

- **Good on a phone:** the four-question installer, checking the site, restarting the service, reading logs, taking a backup. That is 90% of what you will ever do, and it is genuinely comfortable.
- **Better on a laptop:** the first-time server hardening, editing `.env` by hand, and anything where a typo costs you an outage. If a friend has a laptop, do Part 3.4 there.

The reason it is fine today is that the dangerous, typo-prone files (systemd unit, Nginx config) are no longer typed — they are generated and validated, and the installer refuses to reload Nginx on a bad config rather than taking your site down.

**One last thing worth doing before you announce the site:** register yourself as a member on your own phone, upload a receipt, do the OTP, and approve yourself in the admin panel. That exercises the entire flow — upload through Nginx, image screening, OTP, approval, digital card — and it is exactly what your first real member will do.
