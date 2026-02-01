#!/bin/bash
# Stop Job Radar Docker containers

set -e

cd "$(dirname "$0")"

echo "Stopping Job Radar..."
docker compose down

echo "Job Radar stopped."
