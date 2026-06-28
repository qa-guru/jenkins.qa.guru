FROM jenkins/jnlp-agent-python3

USER root

RUN apk add --no-cache msttcorefonts-installer fontconfig git bash openjdk21 \
    && update-ms-fonts \
    && rm -rf /var/cache/apk/*

ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk
ENV PATH="$JAVA_HOME/bin:$PATH"

RUN export POETRY_HOME=/opt/poetry \
    && python3 -m venv "$POETRY_HOME" \
    && "$POETRY_HOME/bin/pip" install "poetry==2.0.0" \
    && ln -sf /opt/poetry/bin/poetry /usr/sbin/poetry
