#!/usr/bin/env bash
set -euo pipefail
docker build -f Dockerfile.test -t geodrops-test .
docker run --rm geodrops-test python -m pytest "$@"
