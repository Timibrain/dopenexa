#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
docker compose up -d
echo "Dopenexa backend is running at http://localhost:8000"
