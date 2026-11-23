FROM python:3.13-slim-bookworm AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx supervisor curl gnupg ca-certificates locales tzdata \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/share/zoneinfo/UTC /etc/localtime \
    && echo "UTC" > /etc/timezone
ENV TZ=UTC
ENV TIME_ZONE=UTC

RUN python -m pip install --upgrade pip

RUN useradd -m project
WORKDIR /home/project/app

COPY nginx.conf supervisord.conf entrypoint.sh ./
RUN chmod +x entrypoint.sh

USER project

ENV PATH="/home/project/.local/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ARG wheel=service-0.1.0-py3-none-any.whl
COPY --chown=project:project ./dist/$wheel .
RUN pip install --no-cache-dir --upgrade --no-warn-script-location /home/project/app/$wheel

ENV API_PORT=8000

ENTRYPOINT ["/home/project/app/entrypoint.sh"]