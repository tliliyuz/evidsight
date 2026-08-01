#!/usr/bin/env bash
set -euo pipefail

services/knowledge/.venv/bin/python -m pytest -c services/knowledge/pytest.ini services/knowledge/tests "$@"
services/research/.venv/bin/python -m pytest -c services/research/pytest.ini services/research/tests "$@"
npm --prefix apps/web test
