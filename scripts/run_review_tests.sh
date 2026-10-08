#!/bin/bash
# Guard dependency imports at interpreter startup, including test collection.
set -euo pipefail

export PYTHONDONTWRITEBYTECODE=1
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

if [ -n "${INTEGRA_TEST_REVIEW_PYTHONPATH:-}" ]; then
  export PYTHONPATH="$INTEGRA_TEST_REVIEW_PYTHONPATH${PYTHONPATH:+:$PYTHONPATH}"
fi

if [ "$#" -eq 0 ]; then
  set -- discover -s tests -v
fi
exec "${INTEGRA_REVIEW_TEST_PYTHON:-python3}" -B -m unittest "$@"
