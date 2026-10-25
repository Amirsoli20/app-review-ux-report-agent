#!/bin/bash
# One command: ./run.sh "App name | App Store link | id" [--country cc] [--set key=value] [--resume runs/<folder>]
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then ./setup.sh || exit 1; fi
exec .venv/bin/python scripts/run_pipeline.py "$@"
