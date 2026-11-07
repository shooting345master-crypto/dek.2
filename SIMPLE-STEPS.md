# THE EASY WAY — step by step, no terminal knowledge needed

**Short answer to your question: skip Termux. Use the Hostinger app + the terminal inside Hostinger's own dashboard.**

Why? Termux exists only to give you an SSH connection to the server. Hostinger's browser terminal *is* that connection — already open, already logged in, no app to install, no password to type. Fewer steps, fewer things to get wrong.

You will only ever deal with **2 windows**: the Hostinger app (browser) and the Hostinger terminal.

---

## The whole thing at a glance

| Step | Where | Time |
|---|---|---|
| 1. Buy the domain | Hostinger app | 5 min |
| 2. Buy the VPS | Hostinger app | 5 min |
| 3. Point the domain at the server | Hostinger app | 3 min |
| 4. Open the terminal | Hostinger app | 1 min |
| 5. Upload the zip | Hostinger file manager | 3 min |
| 6. **One command** | Hostinger terminal | 10 min (mostly waiting) |
| 7. Add HTTPS | Hostinger terminal | 3 min |
| 8. Check it on your phone | your phone browser | 3 min |

**Total: about 30 minutes of your attention.** Most of it is waiting.

---

## STEP 1 — Buy the domain

In the Hostinger app, finish the cart you already have.

- `fitn.co.in` — **₹469** for the first year
- ⚠️ Pay it. It is not reserved until paid.

**Then do the KYC today.** `.co.in` domains require NIXI to verify you as an Indian person/entity. Hostinger emails you a link; send them your PAN or Aadhaar. **If you skip this the domain gets suspended even though you paid.** This is the single most commonly ignored step with `.co.in`.

---

## STEP 2 — Buy the server (KVM 1)

Same app, **VPS → KVM 1 → Order**.

**Only one setting matters.** On the setup screen (it may be the second page) find **"Operating System"** and choose:

> ### Ubuntu 24.04 LTS

Not "Hostinger panel". Not "CyberPanel". Not "Ubuntu with Docker". Just **Ubuntu 24.04 LTS**.

Then finish checkout. Within a few minutes Hostinger emails you:

- an **IP address** (looks like `145.14.88.21`)
- a **root password**

**Copy both into your phone's Notes app right now.** You will need them in Step 4, and switching between an email and a terminal on a phone is annoying.

---

## STEP 3 — Point the domain at the server

Hostinger app → **Domains** → **fitn.co.in** → **DNS / Nameservers** → **DNS records**

You will see a list. Find the row where **Type** is `A` and **Name** is `@`.

1. Tap **edit** (pencil) on that row.
2. Change **Points to** to your server IP from Step 2.
3. Save.

Then add one more record — tap **Add record**:

| Field | Value |
|---|---|
| Type | `A` |
| Name | `www` |
| Points to | your server IP |

**That is all.** Do not delete anything else. Do not add a second `@` record — two `A` records for `@` is the classic mistake that makes a site load "sometimes".

Now leave it alone. DNS takes 15 minutes to a few hours. **You can do the rest while it catches up** — that is why this is Step 3 and not Step 8.

---

## STEP 4 — Open the terminal

Hostinger app → **VPS** → your server → look for **Terminal** (sometimes "Browser terminal" or "Open console").

A black screen appears with a prompt. **You are already logged in as root.** No SSH, no password, no Termux.

Tap the screen once. If a keyboard hides the prompt, scroll down.

### The one command in this step

Copy-paste this and press Enter (in the Hostinger app, long-press the terminal for Paste):

```
mkdir -p /home/falcon/app
```

That creates the folder the site will live in. Nothing else to do here yet.

> **Typing tip for a phone:** every command in this guide is one line. Paste rather than type — a single wrong character causes a confusing error.

---

## STEP 5 — Upload the zip

Stay in the Hostinger app. Go to **VPS → your server → File Manager**.

1. Navigate into **`/home/falcon/app`** (created in Step 4). If you cannot see `/home`, look for a path box or "go to folder" at the top and type `home/falcon/app`.
2. Tap **Upload**.
3. Pick `falcon-fitness.zip` from your phone's Downloads.

Wait for it to reach 100% — it is 4.4 MB, so a few seconds on 4G.

**Do not unzip it here.** The next step does that.

---

## STEP 6 — The one command that installs everything

Back to **VPS → Terminal**.

Paste this **as a single line** and press Enter:

```
cd /home/falcon/app && unzip -qo falcon-fitness.zip && cd falcon-fitness && bash deploy/go-live.sh
```

> If it says `unzip: command not found`, run this first, then the line above again:
> ```
> apt install -y unzip
> ```

### It will ask you 3 things

| It asks | Type |
|---|---|
| `Your domain name [fitn.co.in]:` | press **Enter** |
| `Admin email address [dinoalvez42@gmail.com]:` | press **Enter** |
| `Choose the ADMIN PANEL password (typing is hidden):` | type a password of **10+ characters** and press Enter |

⚠️ **When you type the password, nothing appears on screen.** No dots. That is normal — type it anyway and press Enter.

### Then wait

You will see coloured ticks appear one at a time. **Total: 3 to 8 minutes** on a fresh server, because it installs Python, Nginx and the image library for you.

```
✓ user 'falcon' created
✓ system packages installed
✓ owned by falcon
✓ web server can reach the static files
✓ Flask + Pillow + gunicorn installed
✓ C++ engine compiled natively on this server
✓ .env written (readable only by falcon)
✓ falcon.service is running
✓ Nginx config is valid
✓ Nginx reloaded
{"db":true,...,"engine":"c++","ok":true}
✓ C++ engine live
```

**Keep the tab open.** If your phone locks and the terminal disconnects, do not panic — reconnect and run the same line again. It picks up where it left off and will not damage anything.

### At the end it checks your DNS

One of these appears:

- **`✓ DNS is correct`** → go straight to Step 7.
- **`! DNS is not pointing here yet`** → **nothing is wrong.** Your domain records from Step 3 are still propagating. The site is running; it just is not reachable by name yet. Do Step 8's checks using the **IP address** for now, and come back to Step 7 in an hour or two.

### What that one command actually did

So you know what you agreed to:

- installed Python, Nginx, the compiler and HTTPS tooling
- created a safe non-root user (`falcon`) to run the site
- installed the website's dependencies
- compiled the C++ engine **on the server**
- generated your `.env` with random security salts and `FALCON_HTTPS=1`
- wrote and started the background service, so the site restarts itself after a crash or reboot
- wrote the Nginx config and **tested it before reloading** — a bad config would have been refused, not applied

**Running it a second time is safe.** I tested exactly that: your database, your settings and your password are all left untouched.

---

## STEP 7 — Add HTTPS (the padlock), when DNS says it is ready

Only run this **after** Step 6 said `✓ DNS is correct` — or after you have waited a while.

In the Hostinger terminal:

```
certbot --nginx -d fitn.co.in -d www.fitn.co.in
```

It asks a few things:

1. **Email address** → type your email, Enter
2. **Agree to the terms** → type `A`, Enter
3. **Share your email with EFF?** → `N` is fine, Enter
4. **Redirect HTTP to HTTPS?** → choose **`2`** (Redirect), Enter

When it says **Congratulations**, your padlock is on and it renews itself forever, free.

> If it errors with "no valid IP found" — your DNS simply is not ready. Wait, then run the same command again. Nothing is broken.

---

## STEP 8 — Check it on your phone

Open a **new tab** in your phone browser (keep the Hostinger terminal in the other one).

Go to **`https://fitn.co.in`**

Tick these off. It takes three minutes and it is the difference between "installed" and "working".

- [ ] Site loads, **padlock** showing, no warning
- [ ] **Green/amber dot at the top** with a live status — `OPEN NOW`, `CLOSING SOON` or `CLOSED`
- [ ] Hours card says **`6:30 am – 11:00 pm`**
- [ ] **Menu button** (top right) opens the menu
- [ ] **WhatsApp button** is green and opens WhatsApp
- [ ] **`/register`** opens the registration form
- [ ] **`https://fitn.co.in/admin/login`** → sign in with the password you chose in Step 6

**Then turn your Wi-Fi off and reload.** If it still loads on mobile data, the site is genuinely public. This is the check people skip, and it is the only one that proves it.

### If sign-in does nothing at all

Look at your address bar. If it says `http://` and not `https://`, that is the cause — you are on the insecure version and the login cookie is being refused. Change it to `https://` and try again. (Once Step 7 is done, this fixes itself permanently.)

---

## Everyday use, from the app

You do not need to do anything to keep the site running. It restarts itself after crashes and after reboots.

When you want to look at it, Hostinger app → **VPS → Terminal**, then:

| Task | Command |
|---|---|
| Is it running? | `systemctl status falcon` |
| What went wrong? | `journalctl -u falcon -n 50` |
| Restart it | `systemctl restart falcon` |
| Health check | `curl -s https://fitn.co.in/healthz` |

The health check is your one-glance test. `"ok":true` and `"engine":"c++"` means everything is fine.

### Backup — do this monthly

One line in the terminal, then download the file with the File Manager:

```
sqlite3 /home/falcon/app/data/falcon.db ".backup '/home/falcon/backup-$(date +%F).db'"
```

That file **is your gym** — members, payments, attendance, receipts. Save it somewhere other than the server.

---

## When something looks wrong

| What you see | The fix |
|---|---|
| Site loads but looks unstyled | Run Step 6 again — it repairs file permissions |
| `502 Bad Gateway` | `journalctl -u falcon -n 40` shows why; usually `systemctl restart falcon` |
| "Welcome to nginx" page | Step 6 did not finish — run the line again |
| Padlock missing / certificate error | DNS not ready yet — wait, then Step 7 |
| Sign-in does nothing | Use `https://` not `http://` |
| `unzip: command not found` | `apt install -y unzip`, then Step 6 |
| Terminal disconnects mid-install | Reconnect and run Step 6's line again — it is safe |
| Domain expired/suspended | The `.co.in` KYC from Step 1 was not completed |

**The universal first move:** `journalctl -u falcon -n 50`. It is the site's own diary and it usually names the problem in plain words.

---

## Is Termux ever needed?

Only if you want to poke at the server from the sofa *without* opening a browser. Termux gives you `ssh falcon@YOUR-SERVER-IP` and works fine — but it is a second app, a second password, and no benefit for anything in this guide. **Do the deployment through Hostinger's terminal; ignore Termux.**

---

## What to tell me when it is done

Send me:

1. Whether Step 6 ended with **`✓ DNS is correct`** or the DNS warning
2. The line from **`curl -s https://fitn.co.in/healthz`**
3. Anything that came up as a **red ✗** instead of a green ✓

I can read those three answers and tell you exactly what to do next — no guessing.
