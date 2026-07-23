openwisp-device-info-exporter
=============================

.. image:: https://github.com/openwisp/openwisp-device-info-exporter/actions/workflows/ci.yml/badge.svg
    :target: https://github.com/openwisp/openwisp-device-info-exporter/actions/workflows/ci.yml
    :alt: CI build status

.. image:: https://img.shields.io/badge/license-BSD--3--Clause-blue.svg
    :target: https://github.com/openwisp/openwisp-device-info-exporter/blob/master/LICENSE
    :alt: License

.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
    :target: https://pypi.org/project/black/
    :alt: code style: black

----

Publishes an OpenWISP **device info metric** into VictoriaMetrics so that time
series forwarded from the internal InfluxDB (which are tagged only by the device
UUID, ``object_id``) can be enriched with the human-readable device name at
query time.

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

The exporter uses only the Python standard library.

Usage
-----

The image is designed to run as a container next to a ``vmagent`` relay in a
`docker-openwisp <https://github.com/openwisp/docker-openwisp>`_ deployment.

Build the image::

    docker build -t openwisp/openwisp-device-info-exporter:edge .

Run it (all configuration is via environment variables)::

    docker run --rm \
        -e OPENWISP_API_TOKEN=<token> \
        -e API_DOMAIN=api.openwisp.org \
        -e OPENWISP_API_URL=http://api:8001 \
        -e VM_IMPORT_URL=http://vmagent:8429/api/v1/import/prometheus \
        openwisp/openwisp-device-info-exporter:edge

Configuration
-------------

============================ ============================================================ ===================================================
Environment variable         Description                                                  Default
============================ ============================================================ ===================================================
``OPENWISP_API_TOKEN``       Bearer token used to read the device list. Create it in the  (required)
                             Django admin (*Tokens*) or via ``POST /api/v1/users/token/``.
``OPENWISP_API_URL``         Base URL of the OpenWISP API (internal service address).     ``http://api:8001``
``OPENWISP_API_HOST``        ``Host`` header sent to the API so Django's ``ALLOWED_HOSTS``  falls back to ``API_DOMAIN``
                             accepts the internal request.
``VM_IMPORT_URL``            VictoriaMetrics / vmagent Prometheus import endpoint.        ``http://vmagent:8429/api/v1/import/prometheus``
``DEVICE_INFO_INTERVAL``     Refresh interval in seconds (keep below VM's 5m staleness).  ``120``
``DEVICE_INFO_PAGE_SIZE``    Device list API page size.                                   ``100``
``DEVICE_INFO_HTTP_TIMEOUT`` Per-request HTTP timeout in seconds.                         ``30``
============================ ============================================================ ===================================================

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
      env_file:
        - .env

Set ``OPENWISP_API_TOKEN`` in ``.env`` and start the service.

See `docs/index.rst <docs/index.rst>`_ for the full documentation, including the
alternative "bake the name at ingest with relabeling" approach.

License
-------

See `LICENSE <LICENSE>`_.
