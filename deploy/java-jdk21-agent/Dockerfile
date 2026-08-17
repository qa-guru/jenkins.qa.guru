FROM jenkins/agent:jdk21

USER root

# npx allure-notifications 6.2.2 requires Node >=26 (jobs on this image send A3 collages).
ARG NODE_VER=26.7.0
ARG ALLURE_CLI_VER=3.13.0

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        wget \
        curl \
        ca-certificates \
        proxychains4 \
        libatomic1 \
        zip \
        unzip \
    && curl -fsSL "https://nodejs.org/dist/v${NODE_VER}/node-v${NODE_VER}-linux-x64.tar.gz" \
        | tar -xz -C /opt \
    && mv "/opt/node-v${NODE_VER}-linux-x64" /opt/node \
    && ln -sfn /opt/node/bin/node /usr/local/bin/node \
    && ln -sfn /opt/node/bin/npm /usr/local/bin/npm \
    && ln -sfn /opt/node/bin/npx /usr/local/bin/npx \
    && npm install -g "allure@${ALLURE_CLI_VER}" \
    && ln -sfn /opt/node/bin/allure /usr/local/bin/allure \
    && node --version \
    && allure --version \
    && rm -rf /var/lib/apt/lists/* /root/.npm

# Shared Allure notifications contour (SSOT: deploy/qa-guru/ ← dev/scripts + dev/notifications)
# Pins: docs/allure-notifications/VERSION (CLI 6.x A3) · JAR-A2-VERSION (jar 4.x A2)
COPY qa-guru/send-allure-telegram.sh /opt/qa-guru/bin/send-allure-telegram.sh
COPY qa-guru/render-allure-notifications-config.sh /opt/qa-guru/bin/render-allure-notifications-config.sh
COPY qa-guru/allure3.json.tmpl /opt/qa-guru/etc/allure-notifications/allure3.json.tmpl
COPY qa-guru/allure2.json.tmpl /opt/qa-guru/etc/allure-notifications/allure2.json.tmpl
COPY qa-guru/allure-notifications.version /opt/qa-guru/etc/allure-notifications.version
COPY qa-guru/allure-notifications-jar-a2.version /opt/qa-guru/etc/allure-notifications-jar-a2.version
RUN chmod 755 /opt/qa-guru/bin/send-allure-telegram.sh /opt/qa-guru/bin/render-allure-notifications-config.sh
