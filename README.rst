openwisp-device-info-exporter
=============================

.. image:: https://img.shields.io/badge/license-BSD--3--Clause-blue.svg
    :target: https://github.com/openwisp/openwisp-device-info-exporter/blob/master/LICENSE
    :alt: License

.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
    :target: https://pypi.org/project/black/
    :alt: code style: black

----

Publishes three metrics into VictoriaMetrics: an OpenWISP **device info metric**
so that time series forwarded from the internal InfluxDB can be enriched with the
human-readable device name at query time, an **interface up/down metric** that
OpenWISP never forwards on its own, and a **boot time metric** derived from the
device's uptime.

**Why this exists**

When the OpenWISP monitoring data is forwarded to an external VictoriaMetrics
instance (e.g. via an InfluxDB subscription and a ``vmagent`` relay), the metric
points carry only the device UUID as ``object_id``; the hostname/name lives in
PostgreSQL and never reaches the time series database. This exporter bridges
that gap: it reads the device list from the OpenWISP REST API and publishes ::

    openwisp_device_info{object_id="<uuid>", name="<hostname>", organization_id="...", group="...", model="...", os="..."} 1

Queries can then attach the name (and other attributes) with a ``group_left``
join, evaluated server-side by VictoriaMetrics ::

    traffic_rx_bytes * on(object_id) group_left(name) openwisp_device_info

Interface state is a second, related gap: OpenWISP's InfluxDB writer never
emits a metric for an interface's ``up``/``down`` state, so it never reaches
the forwarded ``autogen`` retention policy either. The exporter reads it
directly from InfluxDB's ``short`` retention policy, where openwisp-monitoring
already writes this exact data on every device check-in, and publishes ::

    openwisp_interface_up{object_id="<uuid>", ifname="<name>"} 1

A value of ``1`` means the interface is up, ``0`` means it is down. A series is
only emitted for interfaces observed in the current cycle.

Boot time is a third, related gap: OpenWISP's InfluxDB writer never emits a
boot/uptime metric either, and there is no direct boot-timestamp field in the
API. The exporter derives it from the same InfluxDB ``device_data`` payload as
the interface metric (``general.local_time - general.uptime``, both captured
at the same measurement instant) and publishes ::

    openwisp_boot_time_seconds{object_id="<uuid>"} 1737600000

The value is the Unix timestamp of the device's last boot; correctness depends
on the device's clock being NTP-synced. A series is only emitted for devices
where both ``general.local_time`` and ``general.uptime`` are present in the
current cycle; see `docs/index.rst <docs/index.rst>`_ for details.

The exporter has one pinned dependency, ``influxdb``, matching openwisp-
monitoring's own version — used only to read InfluxDB directly for
interface/boot-time data (see below).

Why InfluxDB directly, not the REST status endpoint
----------------------------------------------------

``GET /api/v1/monitoring/device/<pk>/?status=true`` looks like the obvious
source for this data, but it is not free: regardless of the ``status`` param,
the view unconditionally recomputes **every** monitoring chart for the device
(traffic per interface, RTT, CPU, disk, memory, uptime, packet loss), issuing
at least 2 InfluxDB queries per chart — 3 for ``top_fields`` charts such as
per-interface traffic. ``status=true`` only adds one extra response field
(``data``); the rest of that work is thrown away. That same ``data`` blob is
also written to InfluxDB independently on every device check-in, at a fixed
location (retention policy ``short``, measurement ``device_data``, tagged by
device UUID), so this exporter reads it directly with a single lightweight
query instead — via the same ``influxdb`` client library openwisp-monitoring
itself uses.

Usage
-----

The image is designed to run as a container next to a ``vmagent`` relay in a
`docker-openwisp <https://github.com/openwisp/docker-openwisp>`_ deployment.

Build the image::

    docker build -t openwisp/openwisp-device-info-exporter:edge .

Run it (all configuration is via environment variables)::

    docker run --rm \
        -e OPENWISP_API_TOKEN=<token> \
        -e API_INTERNAL=api.internal \
        -e VM_IMPORT_URL=http://vmagent:8429/api/v1/import/prometheus \
        openwisp/openwisp-device-info-exporter:edge

Configuration
-------------

============================ ============================================================= ================================================
Environment variable         Description                                                   Default
============================ ============================================================= ================================================
``OPENWISP_API_TOKEN``       Bearer token used to read the device list. Create it in the   (required)
                             Django admin (*Tokens*) or via ``POST /api/v1/users/token/``.
``API_INTERNAL``             Internal hostname of the OpenWISP API (the docker-openwisp    ``api.internal``
                             nginx internal alias). The exporter reaches it over http on
                             port 80 and sends this same name as the ``Host`` header, so
                             nginx hits its internal server block (no HTTPS redirect) and
                             Django's ``ALLOWED_HOSTS`` accepts the request.
``VM_IMPORT_URL``            VictoriaMetrics / vmagent Prometheus import endpoint.         ``http://vmagent:8429/api/v1/import/prometheus``
``DEVICE_INFO_INTERVAL``     Refresh interval in seconds (keep below VM's 5m staleness).   ``120``
``DEVICE_INFO_PAGE_SIZE``    Device list API page size.                                    ``100``
``DEVICE_INFO_HTTP_TIMEOUT`` Per-request HTTP timeout in seconds.                          ``30``
``DEVICE_INFO_MAX_WORKERS``  Max concurrent per-device InfluxDB queries for the interface  ``8``
                             up/down and boot time metrics.
``INFLUXDB_HOST``            InfluxDB hostname. **Required** — default baked into the      ``influxdb``
                             Docker image, not the Python code.
``INFLUXDB_PORT``            InfluxDB port. **Required** — default baked into the Docker   ``8086``
                             image, not the Python code.
``INFLUXDB_NAME``            InfluxDB database name. **Required** — default baked into     ``openwisp``
                             the Docker image, not the Python code.
``INFLUXDB_USER``            InfluxDB username. **Required** — default baked into the      ``admin``
                             Docker image, not the Python code.
``INFLUXDB_PASS``            InfluxDB password. **Required** — default baked into the      ``admin``
                             Docker image, not the Python code.
``INFLUXDB_TIMEOUT``         Per-query InfluxDB timeout in seconds.                        ``30``
============================ ============================================================= ================================================

Deploying with docker-openwisp
------------------------------

Reference the prebuilt image as a service in ``docker-compose.yml`` (it reads
the same ``.env`` as the other services)::

    device-info-exporter:
      image: ${IMAGE_OWNER:-openwisp}/openwisp-device-info-exporter:${OPENWISP_VERSION:-edge}
      restart: always
      depends_on:
        - api
        - vmagent
        - influxdb
      env_file:
        - .env

Set ``OPENWISP_API_TOKEN`` in ``.env`` and start the service.

See `docs/index.rst <docs/index.rst>`_ for the full documentation.

License
-------

See `LICENSE <LICENSE>`_.
