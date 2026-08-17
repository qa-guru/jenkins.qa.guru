FROM jenkins/jnlp-agent-python3

USER root

# Alpine is musl — official nodejs.org linux-x64 tarball is glibc. Unofficial musl build.
# npx allure-notifications 6.2.2 requires Node >=26.
ARG NODE_VER=26.7.0
ARG ALLURE_CLI_VER=3.13.0

RUN apk add --no-cache \
        msttcorefonts-installer \
        fontconfig \
        git \
        bash \
        openjdk21 \
        wget \
        curl \
        ca-certificates \
        proxychains-ng \
        libstdc++ \
        libatomic \
    && update-ms-fonts \
    && curl -fsSL "https://unofficial-builds.nodejs.org/download/release/v${NODE_VER}/node-v${NODE_VER}-linux-x64-musl.tar.gz" \
        | tar -xz -C /opt \
    && mv "/opt/node-v${NODE_VER}-linux-x64-musl" /opt/node \
    && ln -sfn /opt/node/bin/node /usr/local/bin/node \
    && ln -sfn /opt/node/bin/npm /usr/local/bin/npm \
    && ln -sfn /opt/node/bin/npx /usr/local/bin/npx \
    && npm install -g "allure@${ALLURE_CLI_VER}" \
    && ln -sfn /opt/node/bin/allure /usr/local/bin/allure \
    && node --version \
    && allure --version \
    && rm -rf /var/cache/apk/* /root/.npm

ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk
ENV PATH="/opt/node/bin:$JAVA_HOME/bin:$PATH"

RUN export POETRY_HOME=/opt/poetry \
    && python3 -m venv "$POETRY_HOME" \
    && "$POETRY_HOME/bin/pip" install "poetry==2.0.0" \
    && ln -sf /opt/poetry/bin/poetry /usr/sbin/poetry

# Shared Allure notifications contour (SSOT: deploy/qa-guru/ ← dev/scripts + dev/notifications)
# Pins: docs/allure-notifications/VERSION (CLI 6.x A3) · JAR-A2-VERSION (jar 4.x A2)
COPY qa-guru/send-allure-telegram.sh /opt/qa-guru/bin/send-allure-telegram.sh
COPY qa-guru/render-allure-notifications-config.sh /opt/qa-guru/bin/render-allure-notifications-config.sh
COPY qa-guru/allure3.json.tmpl /opt/qa-guru/etc/allure-notifications/allure3.json.tmpl
COPY qa-guru/allure2.json.tmpl /opt/qa-guru/etc/allure-notifications/allure2.json.tmpl
COPY qa-guru/allure-notifications.version /opt/qa-guru/etc/allure-notifications.version
COPY qa-guru/allure-notifications-jar-a2.version /opt/qa-guru/etc/allure-notifications-jar-a2.version
RUN chmod 755 /opt/qa-guru/bin/send-allure-telegram.sh /opt/qa-guru/bin/render-allure-notifications-config.sh
