#!/usr/bin/env bash
# Falcon Fitness — one-command local launcher
set -e
cd "$(dirname "$0")"

echo "▸ Checking Python dependencies…"
python3 - <<'PY'
import importlib.util, sys
missing = [m for m in ("flask", "PIL") if importlib.util.find_spec(m) is None]
if missing:
    print("  missing: " + ", ".join(missing))
    sys.exit(1)
PY
if [ $? -ne 0 ]; then
  echo "  Installing what is missing (this can take a few minutes)…"
  python3 -m pip install --quiet -r requirements.txt || true
fi

echo "▸ Building the C++ engine…"
mkdir -p bin
for CXX in g++ clang++ c++; do
  if command -v "$CXX" >/dev/null 2>&1; then
    "$CXX" -O3 -std=c++17 -o bin/falcon-engine engine/main.cpp && echo "  built with $CXX" && break
  fi
done

echo "▸ Starting the server on http://127.0.0.1:5000"
exec python3 app.py
