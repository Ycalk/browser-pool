FROM python:3.13-slim-bookworm

RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates matchbox-window-manager xz-utils tzdata x11-utils \
    libgtk-3-0 libavformat-dev libasound2 libswscale-dev libdbus-glib-1-2 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip

ARG KASMVNC_VERSION=1.5.0
RUN curl -fsSL -O "https://github.com/kasmtech/KasmVNC/releases/download/v${KASMVNC_VERSION}/kasmvncserver_bookworm_${KASMVNC_VERSION}_amd64.deb" \
    && apt-get update \
    && apt-get install -y --no-install-recommends ./kasmvncserver_bookworm_${KASMVNC_VERSION}_amd64.deb \
    && rm -f kasmvncserver_bookworm_${KASMVNC_VERSION}_amd64.deb \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ENV XDG_CACHE_HOME=/opt/cache
ARG CAMOUFOX_VERSION=152.0.4-beta.30
RUN python -m camoufox fetch "official/stable/${CAMOUFOX_VERSION}"

RUN useradd -u 1000 -m -s /bin/bash project \
    && adduser project ssl-cert \
    && mkdir -p /tmp/.X11-unix /home/project/.camoufox \
    && chown root:root /tmp/.X11-unix \
    && chmod 1777 /tmp/.X11-unix \
    && chown -R project:project /opt/cache /home/project

USER project
WORKDIR /home/project/app
ENV PATH="/home/project/.local/bin:$PATH"

COPY --chown=project:project entrypoint.sh .
RUN chmod +x /home/project/app/entrypoint.sh

ARG wheel=camoufox_browser-0.1.0-py3-none-any.whl
COPY --chown=project:project ./dist/$wheel .
RUN pip install --no-cache-dir --upgrade --no-warn-script-location /home/project/app/$wheel

ENTRYPOINT ["/home/project/app/entrypoint.sh"]