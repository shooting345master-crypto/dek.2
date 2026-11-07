#!/data/data/com.termux/files/usr/bin/bash
# =============================================================================
#  FALCON FITNESS — one-shot Android / Termux installer
#  ---------------------------------------------------------------------------
#  Run this from inside Termux, in the folder where you unzipped the project:
#      bash termux-setup.sh
#
#  It installs the toolchain, compiles the C++ engine, and starts the site on
#  the phone itself at http://127.0.0.1:5000
# =============================================================================
set -e

# Always run from the folder this script lives in (it uses relative paths).
# BASH_SOURCE[0] is the script's own path — works no matter where it's called from.
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" && pwd)"
cd "$HERE" || { echo "cannot cd into $HERE"; exit 1; }

BANNER() { printf '\n\033[38;5;160m▸ %s\033[0m\n' "$1"; }

if [ ! -f app.py ]; then
  echo "✗ app.py not found. cd into the falcon-fitness folder first."
  echo "  e.g.  cd ~/falcon-fitness"
  exit 1
fi

if ! command -v pkg >/dev/null 2>&1; then
  echo "✗ 'pkg' not found — this script must run inside Termux (from F-Droid)."
  exit 1
fi

BANNER "Step 1/4 — updating package list"
yes | pkg update -y >/dev/null 2>&1 || true

BANNER "Step 2/4 — installing python, clang, unzip"
pkg install -y python clang unzip 2>&1 | tail -3 || true

if ! command -v python >/dev/null 2>&1; then
  echo "✗ python install failed. Run:  pkg install python"
  exit 1
fi

BANNER "Step 3/5 — installing Flask"
python -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
python -m pip install --quiet flask || { echo "✗ pip install flask failed"; exit 1; }

# Pillow reads uploaded payment receipts. On Termux the prebuilt wheel is the
# only realistic way to get it (building it from source needs libjpeg, zlib and
# a long compile), so we ask for the binary wheel explicitly and fall back
# gracefully. The site runs without it -- receipts just go to manual review.
BANNER "Step 4/5 — installing Pillow (for receipt screening)"
if python -c "import PIL" >/dev/null 2>&1; then
  echo "  ✓ Pillow already installed"
else
  if python -m pip install --quiet --only-binary=:all: Pillow 2>/tmp/pil.log; then
    echo "  ✓ Pillow installed (prebuilt wheel)"
  elif python -m pip install --quiet Pillow 2>>/tmp/pil.log; then
    echo "  ✓ Pillow installed"
  else
    echo "  ! Pillow could not be installed — receipt screening will be OFF."
    echo "    The site still works; every receipt just goes to manual review."
    echo "    To retry later:   pkg install libjpeg-turbo zlib && pip install Pillow"
    echo "    Last error:"
    tail -3 /tmp/pil.log | sed 's/^/      /'
  fi
fi

BANNER "Step 5/5 — compiling the C++ training engine"
mkdir -p bin
BUILT=0
for CXX in g++ clang++ c++; do
  if command -v "$CXX" >/dev/null 2>&1; then
    if "$CXX" -O3 -std=c++17 -o bin/falcon-engine engine/main.cpp 2>/tmp/build.log; then
      echo "  ✓ compiled with $CXX"
      BUILT=1
      break
    else
      echo "  ! $CXX failed, trying next…"
      tail -3 /tmp/build.log
    fi
  fi
done
if [ "$BUILT" -eq 0 ]; then
  echo "  ! No working compiler — the site will run on the Python mirror."
  echo "    Everything still works, just without the C++ engine."
fi

# keep Android from freezing Termux while you browse the site
command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock && \
  echo "  ✓ wake-lock held (Termux won't sleep)"

# tell the operator plainly whether screening is on
if python -c "import PIL" >/dev/null 2>&1; then
  echo "  ✓ receipt screening: ON"
else
  echo "  ! receipt screening: OFF (Pillow missing) — receipts go to manual review"
fi

PORT="${PORT:-5000}"
cat <<EOF

────────────────────────────────────────────────────────────
  FALCON FITNESS is starting on THIS phone.

  Open Chrome and go to:   http://127.0.0.1:${PORT}
  (or type: localhost:${PORT})

  To stop the server:      press Ctrl + C
────────────────────────────────────────────────────────────

EOF

PORT="$PORT" exec python app.py
