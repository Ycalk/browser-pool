ARG DEBIAN_TAG=bookworm-20260824-slim
FROM debian:${DEBIAN_TAG}

RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates matchbox-window-manager socat xz-utils tzdata \
    x11-utils libnspr4 libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libxkbcommon0 libasound2 libcairo2 libxdamage1 \
    fonts-liberation fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

ARG CHROMIUM_VERSION=152.0.7977.64-1
RUN mkdir -p /opt/chromium && \
    curl -fsSL "https://github.com/ungoogled-software/ungoogled-chromium-portablelinux/releases/download/${CHROMIUM_VERSION}/ungoogled-chromium-${CHROMIUM_VERSION}-x86_64_linux.tar.xz" \
    | tar -xJ -C /opt/chromium --strip-components=1 && \
    ln -s /opt/chromium/chrome /usr/local/bin/chromium

ARG KASMVNC_VERSION=1.5.0
RUN curl -fsSL -O "https://github.com/kasmtech/KasmVNC/releases/download/v${KASMVNC_VERSION}/kasmvncserver_bookworm_${KASMVNC_VERSION}_amd64.deb" \
    && apt-get update \
    && apt-get install -y --no-install-recommends ./kasmvncserver_bookworm_${KASMVNC_VERSION}_amd64.deb \
    && rm -f kasmvncserver_bookworm_${KASMVNC_VERSION}_amd64.deb \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -u 1000 -m -s /bin/bash chromium \
    && adduser chromium ssl-cert \
    && mkdir -p /tmp/.X11-unix /tmp/profile \
    && chown root:root /tmp/.X11-unix \
    && chmod 1777 /tmp/.X11-unix \
    && chown -R chromium:chromium /tmp/profile /home/chromium

RUN mkdir -p /etc/chromium/policies/managed /etc/opt/chrome/policies/managed && \
    echo '{"BookmarkBarEnabled": false}' > /etc/chromium/policies/managed/disable_bookmarks.json && \
    cp /etc/chromium/policies/managed/disable_bookmarks.json /etc/opt/chrome/policies/managed/

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER chromium

ENTRYPOINT ["/entrypoint.sh"]