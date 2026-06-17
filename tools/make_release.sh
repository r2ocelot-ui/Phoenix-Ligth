#!/usr/bin/env bash
# Atajo Linux/macOS: ejecuta el generador de release.
set -e
cd "$(dirname "$0")/.."
python3 tools/make_release.py "$@"
