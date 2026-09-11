#!/bin/sh

VNC_PORT="${VNC_PORT:-6080}"
CDP_PORT="${CDP_PORT:-9222}"
CDP_INTERNAL_PORT=$((CDP_PORT + 1))

TZ="${TZ:-UTC}"
if [ ! -f "/usr/share/zoneinfo/$TZ" ]; then
    TZ=UTC
fi
export TZ

export DISPLAY=:99
Xvnc :99 \
    -screen 0 1920x1080x24 \
    -websocketPort "$VNC_PORT" \
    -httpd /usr/share/kasmvnc/www \
    -sslOnly=0 \
    -SecurityTypes None \
    -DisableBasicAuth=1 \
    -UseIPv6=0 \
    -interface 0.0.0.0 &

sleep 2

matchbox-window-manager -use_titlebar no &

(
    while true; do
        rm -f ~/.config/chromium/Singleton* 2>/dev/null

        chromium \
            --remote-debugging-port="$CDP_INTERNAL_PORT" \
            --remote-debugging-host=127.0.0.1 \
            --no-sandbox \
            --test-type \
            --deny-permission-prompts \
            --no-first-run \
            --no-service-autorun \
            --no-default-browser-check \
            --homepage=about:blank \
            --no-pings \
            --password-store=basic \
            --disable-infobars \
            --disable-breakpad \
            --disable-dev-shm-usage \
            --disable-session-crashed-bubble \
            --disable-search-engine-choice-screen \
            --window-position=0,0 \
            --start-maximized \
            --disable-blink-features=AutomationControlled \
            --disable-features=IsolateOrigins,site-per-process
        sleep 1
    done
) &

exec socat TCP-LISTEN:"$CDP_PORT",fork,reuseaddr TCP:127.0.0.1:"$CDP_INTERNAL_PORT"