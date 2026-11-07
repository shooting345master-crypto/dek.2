#!/usr/bin/env bash
# ============================================================================
#  FALCON FITNESS — one-command go-live installer (written for phones too)
# ============================================================================
#
#  Run ON THE VPS as root, from inside the unzipped project folder:
#
#      sudo bash deploy/go-live.sh
#
#  It asks four questions, then does everything:
#    venv + dependencies, .env, systemd service, Nginx site, reload,
#    and (if you say yes) a free HTTPS certificate.
#
#  Safe to re-run: it updates what it already made instead of duplicating it,
#  and it NEVER touches an existing data/falcon.db or an existing .env.
#
#  Nothing here is mandatory-guessable: press Enter to accept the default shown
#  in [brackets].
# ============================================================================

set -u -o pipefail

say()  { printf '\n\033[1;36m▸ %s\033[0m\n' "$*"; }
ok()   { printf '  \033[1;32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[1;33m!\033[0m %s\n' "$*"; }
die()  { printf '\n\033[1;31m  ✗ %s\033[0m\n\n' "$*" >&2; exit 1; }

[ "$(id -u)" = "0" ] || die "Run this as root:  bash deploy/go-live.sh"

# Run a command as the site's user. When the installer itself runs as a normal
# user with sudo this is "sudo -u"; as root it is a direct call. Without this
# distinction the venv ends up owned by the wrong user and pip fails.
run_as() {
  if [ "$(id -un)" = "$RUN_USER" ]; then
    "$@"
  elif [ "$(id -u)" = "0" ]; then
    su -s /bin/sh -c "$(printf '%q ' "$@")" "$RUN_USER"
  else
    sudo -u "$RUN_USER" "$@"
  fi
}

APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SYSTEM_PY=0
DEFAULT_USER="${SUDO_USER:-root}"
[ "$DEFAULT_USER" = "root" ] && DEFAULT_USER="falcon"

printf '\n'
printf '  ┌──────────────────────────────────────────────┐\n'
printf '  │   FALCON FITNESS  ·  go-live installer       │\n'
printf '  └──────────────────────────────────────────────┘\n'
printf '  Project folder: %s\n' "$APP_DIR"

[ -f "$APP_DIR/app.py" ] || die "app.py not found in $APP_DIR — run this from inside the unzipped folder."

ask() {  # ask <prompt> <default> <var>
  local prompt="$1" def="$2" __v
  if [ -n "$def" ]; then
    printf '\n  %s [%s]: ' "$prompt" "$def"
  else
    printf '\n  %s: ' "$prompt"
  fi
  read -r __v || __v=""
  [ -z "$__v" ] && __v="$def"
  printf -v "$3" '%s' "$__v"
}

# ---- answers (env vars let you skip the questions) -------------------------
DOMAIN="${GO_LIVE_DOMAIN:-}"
[ -z "$DOMAIN" ] && ask "Your domain name (no https://)" "fitn.co.in" DOMAIN
ASK_EMAIL="${GO_LIVE_EMAIL:-}"
if [ -z "$ASK_EMAIL" ]; then
  ask "Admin email address" "dinoalvez42@gmail.com" ASK_EMAIL
fi
RUN_USER="${GO_LIVE_USER:-}"
if [ -z "$RUN_USER" ]; then
  printf '\n  Creating a safe user to run the site (no password needed, no login).\n'
  if id falcon >/dev/null 2>&1; then
    RUN_USER=falcon
    ok "user 'falcon' already exists"
  else
    useradd --create-home --shell /usr/sbin/nologin falcon 2>/dev/null \
      || useradd --create-home --shell /bin/bash falcon
    ok "user 'falcon' created"
  fi
fi
[ "$RUN_USER" = "root" ] && warn "Running the site as root is not ideal, but continuing."
ADMIN_PW="${GO_LIVE_ADMIN_PASSWORD:-}"
if [ -z "$ADMIN_PW" ]; then
  printf '\n  Choose the ADMIN PANEL password (typing is hidden): '
  read -rs ADMIN_PW || true; printf '\n'
fi
[ "${#ADMIN_PW}" -ge 10 ] || die "Password must be at least 10 characters. Nothing was changed."

# ---- is the project somewhere the site's user can actually reach? -----------
# Hostinger's browser terminal drops you in /root, and /root is mode 700: only
# root can enter it. If the site runs as a normal user there, systemd fails with
# the confusing "Changing to the requested working directory failed" and the
# site 502s. Move it somewhere sensible and carry on automatically.
if [ "$(id -u)" = "0" ] && [ "$RUN_USER" != "root" ]; then
  if ! su -s /bin/sh -c "test -x '$APP_DIR'" "$RUN_USER" >/dev/null 2>&1; then
    NEW_DIR="/home/$RUN_USER/app"
    say "This folder ($APP_DIR) is not reachable by the user '$RUN_USER'."
    say "Moving the site to $NEW_DIR and continuing from there."
    mkdir -p "$NEW_DIR" || die "Could not create $NEW_DIR"
    cp -a "$APP_DIR/." "$NEW_DIR"/ || die "Could not copy the files to $NEW_DIR"
    chown -R "$RUN_USER":"$RUN_USER" "$NEW_DIR" || true
    ok "copied to $NEW_DIR"
    export GO_LIVE_DOMAIN="$DOMAIN" GO_LIVE_EMAIL="$ASK_EMAIL" \
           GO_LIVE_USER="$RUN_USER" GO_LIVE_ADMIN_PASSWORD="$ADMIN_PW"
    echo
    echo "  Continuing automatically — please wait..."
    exec bash "$NEW_DIR/deploy/go-live.sh"
  fi
fi

# ---- system packages (installed for you, so you never run apt by hand) -----
MISSING=0
for c in python3 sed curl g++; do
  command -v "$c" >/dev/null 2>&1 || MISSING=1
done
command -v nginx >/dev/null 2>&1 || MISSING=1
if [ "$MISSING" = "1" ]; then
  say "Installing the system packages this needs (2-4 minutes, be patient)"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq || warn "apt update had a warning — continuing"
  apt-get install -y -qq python3 python3-venv python3-pip nginx g++ unzip curl certbot python3-certbot-nginx \
    || die "Could not install the packages. Check the internet connection on the server."
  ok "packages installed"
else
  ok "system packages already present"
fi
python3 -m venv --help >/dev/null 2>&1 || die "python3-venv is missing and could not be installed."

# ---- ownership -------------------------------------------------------------
say "Fixing file ownership for $RUN_USER"
id "$RUN_USER" >/dev/null 2>&1 || die "User '$RUN_USER' does not exist. Create it:  adduser $RUN_USER"
chown -R "$RUN_USER":"$RUN_USER" "$APP_DIR"
ok "owned by $RUN_USER"

# Nginx (the web server user, usually www-data) has to be able to WALK INTO
# this folder to serve the CSS and images directly. A freshly created home
# directory is often mode 700, which blocks it -- the site then loads with no
# styling and no badge, while the server seems fine. Add traverse-only
# permission on every parent, never read or write.
_trav="$APP_DIR"
while [ -n "$_trav" ] && [ "$_trav" != "/" ]; do
  chmod o+x "$_trav" 2>/dev/null || true
  _trav="$(dirname "$_trav")"
done
chmod -R o+rX "$APP_DIR/static" 2>/dev/null || true
ok "web server can reach the static files"

# ---- python environment ----------------------------------------------------
say "Creating the Python environment (this is the slow step, 1-3 min)"
install_deps() {
  if [ ! -x "$APP_DIR/venv/bin/python" ]; then
    run_as python3 -m venv "$APP_DIR/venv" || return 1
  fi
  run_as "$APP_DIR/venv/bin/pip" install --quiet --upgrade pip || warn "pip upgrade skipped"
  run_as "$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt" || return 1
}

if ! install_deps; then
  warn "A virtual environment failed here (common on a cut-down container)."
  warn "Retrying with system-wide Python instead — the site works exactly the same."
  command -v pip3 >/dev/null 2>&1 || apt-get install -y -qq python3-pip || true
  python3 -m pip install --quiet --upgrade pip || true
  python3 -m pip install --quiet -r "$APP_DIR/requirements.txt" \
    || die "Dependency install failed. Check the server's internet connection."
  SYSTEM_PY=1
fi
ok "Flask + Pillow + gunicorn installed"

# ---- C++ engine ------------------------------------------------------------
if [ -f "$APP_DIR/bin/falcon-engine" ]; then
  chmod +x "$APP_DIR/bin/falcon-engine"
  ok "C++ engine marked executable"
fi
if command -v g++ >/dev/null 2>&1 && [ -f "$APP_DIR/engine/main.cpp" ]; then
  if run_as g++ -O3 -std=c++17 -o "$APP_DIR/bin/falcon-engine" "$APP_DIR/engine/main.cpp" 2>/dev/null; then
    chmod +x "$APP_DIR/bin/falcon-engine"
    ok "C++ engine compiled natively on this server"
  else
    warn "C++ engine could not compile — the site will use its Python fallback"
  fi
else
  warn "No g++ on this server; the site will use its Python fallback (works fine)"
fi

# ---- .env ------------------------------------------------------------------
ENV_FILE="$APP_DIR/.env"
if [ -f "$ENV_FILE" ]; then
  ok ".env already exists — left untouched (your settings are safe)"
else
  say "Writing .env"
  SALT1="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
  SALT2="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
  cat > "$ENV_FILE" <<EOF
# Created by deploy/go-live.sh on $(date '+%Y-%m-%d %H:%M')
FALCON_DB_PATH=$APP_DIR/data/falcon.db
FALCON_HTTPS=1
FALCON_ADMIN_EMAIL=$ASK_EMAIL
FALCON_ADMIN_PASSWORD=$ADMIN_PW
FALCON_IP_SALT=$SALT1
FALCON_OTP_SALT=$SALT2
EOF
  chown "$RUN_USER":"$RUN_USER" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  ok ".env written (readable only by $RUN_USER)"
  printf '    Admin password stored in .env — keep that file private.\n'
fi

mkdir -p "$APP_DIR/data"
chown -R "$RUN_USER":"$RUN_USER" "$APP_DIR/data"

# ---- systemd ---------------------------------------------------------------
say "Installing the background service"
UNIT=/etc/systemd/system/falcon.service
if [ -x "$APP_DIR/venv/bin/gunicorn" ] && [ "$SYSTEM_PY" = "0" ]; then
  EXEC_BIN="$APP_DIR/venv/bin/gunicorn"
  EXEC_PATH="$APP_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
else
  EXEC_BIN="$(command -v gunicorn || echo /usr/local/bin/gunicorn)"
  EXEC_PATH="/usr/local/bin:/usr/bin:/bin"
fi
sed -e "s|/home/falcon/app/falcon-fitness|$APP_DIR|g" \
    -e "s|^User=falcon$|User=$RUN_USER|" \
    -e "s|^Group=falcon$|Group=$RUN_USER|" \
    -e "s|^ExecStart=.*/gunicorn |ExecStart=$EXEC_BIN |" \
    -e "s|^Environment=\"PATH=.*\"$|Environment=\"PATH=$EXEC_PATH\"|" \
    "$APP_DIR/deploy/falcon.service" > "$UNIT"
systemctl daemon-reload
systemctl enable falcon >/dev/null 2>&1
systemctl restart falcon || die "The service failed to start. See:  journalctl -u falcon -n 40"
sleep 3
if systemctl is-active --quiet falcon; then
  ok "falcon.service is running"
else
  systemctl --no-pager status falcon | tail -20
  die "The service is not running. The log above says why."
fi

# ---- nginx -----------------------------------------------------------------
say "Installing the Nginx site for $DOMAIN"
SITE=/etc/nginx/sites-available/falcon
sed -e "s|/home/falcon/app/falcon-fitness|$APP_DIR|g" \
    -e "s|fitn.co.in|$DOMAIN|g" \
    "$APP_DIR/deploy/nginx-falcon.conf" > "$SITE"
ln -sf "$SITE" /etc/nginx/sites-enabled/falcon
rm -f /etc/nginx/sites-enabled/default
if nginx -t >/tmp/nginx-test.log 2>&1; then
  ok "Nginx config is valid"
else
  cat /tmp/nginx-test.log
  die "Nginx config is invalid — not reloading. The message above says which line."
fi
systemctl reload nginx 2>/dev/null || systemctl restart nginx || warn "Could not reload Nginx automatically"
ok "Nginx reloaded"

# ---- what the app reports --------------------------------------------------
say "Checking the app answers locally"
HEALTH="$(curl -fsS --max-time 10 http://127.0.0.1:8000/healthz 2>/dev/null || true)"
if [ -n "$HEALTH" ]; then
  printf '  %s\n' "$HEALTH"
  case "$HEALTH" in
    *'"engine":"c++"'*) ok "C++ engine live" ;;
    *) warn "Running the Python fallback — the site still works" ;;
  esac
else
  warn "No answer from 127.0.0.1:8000 — check:  journalctl -u falcon -n 40"
fi

# ---- DNS sanity check ------------------------------------------------------
say "Checking that $DOMAIN points at this server"
SERVER_IP="$(curl -fsS --max-time 8 https://api.ipify.org 2>/dev/null || true)"
DNS_IP="$(getent hosts "$DOMAIN" 2>/dev/null | awk '{print $1; exit}')"
printf '  this server : %s\n' "${SERVER_IP:-unknown}"
printf '  %s : %s\n' "$DOMAIN" "${DNS_IP:-no DNS record found}"
DNS_OK=0
if [ -n "$SERVER_IP" ] && [ "$DNS_IP" = "$SERVER_IP" ]; then
  DNS_OK=1
  ok "DNS is correct"
else
  warn "DNS is not pointing here yet. HTTPS cannot be issued until it does."
  printf '     Fix the A record at your domain registrar, wait, then run:\n'
  printf '       sudo certbot --nginx -d %s -d www.%s\n' "$DOMAIN" "$DOMAIN"
fi

# ---- HTTPS -----------------------------------------------------------------
if [ "$DNS_OK" = "1" ] && [ "${GO_LIVE_SKIP_CERTBOT:-0}" != "1" ]; then
  if command -v certbot >/dev/null 2>&1; then
    printf '\n'
    ask "Get a free HTTPS certificate now? (y/n)" "y" DO_TLS
    if [ "$DO_TLS" = "y" ] || [ "$DO_TLS" = "Y" ]; then
      say "Requesting the certificate"
      certbot --nginx -d "$DOMAIN" -d "www.$DOMAIN" --non-interactive --agree-tos \
              -m "$ASK_EMAIL" --redirect \
        && ok "HTTPS enabled — https://$DOMAIN" \
        || warn "certbot did not finish. Re-run:  sudo certbot --nginx -d $DOMAIN -d www.$DOMAIN"
    fi
  else
    warn "certbot is not installed. Get HTTPS with:  sudo apt install -y certbot python3-certbot-nginx"
  fi
fi

# ---- done ------------------------------------------------------------------
printf '\n'
printf '  ┌──────────────────────────────────────────────┐\n'
printf '  │   DONE                                        │\n'
printf '  └──────────────────────────────────────────────┘\n'
printf '  Site      : http://%s\n' "$DOMAIN"
printf '  Admin     : http://%s/admin/login\n' "$DOMAIN"
printf '  Email     : %s\n' "$ASK_EMAIL"
printf '\n'
printf '  Useful commands:\n'
printf '    systemctl status falcon          is it running?\n'
printf '    journalctl -u falcon -n 50       what went wrong\n'
printf '    systemctl restart falcon         after changing any file\n'
printf '\n'
printf '  Next: open the site on your phone and skim the checklist in\n'
printf '  GOING-LIVE-HOSTINGER.md (Part 10).\n\n'
