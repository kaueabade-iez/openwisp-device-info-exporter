#!/usr/bin/env python3

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("openwisp_device_info_exporter")

API_INTERNAL = os.environ.get("API_INTERNAL", "api.internal")
OPENWISP_API_INTERNAL = (
    API_INTERNAL if "://" in API_INTERNAL else f"http://{API_INTERNAL}"
).rstrip("/")
OPENWISP_API_HOST = urllib.parse.urlsplit(OPENWISP_API_INTERNAL).hostname
OPENWISP_API_TOKEN = os.environ.get("OPENWISP_API_TOKEN", "")

VM_IMPORT_URL = os.environ.get(
    "VM_IMPORT_URL", "http://vmagent:8429/api/v1/import/prometheus"
)

INTERVAL = int(os.environ.get("DEVICE_INFO_INTERVAL", "120"))
PAGE_SIZE = int(os.environ.get("DEVICE_INFO_PAGE_SIZE", "100"))
HTTP_TIMEOUT = int(os.environ.get("DEVICE_INFO_HTTP_TIMEOUT", "30"))

METRIC_NAME = "openwisp_device_info"

# API field -> Prometheus label
LABEL_FIELDS = {
    "name": "name",
    "organization": "organization_id",
    "group": "group",
    "model": "model",
    "os": "os",
}


def _escape(value):
    """Escape a Prometheus label value."""
    text = "" if value is None else str(value)
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def fetch_devices():
    """Yield device dicts from the paginated OpenWISP device list API.

    Pagination is done by incrementing ``page`` against the internal base URL
    instead of following the API's ``next`` link, because DRF builds ``next``
    from the request host (the public API domain), which would leave the
    internal network.
    """
    headers = {"Authorization": f"Bearer {OPENWISP_API_TOKEN}"}
    if OPENWISP_API_HOST:
        headers["Host"] = OPENWISP_API_HOST
    page = 1
    while True:
        url = (
            f"{OPENWISP_API_INTERNAL}/api/v1/controller/device/"
            f"?page={page}&page_size={PAGE_SIZE}"
        )
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            payload = json.load(resp)
        yield from payload.get("results", [])
        if not payload.get("next"):
            break
        page += 1


def build_exposition(devices):
    lines = [
        f"# HELP {METRIC_NAME} OpenWISP device metadata mapping (value is always 1).",
        f"# TYPE {METRIC_NAME} gauge",
    ]
    for device in devices:
        labels = [f'object_id="{_escape(device.get("id"))}"']
        for field, label in LABEL_FIELDS.items():
            labels.append(f'{label}="{_escape(device.get(field))}"')
        lines.append(f"{METRIC_NAME}{{{','.join(labels)}}} 1")
    return "\n".join(lines) + "\n"


def push(exposition):
    req = urllib.request.Request(
        VM_IMPORT_URL,
        data=exposition.encode("utf-8"),
        method="POST",
        headers={"Content-Type": "text/plain"},
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        resp.read()


def run_once():
    devices = list(fetch_devices())
    push(build_exposition(devices))
    logger.info("published %s device info series", len(devices))


def main():
    logger.info(
        "starting; api=%s vm=%s interval=%ss",
        OPENWISP_API_INTERNAL,
        VM_IMPORT_URL,
        INTERVAL,
    )
    while True:
        try:
            if not OPENWISP_API_TOKEN:
                raise RuntimeError(
                    "OPENWISP_API_TOKEN is not set; cannot query the API"
                )
            run_once()
        except urllib.error.HTTPError as exc:
            logger.error("HTTP error from %s: %s %s", exc.url, exc.code, exc.reason)
        except Exception as exc:  # noqa: BLE001 - keep the loop alive on any failure
            logger.error("failed to publish device info: %s", exc)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
