# FALCON FITNESS — website + training engine

A complete, self-contained gym website built on four languages, each doing the job
it is actually good at. Runs entirely on your own machine — no CDN, no fonts,
no trackers, no external calls.

```
HTML      structure & semantic markup (server-rendered Jinja templates)
Python    the service layer: routing, validation, SQLite persistence
C++       the numeric engine: programming, macros, plate maths, 1RM, ACWR
JS        the interaction layer: state, animation, fetch
```

---

## Run it

**On a computer** (Windows / Mac / Linux):
```bash
cd falcon-fitness
./run.sh
```

**Using Visual Studio Code on Windows or macOS?** There is a complete,
tested step-by-step guide — including the Windows C++ caveat, the virtual
environment, and how to debug — in **[VSCODE.md](VSCODE.md)**. The project
ships with a `.vscode` folder already configured, so pressing **F5** starts
the site.

**On an Android phone, no computer at all:** see **[ANDROID-TERMUX.md](ANDROID-TERMUX.md)**
— install Termux from F-Droid, unzip the project, run `bash termux-setup.sh`.

Then open **http://127.0.0.1:5000**

Two separate sign-in doors:

| Who | Address | Password |
|---|---|---|
| **Admin (owner)** | `/admin/login` | `Falcon.fitness29` — change it on first sign-in |
| **Member** | `/login` | `member_FF_<first name, lower case>` — e.g. `member_FF_rahul` |

Admin email is `dinoalvez42@gmail.com` unless you set `FALCON_ADMIN_EMAIL`.
Full walkthrough in **[ADMIN-GUIDE.md](ADMIN-GUIDE.md)**.

`run.sh` installs Flask if it is missing, compiles the C++ engine, and starts the
server. If you would rather do it by hand:

```bash
pip install -r requirements.txt
g++ -O3 -std=c++17 -o bin/falcon-engine engine/main.cpp
python3 app.py
```

**Requirements:** Python 3.10+ and any C++17 compiler (`g++`, `clang++`).
Receipt screening also needs **Pillow** (`pip install Pillow`). If Pillow is
missing the site still runs — receipts are simply flagged as not screened.
If no compiler is found the site still runs — `fallback_engine.py` mirrors the
C++ logic and produces byte-identical output, so nothing ever hard-fails.

The database is created on first boot at `data/falcon.db`. Delete that file to
reset bookings and leads.

---

## What is on the site

| Section | What it does |
|---|---|
| **Hero** | Live local clock, open/closed state, engine build badge, real facility photo |
| **The club** | Air conditioning, equipment, hygiene and parking — the real amenity list |
| **Program builder** | 4-step wizard → 8-week periodised block with macros, session tables, downloadable plan |
| **Floor tools** | Plate loader, 1RM lab, strength standards, ACWR recovery screen, hydration |
| **Membership** | Real price sheet — general, PT single/duo, couple, student, friends, day pass |
| **Facility** | Real photography of the Kestopur floor plus the full amenity list |
| **Visit** | Address, both phone numbers, Instagram, Google Maps, enquiry form |
| **Enquiry form** | Validates, saves to SQLite, emails you if SMTP is configured |
| **Legal** | `/privacy` and `/terms` — DPDP-aligned, refund policy, custom 404 |
| **Command palette** | `⌘K` / `Ctrl+K` / `/` — jump to any section or run any tool |

### UI details worth trying
- Type `⌘K` and hit **"Generate my training block"**
- Drag the target weight on the plate loader — the SVG barbell re-renders per side
- Click any week in the **Periodisation** strip to read that week's prescription
- Log a few sessions in the **ACWR** tool, then watch the ratio band change
- Tab through the builder — every control is keyboard reachable with visible focus

---

## The C++ engine

`engine/main.cpp` — zero dependencies, single translation unit, emits JSON.

```bash
./bin/falcon-engine plan --goal strength --days 4 --level intermediate \
                         --age 29 --sex m --weight 74 --height 174 --activity 1.55
./bin/falcon-engine plates --total 142.5 --bar 20
./bin/falcon-engine e1rm --weight 120 --reps 3
./bin/falcon-engine standards --lift squat --weight 160 --bw 78 --sex m
./bin/falcon-engine acwr --history 10,12,0,14,11,0,12,13,0,12,15,0,26,28
```

| Command | Model |
|---|---|
| `plan` | Mifflin-St Jeor → activity → goal delta; macro split by g/kg; split library by training days; exercise selection by movement pattern, tier and experience; 8-week accumulation → deload → intensification → peak |
| `plates` | Greedy per-side loading against 25/20/15/10/5/2.5/1.25 kg |
| `e1rm` | Weighted ensemble of Epley, Brzycki and Lombardi; full percentage table |
| `standards` | Bodyweight-ratio bands by lift and sex |
| `acwr` | Trailing 7-day vs mean daily tonnage, banded against the 0.8–1.3 sweet spot |

---

## JSON API

| Method | Endpoint | Body |
|---|---|---|
| POST | `/api/plan` | `goal, days, level, age, sex, weight, height, activity` |
| POST | `/api/plates` | `total, bar` |
| POST | `/api/e1rm` | `weight, reps` |
| POST | `/api/standards` | `lift, weight, bw, sex` |
| POST | `/api/acwr` | `history` (comma-separated daily loads) |
| POST | `/api/book` | `class_id, session_date, name, email` |
| POST | `/api/lead` | `name, email, phone, goal, message` |
| POST | `/api/checkin` | `member, kind, load` |
| GET | `/api/classes`, `/api/checkin/stats`, `/api/engine/status` | — |

---

## Editing content

- **Classes & coaches** → `app.py` (`SEED_CLASSES`), `templates/index.html`
- **Colours** → the `:root` block at the top of `static/css/style.css`
  (the palette is sampled straight from your crest: `#5c0b14` oxblood → `#c8374a` ember)
- **Engine logic** → `engine/main.cpp`, then rebuild:
  `g++ -O3 -std=c++17 -o bin/falcon-engine engine/main.cpp`
  (mirror the change in `fallback_engine.py` if you want it to work without a compiler)

## Note on the imagery

The four photographs in `static/img/` are stock shots graded into a single
maroon duotone so the page reads as one campaign. Swap in your own facility
photos at the same filenames (`facility.jpg`, `floor.jpg`, `platform.jpg`,
`racks.jpg`) and they will inherit the grade — or drop the `filter`/duotone and
use them straight.

To serve it to other devices on your network:

```bash
python3 app.py   # already binds 0.0.0.0 — hit http://<your-lan-ip>:5000
```

---

## Deploying (phone access without your laptop)

This folder is deployment-ready — `Dockerfile`, `render.yaml`, `fly.toml`,
`/healthz`, `$PORT` and `$FALCON_DB_PATH` support are all included.
See **[DEPLOY.md](DEPLOY.md)** for step-by-step instructions on Render,
Fly.io and Google Cloud Run, plus the pre-launch checklist.
