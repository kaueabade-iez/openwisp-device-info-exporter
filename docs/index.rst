OpenWISP Device Info Exporter
=============================

The **openwisp-device-info-exporter** is a single process that publishes three
Prometheus metrics into VictoriaMetrics: an *info metric* that maps each
OpenWISP device UUID to its human-readable name (and a few attributes), an
interface up/down metric that OpenWISP itself never forwards, and a boot time
metric derived from the device's uptime.

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
VictoriaMetrics. There is no bulk API for it, so the exporter reads it
directly from InfluxDB's ``short`` retention policy, where openwisp-monitoring
already writes this exact data on every device check-in (see `README
<../README.rst>`_ for why this reads InfluxDB directly rather than the REST
status endpoint) and publishes::

    openwisp_interface_up{object_id="<uuid>", ifname="<name>"} 1

A third, related gap is boot time: OpenWISP's InfluxDB writer never emits a
boot/uptime metric either, and there is no direct boot-timestamp field in the
API. The same InfluxDB ``device_data`` payload used for the interface metric
also carries a ``general`` block with two integers: ``uptime`` (seconds since boot)
and ``local_time`` (the device's Unix timestamp at the moment of the
measurement). Both are captured at the same instant, so their difference is
the boot epoch and is immune to how stale the cached snapshot is — as the
snapshot ages, both values drift up together. The exporter derives it as
``general.local_time - general.uptime`` and publishes::

    openwisp_boot_time_seconds{object_id="<uuid>"} 1737600000

Architecture
------------

::

    exporter --(internal)--> api.internal     (device list, Bearer token)
             --(internal)--> influxdb:8086/query (per-device device_data point, threaded)
             --(internal)--> vmagent:8429/api/v1/import/prometheus
                                  └--> external VictoriaMetrics (remote_write)

Each cycle, the exporter fetches the device list once and reuses it for all
three metrics: it pushes the device info metric first, then queries InfluxDB
for every device's ``device_data`` point concurrently (bounded by
``DEVICE_INFO_MAX_WORKERS``) — a single query per device yields both its
interface list and its ``general`` block — and pushes the interface up/down
and boot time metrics from that one pass. All metrics are pushed to
``vmagent``'s Prometheus import endpoint, which forwards them to
VictoriaMetrics reusing ``vmagent``'s disk buffering and remote_write
authentication.

Configuration
-------------

All configuration is done through environment variables; see the table in the
`README <../README.rst>`_.

Querying
--------

Attach the device name to any metric at query time with a ``group_left`` join
(evaluated server-side by VictoriaMetrics)::

    traffic_rx_bytes * on(object_id) group_left(name) openwisp_device_info

To avoid repeating the join, you can define a MetricsQL ``WITH`` template::

    WITH (named(m) = m * on(object_id) group_left(name) openwisp_device_info)
    named(traffic_rx_bytes)

The same join works for the interface metric, e.g. to list currently-down
interfaces with their device name::

    openwisp_interface_up == 0
    openwisp_interface_up * on(object_id) group_left(name) openwisp_device_info

The boot time metric follows the same node_boot_time_seconds idiom used by the
Prometheus node exporter. Current uptime, computed query-side::

    time() - openwisp_boot_time_seconds

Reboot detection / alerting — a non-zero result means the boot timestamp
changed within the window, i.e. the device rebooted::

    changes(openwisp_boot_time_seconds[1h]) > 0

Enriched with the device name::

    openwisp_boot_time_seconds * on(object_id) group_left(name) openwisp_device_info

Rename edge case
~~~~~~~~~~~~~~~~~

Right after a device is renamed, both the old and new ``openwisp_device_info``
series can briefly coexist within VictoriaMetrics' staleness window (5m by
default); a ``group_left`` join may momentarily report a duplicate match for
that device until the old series goes stale. This is transient and self-heals.
