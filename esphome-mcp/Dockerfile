ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install build dependencies and glibc compatibility for ESPHome/PlatformIO compilation
RUN apk add --no-cache \
    build-base \
    libc6-compat \
    gcompat \
    libffi-dev \
    openssl-dev \
    rust \
    cargo \
    git \
    python3-dev

# Install Python dependencies and ESPHome
COPY requirements.txt /tmp/
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt \
    && pip3 install --no-cache-dir esphome \
    && rm /tmp/requirements.txt

# Copy server code
COPY server/ /opt/server/
COPY run.sh /opt/

RUN chmod a+x /opt/run.sh

WORKDIR /opt

CMD ["/opt/run.sh"]
