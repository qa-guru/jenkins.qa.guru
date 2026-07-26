FROM jenkins/agent:jdk21

USER root

ARG NODE_VER=24.11.0
ARG ALLURE_CLI_VER=3.13.0

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        wget \
        curl \
        ca-certificates \
        proxychains4 \
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

# Shared Telegram notify (SSOT: deploy/qa-guru/; pin docs/allure-notifications/VERSION)
COPY qa-guru/send-allure-telegram.sh /opt/qa-guru/bin/send-allure-telegram.sh
COPY qa-guru/allure-notifications.version /opt/qa-guru/etc/allure-notifications.version
RUN chmod 755 /opt/qa-guru/bin/send-allure-telegram.sh
