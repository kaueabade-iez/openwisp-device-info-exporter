Contributing
============

Thank you for your interest in contributing to
**openwisp-device-info-exporter**!

Quick start
-----------

The exporter uses only the Python standard library, so no runtime dependencies
need to be installed.

Development tooling::

    pip install black flake8

Before opening a pull request, make sure the code is formatted and lints
cleanly::

    black --check .
    flake8 .

Build the container image locally::

    docker build -t openwisp/openwisp-device-info-exporter:edge .

Coding style
------------

- Code is formatted with `black <https://github.com/psf/black>`_.
- Keep the exporter dependency-free (standard library only) so the image stays
  minimal and requires no pip install.
