# Falcon Fitness on your Android phone — no computer needed

Your phone will **host the site itself**. Termux gives Android a real Linux
terminal, so `127.0.0.1:5000` means "this phone". No Wi-Fi, no laptop, no cloud.

Total time: **10–15 minutes**, mostly waiting for downloads.

---

## Step 1 — Install Termux (the right one)

⚠️ **Do not use the Play Store version — it is abandoned and will fail.**

Get it from **F-Droid**:

1. Open Chrome on your phone → **https://f-droid.org/packages/com.termux/**
2. Download and install the APK
   (Android will warn about "unknown sources" — allow it for Chrome)

> Termux from F-Droid is required. The Play Store build is years out of date and
> cannot install current Python packages.

---

## Step 2 — Download the zip (do not extract it)

In **this chat**, tap **`falcon-fitness.zip`** to download it.

It lands in `Download/` on your phone. **Leave it as a .zip** — the terminal
will unpack it in Step 4. You do not need to extract it, and you do not need a
file manager.

## Step 3 — Open Termux and allow storage

In Termux, type this and press Enter:

```bash
termux-setup-storage
```

A popup asks for permission → tap **Allow**.

---

## Step 4 — Unpack, then install by hand (works with any zip version)

Unpack:

```bash
cd ~ && unzip -o ~/storage/downloads/falcon-fitness.zip
cd ~/falcon-fitness
ls
```

You must see **`app.py`**. If you do, the installer script is optional — these
two commands do the same thing and never fail on a missing helper file.

**A — install Python, a compiler and Flask** (~3–8 min, downloads about 150 MB):

```bash
pkg install -y python clang unzip && python -m pip install flask
```

**B — compile the engine and start the site:**

```bash
mkdir -p bin && ( g++ -O3 -std=c++17 -o bin/falcon-engine engine/main.cpp 2>/dev/null || clang++ -O3 -std=c++17 -o bin/falcon-engine engine/main.cpp || echo "engine: python fallback" ) && python app.py
```

If the engine line prints `engine: python fallback`, that is fine — the site
works identically, just without the C++ speed.

## Step 5 — Wait for it to finish

The installer prints four steps and takes **3–8 minutes** the first time
(it downloads ~150 MB). Do not close Termux.

When it finishes you'll see:

```
FALCON FITNESS is starting on THIS phone.
Open Chrome and go to:   http://127.0.0.1:5000
```

## Step 6 — Open it

Leave Termux running (don't swipe it away). Open **Chrome** and type:

```
127.0.0.1:5000
```

The site is now running **on your phone**, from your phone.

---

## Afterwards

**To start it again** (no reinstall needed) — one line, works from anywhere:

```bash
find /sdcard -maxdepth 5 -name start-falcon.sh -exec bash {} \;
```

**To stop it** — go back to Termux and press **Ctrl + C**
(in Termux the volume-down key acts as Ctrl).

**To see it on another device** on the same Wi-Fi, the server prints a second
address like `http://192.168.1.5:5000` — type that into the other device.

---

---

## Command reference (read this once, then forget it)

### The only one you normally need

```bash
cd ~/falcon-fitness && python app.py
```

Then open `127.0.0.1:5000`. No recompiling — `bin/falcon-engine` is already built.

### When to use what

| Situation | Command |
|---|---|
| Normal restart | `cd ~/falcon-fitness && python app.py` |
| Edited HTML / CSS / JS | restart (same command) |
| Edited `engine/main.cpp` | the compile line below |
| Termux home was wiped | restore line **once**, then compile, then run |
| Updating to a newer zip | the **merge** line below |

### Restore after Termux home is wiped

Run **once**, only if `~/falcon-fitness` no longer exists:

```bash
cp -r /sdcard/falcon-fitness/falcon-fitness ~/falcon-fitness && cd ~/falcon-fitness && ls
```

> ⚠️ Do not run this a second time while `~/falcon-fitness` already exists — it
> nests a duplicate copy inside itself (`~/falcon-fitness/falcon-fitness/`).
> It will not delete your edits, but it makes a mess.

### Updating files safely (keeps your edits AND your database)

```bash
cp -r /sdcard/falcon-fitness/falcon-fitness/. ~/falcon-fitness/
```

Note the `/.` on the source. This **merges** — refreshes code without deleting
`data/falcon.db`, so bookings and leads survive.

### Recompile the C++ engine

```bash
cd ~/falcon-fitness && mkdir -p bin && ( g++ -O3 -std=c++17 -o bin/falcon-engine engine/main.cpp 2>/dev/null || clang++ -O3 -std=c++17 -o bin/falcon-engine engine/main.cpp || echo "engine: python fallback" )
```

`engine: python fallback` is fine — the site works identically, just slower.

### Quoting gotchas

- If a command fails with `SyntaxError: invalid character '\u2018'`, your
  keyboard or notes app inserted "smart quotes". Retype with straight `"` or use
  single quotes: `python -c 'import flask'`
- Folder names containing spaces **must** be quoted: `cd "$HOME/my folder"`
- Avoid copy-pasting lines containing `$` into Termux — the `$` sometimes gets
  stripped, turning `$HOME` into `HOME`


## If something breaks

| Problem | Fix |
|---|---|
| `bash: termux-setup.sh: No such file` | You're in the wrong folder — redo Step 4 |
| `pkg: command not found` | You installed Termux from Play Store. Uninstall, reinstall from **F-Droid** |
| Chrome says "site can't be reached" | The Termux script stopped. Re-run `bash start-falcon.sh` and check for red errors |
| `Address already in use` | It's already running — just open Chrome, or press Ctrl+C in Termux first |
| Site works, then dies after a few minutes | Android killed Termux. The script holds a wake-lock, but also: Settings → Apps → Termux → Battery → **Unrestricted** |
| `clang: error` during compile | Fine — it falls back to the Python engine. Site still works fully |
| Downloads fail in `pkg install` | `pkg update` again, or switch from mobile data to Wi-Fi |

---

## Things worth knowing

- **This is a real server on your phone.** Nothing is uploaded anywhere.
- **Termux must stay open** while you browse — Android may pause it otherwise.
  The setup script holds a wake-lock to help; allow Termux "Unrestricted"
  battery use to be safe.
- **Bookings, leads and check-ins** are saved to a file on your phone at
  `data/falcon.db`. They persist between restarts.
- **Storage:** the whole project is ~5 MB, plus ~150 MB of Python and clang.

If any step produces an error, paste the exact red text here and I'll fix it.


---

## Updating to a newer build

If you already have the site working and just want the new files, copy them over
your existing folder **without** touching your `data/` folder (that holds your
members and payments):

```bash
cp -r /sdcard/falcon-fitness/falcon-fitness/. ~/falcon-fitness/
cd ~/falcon-fitness
pip install -r requirements.txt
python app.py
```

### "No module named 'PIL'" — what it means and how to fix it

`PIL` is Pillow, the library that reads uploaded receipt photos. It is a native
package, so pip has to download a prebuilt wheel for your phone's processor.

Install it with:

```bash
pip install --only-binary=:all: Pillow
```

`--only-binary=:all:` tells pip to use the prebuilt wheel instead of trying to
compile Pillow from source, which needs libjpeg and zlib and takes a long time on
a phone.

If that fails, install the prerequisites first and try again:

```bash
pkg install libjpeg-turbo zlib
pip install Pillow
```

**You do not have to fix this to use the site.** Without Pillow the website still
runs normally — home page, prices, logins, memberships, digital cards, expiry all
work. Only the automatic receipt check is switched off, and every receipt is
marked **NOT SCREENED** in the admin panel so you know to look at it yourself.

### Checking what is installed

```bash
python -c "import flask, PIL; print('flask + Pillow OK')"
```

If that prints `flask + Pillow OK`, everything including receipt screening is on.
