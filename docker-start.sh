#!/bin/bash
# Start Job Radar in Docker

set -e

cd "$(dirname "$0")"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Job Radar...${NC}"

# Create data directory if needed
mkdir -p data logs

# Check for required files
if [ ! -f "config/profile.yaml" ]; then
    if [ -f "config/profile.yaml.example" ]; then
        echo -e "${YELLOW}Creating config/profile.yaml from example...${NC}"
        cp config/profile.yaml.example config/profile.yaml
        echo -e "${YELLOW}Please edit config/profile.yaml with your settings.${NC}"
    else
        echo "Error: config/profile.yaml not found"
        exit 1
    fi
fi

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo -e "${YELLOW}Creating .env from example...${NC}"
        cp .env.example .env
        echo -e "${YELLOW}Please edit .env with your settings.${NC}"
    else
        echo "Error: .env not found"
        exit 1
    fi
fi

# Create empty credential files if they don't exist (for volume mounts)
touch credentials.json 2>/dev/null || true
touch token.json 2>/dev/null || true

# Start services
echo "Building and starting containers..."
docker compose up -d --build

echo ""
echo -e "${GREEN}Job Radar is running!${NC}"
echo ""
echo "Dashboard: http://localhost:8501"
echo ""
echo "View logs:"
echo "  docker compose logs -f dashboard"
echo "  docker compose logs -f scanner"
echo ""
echo "Stop with: ./docker-stop.sh"
