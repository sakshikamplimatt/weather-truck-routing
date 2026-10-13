#!/usr/bin/env bash
# Single-service build: React -> frontend/dist, served by Django via WhiteNoise.
set -euo pipefail
(cd frontend && npm ci || npm install && npm run build)
pip install -r backend/requirements.txt
