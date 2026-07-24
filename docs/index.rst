OpenWISP Device Info Exporter
=============================

The **openwisp-device-info-exporter** is a single process that publishes two
Prometheus metrics into VictoriaMetrics: an *info metric* that maps each
OpenWISP device UUID to its human-readable name (and a few attributes), and an
interface up/down metric that OpenWISP itself never forwards.

Background
----------

In a deployment where OpenWISP's monitoring data is forwarded to an external
VictoriaMetrics instance (for example via an InfluxDB ``CREATE SUBSCRIPTION``
and a ``vmagent`` relay), every metric point carries only the device UUID as the
``object_id`` label. The human-readable hostname is stored in PostgreSQL and is
never written to the time series database.

This exporter closes that gap by periodically reading the device list from the
OpenWISP REST API (``GET /api/v1/controller/device/``) and publishing::

    openwisp_device_info{object_id="<uuid>", name="<hostname>", organization_id="...", group="...", model="...", os="..."} 1

A second, related gap is interface state: OpenWISP's InfluxDB writer
(``openwisp-monitoring``'s device writer) only ever emits ``traffic``,
``wifi_clients`` and mobile ``signal`` per interface — it never reads the
``up``/``down`` boolean. That boolean lives only inside the raw NetJSON device
data blob, which OpenWISP writes to the short-lived ``short`` retention policy
(24h by default) as one opaque JSON field; the InfluxDB subscription forwards
only the ``autogen`` retention policy, so this data never reaches external
VictoriaMetrics. There is no bulk API for it, so the exporter reads it directly
from each device's monitoring status endpoint
(``GET /api/v1/monitoring/device/<pk>/?status=true``), one request per device
per cycle, and publishes::

    openwisp_interface_up{object_id="<uuid>", ifname="<name>"} 1

Architecture
------------

::

    exporter --(internal)--> api.internal     (device list, Bearer token)
             --(internal)--> api.internal     (per-device status, Bearer token, threaded)
             --(internal)--> vmagent:8429/api/v1/import/prometheus
                                  └--> external VictoriaMetrics (remote_write)

Each cycle, the exporter fetches the device list once and reuses it for both
metrics: it pushes the device info metric first, then fetches every device's
interface status concurrently (bounded by ``INTERFACE_UP_MAX_WORKERS``) and
pushes the interface up/down metric. Both metrics are pushed to ``vmagent``'s
Prometheus import endpoint, which forwards them to VictoriaMetrics reusing
``vmagent``'s disk buffering and remote_write authentication. Only the Python
standard library is used.

Interface up/down semantics
----------------------------

- Labels are only ``object_id`` and ``ifname`` — the device name is *not*
  duplicated onto this metric; join it at query time (see below), exactly like
  the other forwarded metrics.
- A series is only emitted for an interface actually observed in the current
  cycle: value ``1`` if up, ``0`` if down.
- If a device's status request fails (device unreachable, timeout, error
  response), that device's interfaces are skipped for the cycle — the exporter
  does **not** synthesize a ``0``, because it cannot enumerate the device's
  interfaces and reporting "unknown" as "down" would be misleading. Their
  series simply stop updating and fall out of VictoriaMetrics' default 5-minute
  staleness window, so instant queries drop them after ~5 minutes rather than
  showing a stale wrong value. At the default 120s interval that tolerates
  roughly two missed cycles before a transiently-unreachable device's
  interfaces disappear from instant queries.
- One failing device never aborts the cycle: each per-device fetch is isolated
  and errors are logged individually.

Configuration
-------------

All configuration is done through environment variables; see the table in the
`README <../README.rst>`_.

Querying
--------

Attach the device name to any metric at query time with a ``group_left`` join
(evaluated server-side by VictoriaMetrics)::

    traffic_rx_bytes * on(object_id) group_left(name) openwisp_device_info

In Grafana, use ``{{name}}`` in the panel legend. Swap ``name`` for ``group``,
``model`` or ``os`` to group by those attributes instead.

To avoid repeating the join, you can define a MetricsQL ``WITH`` template::

    WITH (named(m) = m * on(object_id) group_left(name) openwisp_device_info)
    named(traffic_rx_bytes)

The same join works for the interface metric, e.g. to list currently-down
interfaces with their device name::

    openwisp_interface_up == 0
    openwisp_interface_up * on(object_id) group_left(name) openwisp_device_info

Rename edge case
~~~~~~~~~~~~~~~~~

Right after a device is renamed, both the old and new ``openwisp_device_info``
series can briefly coexist within VictoriaMetrics' staleness window (5m by
default); a ``group_left`` join may momentarily report a duplicate match for
that device until the old series goes stale. This is transient and self-heals.
