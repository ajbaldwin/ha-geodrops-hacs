#!/usr/bin/env bash
set -euo pipefail
docker build -f Dockerfile.test -t geodrops-hacs-test .
docker run --rm geodrops-hacs-test mypy
docker run --rm geodrops-hacs-test python -m pytest "$@"
