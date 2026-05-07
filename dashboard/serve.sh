#!/usr/bin/env bash
# Local HTTP server for the dashboard. Run from the dashboard/ folder.
# Browsers refuse fetch() from file:// pages, so the JSON data files won't
# load unless the dashboard is served over HTTP. This is the simplest fix.

PORT=${1:-8765}
echo
echo "Serving dashboard on http://localhost:$PORT/"
echo "  - Landing:       http://localhost:$PORT/"
echo "  - Institutional: http://localhost:$PORT/institutional/"
echo "  - Research:      http://localhost:$PORT/research/"
echo
echo "Press Ctrl+C to stop."
echo
python -m http.server $PORT
