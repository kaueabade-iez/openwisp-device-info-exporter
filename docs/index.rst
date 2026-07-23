OpenWISP Device Info Exporter
=============================

The **openwisp-device-info-exporter** publishes a Prometheus *info metric* that
maps each OpenWISP device UUID to its human-readable name (and a few
attributes), so that monitoring data forwarded to VictoriaMetrics can be
enriched with the device name.

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

Architecture
------------

::

    exporter --(internal)--> api.internal     (device list, Bearer token)
             --(internal)--> vmagent:8429/api/v1/import/prometheus
                                  └--> external VictoriaMetrics (remote_write)

The exporter pushes the info metric to ``vmagent``'s Prometheus import endpoint,
which forwards it to VictoriaMetrics reusing ``vmagent``'s disk buffering and
remote_write authentication. Only the Python standard library is used.

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

Rename edge case
~~~~~~~~~~~~~~~~~

Right after a device is renamed, both the old and new ``openwisp_device_info``
series can briefly coexist within VictoriaMetrics' staleness window (5m by
default); a ``group_left`` join may momentarily report a duplicate match for
that device until the old series goes stale. This is transient and self-heals.
