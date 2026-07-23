# AGENTS.md

## Project Overview

`openwisp-device-info-exporter` is a small, dependency-free Python service that
publishes an `openwisp_device_info` metric into VictoriaMetrics, mapping each
OpenWISP device UUID (`object_id`) to its human-readable name and attributes.
It is packaged as a Docker image and deployed alongside a `vmagent` relay in a
`docker-openwisp` stack.

Core code lives in `openwisp_device_info_exporter/`:

- `exporter.py` contains the whole exporter: reading the OpenWISP device list
  from the REST API and pushing the info metric to the VictoriaMetrics/vmagent
  Prometheus import endpoint.
- `__main__.py` is the container entrypoint (`python -m openwisp_device_info_exporter`).

## Source of Truth

- Use `README.rst` and `docs/` for usage, configuration (environment
  variables), and query examples.
- Use `Dockerfile` for how the image is built and run.
- Use `.github/workflows/ci.yml` for the CI-tested lint/build commands.

Follow the DRY principle: do not duplicate information or code across files.

If instructions conflict, repository config and CI workflows win first, docs
next, and this file is supplemental.

## Development Notes

- Keep the exporter dependency-free (Python standard library only) so the image
  stays minimal and requires no pip install.
- Keep changes focused. Avoid unrelated refactors and formatting churn.
- All runtime configuration is via environment variables; document any new
  variable in `README.rst` and `docs/index.rst`.
- Place imports at the top of the file.

## Testing and QA

- Format and lint before committing: `black --check .` and `flake8 .`.
- Verify the image builds: `docker build -t openwisp/openwisp-device-info-exporter:edge .`.
- A quick smoke test: `python -m openwisp_device_info_exporter` with `OPENWISP_API_TOKEN`
  unset should log a clear misconfiguration message and keep retrying (it must
  not crash-loop).
