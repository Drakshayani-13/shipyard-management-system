#!/usr/bin/env bash
# One-command local run (Mac/Linux):  ./run.sh
set -e
cd "$(dirname "$0")/backend"
[ -d venv ] || python3 -m venv venv
source venv/bin/activate
pip install -q -r requirements.txt
python seed.py
echo
echo "Open http://127.0.0.1:5001/portal/   (login: admin / admin123)"
python app.py
