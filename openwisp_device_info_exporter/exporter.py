#!/usr/bin/env python3

import concurrent.futures
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
MAX_WORKERS = int(os.environ.get("DEVICE_INFO_MAX_WORKERS", "8"))

METRIC_NAME = "openwisp_device_info"
INTERFACE_METRIC_NAME = "openwisp_interface_up"

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


def build_device_info_exposition(devices):
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


def fetch_status(device):
    """Fetch the interface list from a device's monitoring status endpoint."""
    headers = {"Authorization": f"Bearer {OPENWISP_API_TOKEN}"}
    if OPENWISP_API_HOST:
        headers["Host"] = OPENWISP_API_HOST
    url = (
        f"{OPENWISP_API_INTERNAL}/api/v1/monitoring/device/{device['id']}/?status=true"
    )
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        payload = json.load(resp)
    return payload.get("data", {}).get("interfaces", [])


def collect_interfaces(devices):
    """Fetch interface status for every device concurrently.

    Devices whose status fetch fails are skipped: we cannot enumerate their
    interfaces, so we must not report them as up or down for this cycle.
    """
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(fetch_status, device): device for device in devices}
        for future in concurrent.futures.as_completed(futures):
            device = futures[future]
            try:
                interfaces = future.result()
            except Exception as exc:  # noqa: BLE001 - isolate one bad device
                logger.error(
                    "failed to fetch status for device %s: %s", device.get("id"), exc
                )
                continue
            for interface in interfaces:
                ifname = interface.get("name")
                if not ifname:
                    continue
                rows.append((device["id"], ifname, bool(interface.get("up"))))
    return rows


def build_interface_exposition(rows):
    lines = [
        f"# HELP {INTERFACE_METRIC_NAME} OpenWISP interface operational state "
        "(1=up, 0=down).",
        f"# TYPE {INTERFACE_METRIC_NAME} gauge",
    ]
    for object_id, ifname, up in rows:
        labels = f'object_id="{_escape(object_id)}",ifname="{_escape(ifname)}"'
        lines.append(f"{INTERFACE_METRIC_NAME}{{{labels}}} {1 if up else 0}")
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
    push(build_device_info_exposition(devices))
    interfaces = collect_interfaces(devices)
    push(build_interface_exposition(interfaces))
    logger.info(
        "published %s device info and %s interface_up series",
        len(devices),
        len(interfaces),
    )


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
