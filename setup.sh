#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
echo "Dopenexa development setup"
command -v docker >/dev/null || { echo "Docker Desktop is required."; exit 1; }
command -v xcodebuild >/dev/null || echo "Note: run this script on macOS with Xcode installed to validate the iOS project."
docker compose config >/dev/null
echo "Starting Dopenexa backend services..."
docker compose up -d --build
echo "Backend: http://localhost:8000"
echo "Open ios/Dopenexa.xcodeproj in Xcode and run the Dopenexa scheme."
