# DOCKER HOSTING — what to do, and what it will actually cost

Your situation: **cost matters**, and the only hosting category you are confident about is **Docker-compatible**.

Good news: your project already has a working `Dockerfile`. I fixed two bugs in it below that would have destroyed data or stopped it booting at all.

---

## THE ANSWER, SHORT

**Docker hosting costs you MORE than the KVM 1, not less.** The reason is not CPU or traffic — it is the **persistent disk** you are forced to rent.

| Option | Monthly | Data survives redeploy? |
|---|---|---|
| **KVM 1 + the installer** | already paid | **Yes** — plain file on disk |
| Fly.io, smallest with a volume | **≈ ₹1,178** ($14) | Yes — volume is 1 GB min |
| Railway | usage-based, ≈ ₹420–₹840 typical | Yes, volumes included |
| Render (free tier) | ₹0 | ❌ **No — wiped on every restart** |

Sources: Fly's 1 GB volume is $0.15/GB/month with a **1 GB minimum**, and shared-cpu-1x 256 MB is $1.94/month ([Fly pricing](https://fly.io/docs/about/pricing/)). Render's free tier has no persistent disk at all ([Render disks](https://render.com/docs/disks)).

**So Docker hosting is roughly ₹1,000+/month where the VPS you already bought is a fixed yearly cost.** You are right that traffic does not justify a bigger machine — but no Docker platform sells you a machine smaller than this one.

---

## WHAT I FIXED IN YOUR DOCKERFILE (it could not have worked)

I simulated the image locally — same file list, same non-root user, port 8080, 2 workers.

### Bug 1 — the container crashed on boot

```
ModuleNotFoundError: No module named 'receipt_check'
```

`app.py` imports **`receipt_check`, `membership`, `sms_otp`** at lines 36–38, but the Dockerfile only copied `app.py` and `fallback_engine.py`. The image would have died instantly on every platform. **Fixed** — all five modules are copied now.

### Bug 2 — every deploy would have wiped your members

`fly.toml` mounts the volume at **`/data`**, but the Dockerfile set `FALCON_DB_PATH=/app/data/falcon.db` — which is inside the container's throwaway filesystem, **not** on the volume. Every redeploy would have silently replaced your members, payments and attendance with an empty database.

**Fixed** — the Dockerfile now writes to `/data/falcon.db`, matching the volume.

### Bug 3 — Render's free tier would wipe your data too

`render.yaml` sets `plan: free`, and free instances have no persistent disk. Data is lost on every redeploy, restart, and idle spin-down. I left the blueprint but added a plain warning in the file, because a gym that loses its payment records is worse than a gym with no website.

### Verified after the fixes

- boots, `/healthz` → `{"ok":true,"engine":"c++"}`
- all pages 200, live badge correct, mobile menu works, admin login works
- **data survived a simulated redeploy** — the admin account was still there

---

## IF YOU STILL WANT DOCKER: THE BEST FIT

### Option A — Fly.io, Mumbai (`bom`)

Your `fly.toml` is already configured for it, including `auto_stop_machines = "stop"` so it scales to zero when nobody is visiting.

```
fly launch --no-deploy --copy-config
```
```
fly volumes create falcon_data --size 1 --region bom
```
```
fly secrets set FALCON_ADMIN_PASSWORD=your-password FALCON_HTTPS=1
```
```
fly deploy
```

Notes that will bite you otherwise:

- **Do this before your first deploy:** `fly volumes create`. Without the volume the database is lost on every deploy.
- **`FALCON_ADMIN_PASSWORD` must be set in `fly secrets` before the first boot**, or your live site gets the default password.
- Money-saving trap: **auto-stop does not stop billing for a volume.** The disk is charged whether the machine runs or not.
- The first visitor after idle waits ~a few seconds while the machine starts.

### Option B — Railway

Similar Docker support, friendlier dashboard, volumes included in the plan, and it has an India-adjacent region. Slightly cheaper than Fly for this size, but the price is usage-based so it drifts.

### Option C — any Docker host you like

The image is now correct, so **Ghostty, Sliplane, Kamal on a VPS, Hostinger's own Docker VPS template, or AWS Lightsail Containers** will all work. The Dockerfile is portable now — that is the real win from the fixes above.

---

## THE TRAP TO AVOID

**Do not use a free Docker tier with SQLite.** Render free, Koyeb free, Hugging Face Spaces — none of them give you a persistent disk, so your database resets. Your app stores everything in one SQLite file (`data/falcon.db`) plus receipt images. Without a disk, members vanish.

If a Docker platform does not clearly say "persistent volume" or "disk", assume it loses your data.

---

## MY RECOMMENDATION

**Keep the KVM 1 you already bought and run the installer.** It is the cheapest option that does not lose data, the database is a real file you can copy in one command, and the setup is already down to three typed lines.

Use Docker only if one of these is true:

- you want to move between hosts easily later (the fixed Dockerfile makes that possible now)
- you specifically want scale-to-zero
- you would rather pay monthly than yearly

If it is purely **cost** that worries you, tell me the actual number you are trying to stay under, and I will tell you honestly whether any option meets it — including whether a cheaper VPS tier than KVM 1 exists that still runs this fine (it does: this app is happy on 512 MB).
