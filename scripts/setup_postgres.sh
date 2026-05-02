#!/bin/bash
# Setup PostgreSQL for NetOps

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== NetOps PostgreSQL Setup ==="
echo ""

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker is not installed or not in PATH"
    echo "Please install Docker Desktop or Docker Engine first."
    exit 1
fi

# Start PostgreSQL with Docker Compose
echo "Starting PostgreSQL container..."
cd "$PROJECT_ROOT/docker"
docker compose up -d postgres

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL to be ready..."
for i in {1..30}; do
    if docker exec netops-postgres pg_isready -U netops -d netops > /dev/null 2>&1; then
        echo "PostgreSQL is ready!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "ERROR: PostgreSQL did not start in time"
        exit 1
    fi
    sleep 1
done

# Run migrations
echo ""
echo "Running database migrations..."
cd "$PROJECT_ROOT"

# Activate virtual environment if it exists
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

python scripts/migrate.py upgrade head

echo ""
echo "=== Setup Complete ==="
echo ""
echo "PostgreSQL is running at: localhost:5432"
echo "Database: netops"
echo "Username: netops"
echo "Password: netops"
echo ""
echo "To stop PostgreSQL: docker compose -f docker/docker-compose.yml down"
echo "To view logs: docker compose -f docker/docker-compose.yml logs -f postgres"
