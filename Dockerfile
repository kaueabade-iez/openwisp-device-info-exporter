# hadolint ignore=DL3007
FROM python:3.13-slim

LABEL org.opencontainers.image.title="openwisp-device-info-exporter" \
    org.opencontainers.image.description="Publishes OpenWISP device UUID->name info, interface up/down, and boot time metrics to VictoriaMetrics" \
    org.opencontainers.image.source="https://github.com/kaueabade-iez/openwisp-device-info-exporter" \
    org.opencontainers.image.licenses="BSD-3-Clause"

RUN useradd --system --create-home --shell /bin/bash --uid 1001 --gid root openwisp

WORKDIR /opt/openwisp

# The exporter uses only the Python standard library, so there is nothing to
# pip install; just copy the package in.
COPY --chown=openwisp:root openwisp_device_info_exporter/ /opt/openwisp/openwisp_device_info_exporter/

USER openwisp:root

ENTRYPOINT ["python3", "-m", "openwisp_device_info_exporter"]
