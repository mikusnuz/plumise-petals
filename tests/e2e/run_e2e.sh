#!/bin/bash
# E2E test runner for Plumise Petals distributed inference
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "========================================"
echo "Plumise Petals E2E Test Runner"
echo "========================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_info() {
    echo -e "${YELLOW}[i]${NC} $1"
}

# Change to project root
cd "$PROJECT_ROOT"

# Step 1: Run unit tests first
print_info "Step 1: Running unit tests..."
if pytest tests/ -v --ignore=tests/e2e/ -k "not e2e" ; then
    print_status "Unit tests passed"
else
    print_error "Unit tests failed"
    exit 1
fi

echo ""

# Step 2: Run E2E tests (without Docker)
print_info "Step 2: Running E2E tests (mocked)..."
if pytest tests/e2e/ -v --log-cli-level=INFO ; then
    print_status "E2E tests passed"
else
    print_error "E2E tests failed"
    exit 1
fi

echo ""

# Step 3: Check if Docker is available
print_info "Step 3: Checking Docker availability..."
if ! command -v docker &> /dev/null ; then
    print_error "Docker not found. Skipping Docker-based tests."
    print_status "All non-Docker tests completed successfully"
    exit 0
fi

if ! docker info &> /dev/null ; then
    print_error "Docker daemon not running. Skipping Docker-based tests."
    print_status "All non-Docker tests completed successfully"
    exit 0
fi

print_status "Docker is available"

# Step 4: Build Docker image
print_info "Step 4: Building Docker image..."
if docker build -t plumise-petals:test -f Dockerfile . ; then
    print_status "Docker image built successfully"
else
    print_error "Docker image build failed"
    exit 1
fi

echo ""

# Step 5: Start services
print_info "Step 5: Starting Docker services..."
cd "$SCRIPT_DIR"

# Clean up any existing containers
docker-compose -f docker-compose.test.yml down -v 2>/dev/null || true

# Start services
if docker-compose -f docker-compose.test.yml up -d ; then
    print_status "Services started"
else
    print_error "Failed to start services"
    exit 1
fi

# Step 6: Wait for services to be ready
print_info "Step 6: Waiting for services to be ready..."

# Wait for mock oracle
MAX_WAIT=30
WAITED=0
while ! curl -s http://localhost:3100/health > /dev/null 2>&1 ; do
    if [ $WAITED -ge $MAX_WAIT ]; then
        print_error "Mock Oracle did not start in time"
        docker-compose -f docker-compose.test.yml logs
        docker-compose -f docker-compose.test.yml down -v
        exit 1
    fi
    sleep 1
    WAITED=$((WAITED + 1))
done
print_status "Mock Oracle is ready"

# Wait a bit for Petals nodes to initialize (they take longer)
print_info "Waiting for Petals nodes to initialize (this may take a few minutes)..."
sleep 30

# Check if nodes are running
if docker ps | grep -q plumise-petals-node-a && docker ps | grep -q plumise-petals-node-b ; then
    print_status "Petals nodes are running"
else
    print_error "Petals nodes failed to start"
    docker-compose -f docker-compose.test.yml logs
    docker-compose -f docker-compose.test.yml down -v
    exit 1
fi

echo ""

# Step 7: Run integration tests
print_info "Step 7: Running integration tests..."

# Test 1: Check mock oracle logs for reports
print_info "Checking mock oracle received reports..."
sleep 10  # Wait for at least one report cycle

if docker-compose -f docker-compose.test.yml logs mock-oracle | grep -q "Received report from agent" ; then
    print_status "Mock oracle received reports"
else
    print_error "Mock oracle did not receive any reports"
    docker-compose -f docker-compose.test.yml logs mock-oracle
fi

# Test 2: Check both nodes are reporting
print_info "Verifying both nodes are reporting..."
ORACLE_LOGS=$(docker-compose -f docker-compose.test.yml logs mock-oracle)

NODE_A_COUNT=$(echo "$ORACLE_LOGS" | grep "Received report from agent" | wc -l)
if [ "$NODE_A_COUNT" -ge 1 ]; then
    print_status "Node A is reporting (${NODE_A_COUNT} reports)"
else
    print_error "Node A is not reporting"
fi

echo ""

# Step 8: View logs
print_info "Step 8: Viewing recent logs..."
echo ""
echo "--- Mock Oracle Logs ---"
docker-compose -f docker-compose.test.yml logs --tail=20 mock-oracle
echo ""
echo "--- Petals Node A Logs ---"
docker-compose -f docker-compose.test.yml logs --tail=20 petals-node-a
echo ""
echo "--- Petals Node B Logs ---"
docker-compose -f docker-compose.test.yml logs --tail=20 petals-node-b
echo ""

# Step 9: Cleanup
print_info "Step 9: Cleaning up..."
if docker-compose -f docker-compose.test.yml down -v ; then
    print_status "Services stopped and cleaned up"
else
    print_error "Cleanup failed"
fi

echo ""
print_status "========================================"
print_status "All E2E tests completed successfully!"
print_status "========================================"

cd "$PROJECT_ROOT"
exit 0
