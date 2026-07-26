FROM jenkins/jnlp-agent-python3

USER root

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
        nodejs \
        npm \
    && update-ms-fonts \
    && npm install -g "allure@${ALLURE_CLI_VER}" \
    && allure --version \
    && rm -rf /var/cache/apk/* /root/.npm

ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk
ENV PATH="$JAVA_HOME/bin:$PATH"

RUN export POETRY_HOME=/opt/poetry \
    && python3 -m venv "$POETRY_HOME" \
    && "$POETRY_HOME/bin/pip" install "poetry==2.0.0" \
    && ln -sf /opt/poetry/bin/poetry /usr/sbin/poetry

# Shared Telegram notify (SSOT: deploy/qa-guru/; pin docs/allure-notifications/VERSION)
COPY qa-guru/send-allure-telegram.sh /opt/qa-guru/bin/send-allure-telegram.sh
COPY qa-guru/allure-notifications.version /opt/qa-guru/etc/allure-notifications.version
RUN chmod 755 /opt/qa-guru/bin/send-allure-telegram.sh
