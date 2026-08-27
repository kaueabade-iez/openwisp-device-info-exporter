Contributing
============

Thank you for your interest in contributing to
**openwisp-device-info-exporter**!

Quick start
-----------

Setup and activate a virtual environment (we'll be using `virtualenv
<https://pypi.org/project/virtualenv/>`_)::

    python -m virtualenv env
    source env/bin/activate

Install the runtime dependency (needed to import ``exporter.py`` and to run
the exporter locally)::

    pip install -r requirements.txt

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
- At most one *direct* third-party dependency, ``influxdb``, pinned to match
  ``openwisp-monitoring/requirements.txt``'s own version exactly — bump the
  two together, don't add other dependencies without discussion.
