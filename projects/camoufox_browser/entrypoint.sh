#!/bin/sh
set -e

VNC_PORT="${VNC_PORT:-6080}"
SCREEN_GEOMETRY="${SCREEN_WIDTH:-1920}x${SCREEN_HEIGHT:-1080}x${SCREEN_DEPTH:-24}"

export DISPLAY=:99
Xvnc :99 \
    -screen 0 "$SCREEN_GEOMETRY" \
    -websocketPort "$VNC_PORT" \
    -httpd /usr/share/kasmvnc/www \
    -sslOnly=0 \
    -SecurityTypes None \
    -DisableBasicAuth=1 \
    -UseIPv6=0 \
    -interface 0.0.0.0 &

for _ in $(seq 1 100); do
    [ -e /tmp/.X11-unix/X99 ] && break
    sleep 0.1
done
if [ ! -e /tmp/.X11-unix/X99 ]; then
    echo "Xvnc failed to create display :99" >&2
    exit 1
fi

matchbox-window-manager -use_titlebar no &

exec run_server
