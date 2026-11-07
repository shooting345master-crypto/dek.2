# Running Falcon Fitness in Visual Studio Code

Everything you need to open this project in VS Code on **Windows** or **macOS**,
run it, edit it, and not break it. Takes about ten minutes the first time.

No build step, no npm, no frameworks. It is plain Python, HTML, CSS and one C++
file.

---

## Contents

1. [Install the three things you need](#1-install-the-three-things-you-need)
2. [Open the project](#2-open-the-project)
3. [Set up the virtual environment](#3-set-up-the-virtual-environment)
4. [Run the site](#4-run-the-site)
5. [The C++ engine on Windows — read this](#5-the-c-engine-on-windows--read-this)
6. [Recommended VS Code extensions](#6-recommended-vs-code-extensions)
7. [Where everything lives](#7-where-everything-lives)
8. [Settings you can change in .env](#8-settings-you-can-change-in-env)
9. [Common tasks](#9-common-tasks)
10. [When something goes wrong](#10-when-something-goes-wrong)
11. [Git and backing up](#11-git-and-backing-up)
12. [What NOT to touch](#12-what-not-to-touch)

---

## 1. Install the three things you need

### Python 3.10 or newer

**Windows** — open the Microsoft Store, search **Python 3.12**, install it.
Or download from [python.org](https://www.python.org/downloads/) and **tick
"Add python.exe to PATH"** on the first screen of the installer. That tick box
matters; without it nothing else works.

**macOS** — either download from [python.org](https://www.python.org/downloads/),
or if you have Homebrew:

```
brew install python
```

Check it worked. Open Terminal (macOS) or Command Prompt (Windows) and run:

```
python --version
```

You want `Python 3.10` or higher. On macOS the command may be `python3` instead
of `python` — use whichever answers.

### Visual Studio Code

Download from [code.visualstudio.com](https://code.visualstudio.com/) and install
it normally.

### A C++ compiler — optional, but good to have

This is only for the training-program engine. **The site works fully without it**,
using the Python mirror, with byte-identical output. Skip this if you like; come
back to it later.

**Windows** — installing the Microsoft C++ build tools is a 6 GB download. If you
already have Visual Studio or "Build Tools for Visual Studio" installed you have
it. Otherwise read [section 5](#5-the-c-engine-on-windows--read-this) first — on
Windows the prebuilt Linux binary in this project **will not run**, and you do not
need it to.

**macOS** — one command, it will prompt you to install the developer tools:

```
xcode-select --install
```

---

## 2. Open the project

1. Unzip `falcon-fitness.zip`. You get a folder called **`falcon-fitness`**.
2. Put it somewhere sensible and permanent — `Documents\falcon-fitness` on
   Windows, `~/falcon-fitness` on macOS. Not inside your Downloads folder, which
   gets cleaned out.
3. In VS Code: **File → Open Folder…** and choose that `falcon-fitness` folder.

You should now see `app.py`, `README.md`, `templates`, `static` and the rest in
the Explorer panel on the left.

> **Open the folder, not the zip.** If VS Code asks "do you trust the authors of
> the files in this folder?" choose **Yes, I trust the authors** — otherwise the
> integrated terminal and debugging will not work properly.

---

## 3. Set up the virtual environment

A virtual environment keeps this project's Python packages separate from
everything else on your computer. Do this once per project.

### Open the terminal in VS Code

**Terminal → New Terminal**, or press `` Ctrl+` `` (Windows) / `` Cmd+` `` (macOS).

The terminal opens already inside your project folder. Confirm with:

```
dir
```
on Windows, or
```
ls
```
on macOS. You should see `app.py` in the list.

### Create and activate it

**Windows (Command Prompt — the default terminal):**

```
python -m venv .venv
.venv\Scripts\activate
```

**Windows (PowerShell)** — if VS Code opened PowerShell instead:

```
python -m venv .venv
.venv\Scripts\Activate.ps1
```

If PowerShell refuses with *"running scripts is disabled on this system"*, run
this once and try again:

```
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

**macOS:**

```
python3 -m venv .venv
source .venv/bin/activate
```

You will know it worked when your prompt gains a **`(.venv)`** at the front.

### Install the packages

```
pip install -r requirements.txt
```

This installs Flask (the web server) and Pillow (reads uploaded receipts). Takes
a minute or two.

### Tell VS Code to use it

1. Press **Ctrl+Shift+P** (Windows) or **Cmd+Shift+P** (macOS) to open the
   Command Palette.
2. Type **Python: Select Interpreter** and press Enter.
3. Choose the entry that says **`.venv`** in it, for example
   `Python 3.12.0 ('.venv': venv)`.

If you miss this step the Run button will use a different Python and complain
that Flask is missing.

---

## 4. Run the site

There are three ways. Use whichever you like — the first is the least trouble.

### Option A — the Run button (recommended)

This project ships with a `.vscode` folder already set up, so there is nothing to
configure.

1. Press **F5** — or open the **Run and Debug** panel on the left (the ▷ icon with
   a bug) and press the green ▷ button.
2. A dropdown at the top offers four ready-made options. Choose
   **Falcon Fitness — run the site**.
3. If VS Code ever asks you to pick a debugger, choose **Python Debugger**.

A terminal panel opens and you should see:

```
──────────────────────────────────────────────────────────────
  FALCON FITNESS  ·  local instance
  engine : C++ live  (prebuilt binary found)
  email  : not configured (leads saved locally only)

  On this computer   http://127.0.0.1:5000
  ...
  Admin login        http://127.0.0.1:5000/admin/login
  Member login       http://127.0.0.1:5000/login
  Receipts   : automatic screening ON
──────────────────────────────────────────────────────────────
```

3. **Ctrl+click** (Windows) or **Cmd+click** (macOS) the `http://127.0.0.1:5000`
   link to open the site in your browser.

To stop it: click in the terminal and press **Ctrl+C**.

**The four ready-made run options:**

| Option | What it does |
|---|---|
| Falcon Fitness — run the site | Normal start on port 5000 |
| Falcon Fitness — run on port 5001 | Use this when 5000 is already taken |
| Reset an account password | Runs `reset-password.py` (see section 9) |
| Build the C++ engine (macOS / Linux) | Compiles `engine/main.cpp` into `bin/` |

If the Run button complains it cannot find Flask, you skipped
[section 3](#3-set-up-the-virtual-environment) — the interpreter is not pointing
at `.venv`.

### Option B — the terminal

With the virtual environment active:

```
python app.py
```

That is all. Same banner, same address.

### Option C — the launcher script

```
run.sh
```
on macOS, or
```
bash run.sh
```
This checks your dependencies, builds the C++ engine if it can, and starts the
server. It is the most forgiving of the three.

### The admin password

```
Email    : dinoalvez42@gmail.com
Password : Falcon.fitness29
```

Sign in at **`/admin/login`**. Change the password from **My account** once you
are in — it is written in this file and in the guide, so it is not a secret.

> **Your first run creates `data/`.** That folder holds your database, your
> secret key and uploaded receipts. It is created automatically. **Back it up**
> (section 11) and never commit it to a public repository.

---

## 5. The C++ engine on Windows — read this

The project ships with a **prebuilt Linux binary** at `bin/falcon-engine`. On
Windows that file cannot run, and Windows will not tell you clearly why.

**This does not break anything.** `app.py` tries the binary, sees it fail, and
switches to `fallback_engine.py`, which is a Python rewrite of the same maths
producing identical output. The banner will say `engine : python mirror` — that
is expected and fine.

If you want the real C++ engine on Windows, you need a Windows compiler. The
easiest route:

1. Install **Visual Studio Build Tools** from Microsoft (free, about 6 GB),
   selecting the **"Desktop development with C++"** workload.
2. Install **MSYS2** from [msys2.org](https://www.msys2.org/), then in the MSYS2
   terminal run `pacman -S mingw-w64-x86_64-gcc`.
3. Add `C:\msys64\mingw64\bin` to your PATH.
4. In the project folder:

```
g++ -O3 -std=c++17 -o bin/falcon-engine engine/main.cpp
```

5. Restart the site. The banner should now say `engine : C++ live`.

On **macOS** it is much simpler, because `clang++` is a normal compiler:

```
clang++ -O3 -std=c++17 -o bin/falcon-engine engine/main.cpp
```

If your Mac has an Apple Silicon chip (M1/M2/M3), that produces a native binary
and everything works.

**Either way, you can ignore this section entirely.** The site is complete
without the C++ engine.

---

## 6. Recommended VS Code extensions

VS Code will suggest most of these when you open the folder. Accept the
suggestions, or install from the Extensions panel (**Ctrl+Shift+X**):

| Extension | Why |
|---|---|
| **Python** (Microsoft) | Running, debugging, and catching Python mistakes as you type |
| **Pylance** (Microsoft) | Comes with Python; makes autocomplete useful |
| **Jinja** (wholroyd) | Syntax highlighting for the `.html` templates, which are Jinja, not plain HTML |
| **HTML CSS Support** | Autocomplete for class names in the templates |
| **C/C++** (Microsoft) | Only if you plan to edit `engine/main.cpp` |

You do **not** need any React, Node, npm or bundler extensions. There is no build
step in this project.

---

## 7. Where everything lives

```
falcon-fitness/
│
├── app.py                  ← the whole web server: routes, database, security
├── membership.py           ← membership expiry, digital cards, revocation
├── receipt_check.py        ← the receipt image screening
├── sms_otp.py              ← one-time codes and SMS providers
├── fallback_engine.py      ← Python mirror of the C++ engine
├── reset-password.py       ← run this if you lose the admin password
│
├── engine/main.cpp         ← the C++ training-program engine
├── bin/falcon-engine       ← compiled binary (Linux build included)
│
├── templates/              ← the pages. Jinja templates.
│   ├── shell.html          ←   the outer frame every page extends
│   ├── index.html          ←   the home page (biggest file)
│   ├── login.html          ←   both sign-in doors
│   ├── account.html        ←   member area + digital card
│   ├── admin.html          ←   the owner panel
│   ├── register.html       ←   membership registration
│   ├── register_verify.html←   the OTP step
│   ├── privacy.html
│   ├── terms.html
│   └── 400/403/404.html
│
├── static/
│   ├── css/style.css       ← all styling, one file
│   ├── js/app.js           ← all interaction, one file
│   └── img/                ← your real photographs
│       └── real/           ←   the gym photos
│
├── data/                   ← CREATED ON FIRST RUN. Your database lives here.
│   ├── falcon.db           ←   members, payments, memberships, receipts
│   ├── secret.key          ←   keeps logins valid across restarts
│   └── receipts/           ←   uploaded receipt images
│
├── .vscode/                ← ready-made Run/Debug setup (already done for you)
│   ├── launch.json         ←   the four run options
│   ├── settings.json       ←   tells VS Code the templates are Jinja
│   └── extensions.json     ←   recommends the right extensions
│
├── .env                    ← your settings (you create this — see section 8)
├── .env.example            ← a template listing every setting
├── requirements.txt
├── run.sh
└── *.md                    ← the guides
```

### The three files you are most likely to edit

**`static/css/style.css`** — all colours, spacing and layout. The top of the file
defines the colour variables. Change `--crimson` and `--ember` and the whole site
changes accent colour.

**`templates/index.html`** — the wording of the home page. Find the section
comment like `<!-- ░░ HERO ░░ -->` and edit the text between them. It is ordinary
HTML.

**`app.py`** — only if you want to change behaviour, not appearance. Look for the
`@app.route("/something")` line for the page you care about.

---

## 8. Settings you can change in `.env`

Create a file called **exactly** `.env` (with the dot, no `.txt` on the end) in
the project folder, next to `app.py`.

> **Windows note:** Notepad will try to save it as `.env.txt`. Either choose
> "All Files" in the save dialog's *File type* dropdown, or create it from VS
> Code: **File → New File**, save as `.env`. VS Code handles it correctly.

Start by copying `.env.example`:

```
copy .env.example .env
```
on Windows, or
```
cp .env.example .env
```
on macOS.

Then edit it. Everything in it is optional; delete the `#` at the start of a line
to switch that setting on.

| Setting | What it does |
|---|---|
| `PORT=5000` | Change the port. Useful if something else is using 5000. |
| `FALCON_ADMIN_EMAIL` | Your admin sign-in email |
| `FALCON_ADMIN_PASSWORD` | Sets the admin password **on first run only** |
| `FALCON_SMTP_HOST` … | Gmail details, so enquiries email you |
| `FALCON_SMS_PROVIDER` / `_KEY` | Real SMS for one-time codes (needs DLT registration in India) |
| `FALCON_REQUIRE_LIVE_MEMBERSHIP=1` | Block lapsed members from signing in at all |
| `FALCON_SECRET_KEY` | Fixed session key instead of a generated one |
| `FALCON_HTTPS=1` | Only when the site is served over HTTPS |

**Real environment variables always win over `.env`.** So if you set `PORT` in
your terminal, that takes priority — handy when debugging.

**Restart the server after changing `.env`.** It is read once at startup.

---

## 9. Common tasks

### Change a price

Sign in as admin → **Prices** tab → edit the number → **Save**. It is live
immediately, and members see the new figure on their next page load. You do not
need to touch any file.

### Change wording on the home page

Open `templates/index.html`, find the text, edit it, save, then **refresh the
browser**. Templates are re-read on each request, so no restart is needed for
HTML changes.

### Change a colour

Open `static/css/style.css`. The colour variables are at the top:

```css
--crimson:   #9d1b2b;   /* the deep red of the primary buttons */
--ember:     #c8374a;   /* the lighter red used for accents and links */
```

Change them, save, refresh. Because the stylesheet URL carries a version stamp,
the browser will always fetch your new version — no cache problems.

### Add a member by hand

Admin → **Members** → fill in the *Add a member* form. Leave the password blank
and it becomes `member_FF_<firstname>`, shown to you in a green message right
after you create them.

### Reset the admin password

```
python reset-password.py
```

It lists the accounts, asks which one, asks for a new password twice. It does not
need the old password.

### Start over with an empty database

**Stop the server first**, then delete the `data` folder and start again. It is
rebuilt on next launch. **This deletes every member, payment and receipt.**

---

## 10. When something goes wrong

### `ModuleNotFoundError: No module named 'flask'`

The virtual environment is not active, or VS Code is using a different Python.

1. Look at your terminal prompt — does it show `(.venv)`? If not, activate it
   (section 3).
2. If it does, run `pip install -r requirements.txt` again.
3. Still failing: **Ctrl+Shift+P → Python: Select Interpreter** and pick the
   `.venv` one.

### `ModuleNotFoundError: No module named 'PIL'`

Pillow, which reads receipt images, is not installed:

```
pip install --only-binary=:all: Pillow
```

**The site runs without it.** Only the automatic receipt check switches off, and
the admin panel will say **NOT SCREENED** so you know to look at receipts
yourself.

### `Address already in use` / `Port 5000 is in use`

Something else is on port 5000 — often a previous copy of this app that did not
stop.

- Easiest: put `PORT=5001` in your `.env` and restart. The banner will show the
  new address.
- Or find and stop the old process. On macOS: `lsof -ti:5000 | xargs kill -9`.
  On Windows: `netstat -ano | findstr :5000`, note the PID, then
  `taskkill /PID <number> /F`.

### The site loads but everything looks unstyled

You are seeing a cached stylesheet. Do a hard refresh: **Ctrl+Shift+R**
(Windows) or **Cmd+Shift+R** (macOS).

### My changes to the CSS or JS do nothing

Same as above — hard refresh. If it still will not update, check you saved the
file (VS Code shows a dot on the tab if you did not).

### `engine : python mirror` in the banner

Expected on Windows, and harmless. See [section 5](#5-the-c-engine-on-windows--read-this).

### The receipt panel says NOT SCREENED

Pillow is missing. Install it, then press **Re-screen** on that registration.

### SQLite errors about a locked database

Two copies of the app are running against the same `data` folder. Stop the extra
one.

---

## 11. Git and backing up

### Initialise a repository (optional)

```
git init
git add .
git commit -m "Falcon Fitness website"
```

The included `.gitignore` already excludes `data/` and `.env`, so your database
and settings stay out of version control. **Leave that as it is** — committing
`data/falcon.db` to a public GitHub repository would publish every member's name,
phone number and payment history.

### The backup that actually matters

Your website code is replaceable. **Your members and payments are not.** Copy
these:

```
data/falcon.db        ← everything: members, payments, memberships, cards
data/secret.key       ← keeps existing logins working
data/receipts/        ← uploaded receipt images
```

On Windows, just copy the whole **`data`** folder to a USB stick or your Google
Drive once a week. That is a complete backup. Restoring is copying it back.

---

## 12. What NOT to touch

| Don't | Why |
|---|---|
| Don't edit `data/falcon.db` in a database browser while the site is running | SQLite will lock and the app will error |
| Don't commit `data/` or `.env` to a public repository | Members' personal data and your settings |
| Don't rename files in `templates/` or `static/` | `app.py` refers to them by name; the site will 500 |
| Don't delete `bin/falcon-engine` | It is fine if it does not run on Windows; the fallback handles it. Deleting it is also fine, but there is no reason to |
| Don't change `SECRET_KEY` casually | Every logged-in user gets signed out |
| Don't put real photos in `static/img/` root | The site expects them in `static/img/real/` |
| Don't remove the `pointer-events: none` rule on images | It is what stops long-press saving |

---

## Quick reference

```
Set up once:
    python -m venv .venv
    .venv\Scripts\activate          (Windows)
    source .venv/bin/activate       (macOS)
    pip install -r requirements.txt

Every time:
    python app.py

Then open:
    http://127.0.0.1:5000           the website
    http://127.0.0.1:5000/admin/login    owner sign-in
    http://127.0.0.1:5000/login          member sign-in

Admin:  dinoalvez42@gmail.com  /  Falcon.fitness29

Stop the server:
    Ctrl+C

Back up:
    copy the whole data/ folder
```

---

If something here is wrong or unclear, say so and it gets fixed. The rest of the
guides — `ADMIN-GUIDE.md` for running the club side, `DEPLOY.md` for putting it on
the internet — sit alongside this one.
