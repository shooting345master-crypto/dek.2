#!/data/data/com.termux/files/usr/bin/bash
# Everyday launcher — run this after the first-time setup.
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" && pwd)"
cd "$HERE" || exit 1
command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock
echo ""
echo "  FALCON FITNESS → http://127.0.0.1:5000"
echo "  stop with Ctrl+C"
echo ""
exec python app.py
