#!/bin/sh
set -e

export BROWSER_SERVICE_CONTAINER_ID="${BROWSER_SERVICE_CONTAINER_ID:-$(hostname)}"

mkdir -p /tmp/nginx-client-body /tmp/nginx-proxy /tmp/nginx-fastcgi /tmp/nginx-uwsgi /tmp/nginx-scgi

alembic upgrade head

exec supervisord -c /home/project/app/supervisord.conf -n
