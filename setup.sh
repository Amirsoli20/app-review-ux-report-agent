#!/bin/bash
# Creates .venv and installs the pipeline's Python packages (Python 3.10 to 3.13).
cd "$(dirname "$0")" || exit 1
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(not (3,10) <= sys.version_info[:2] <= (3,13))'; then PY="$c"; break; fi
done
[ -z "$PY" ] && { echo "Python 3.10 to 3.13 is required"; exit 1; }
"$PY" -m venv .venv && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -r requirements.txt || exit 1
.venv/bin/python -c "from sentence_transformers import SentenceTransformer as S; S('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')" \
  && echo "Setup done." || echo "Setup done; the embedding model will download on first run."
