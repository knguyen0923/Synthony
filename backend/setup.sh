#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v python3.11 >/dev/null 2>&1; then
  echo "python3.11 not found. Install it first (e.g. 'brew install python@3.11')." >&2
  exit 1
fi

python3.11 -m venv .venv --clear
source .venv/bin/activate
pip install --upgrade pip

# madmom (unmaintained since ~2022) needs numpy/Cython/scipy/mido already
# present to build from its sdist, and must be installed with build
# isolation off -- see the comments on madmom/numpy/setuptools in
# requirements.txt for why.
pip install "numpy>=1.26.4,<2.0" scipy cython mido "setuptools<81"
pip install --no-build-isolation -r requirements.txt

echo ""
echo "Backend environment ready. Activate it with:"
echo "    source $(pwd)/.venv/bin/activate"
