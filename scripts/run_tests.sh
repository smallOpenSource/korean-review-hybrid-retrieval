#!/bin/bash
# =============================================================================
# Test Runner Script
# =============================================================================

set -e

cd "$(dirname "$0")/.."

# Load environment if exists
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

PYTHON_PATH=${PYTHON_PATH:-python}

echo "============================================="
echo "  App Reviews Analysis - Test Runner"
echo "============================================="
echo ""

# Check if pytest is installed
if ! $PYTHON_PATH -c "import pytest" 2>/dev/null; then
    echo "⚠ pytest가 설치되어 있지 않습니다."
    echo "  pip install pytest pytest-cov pytest-asyncio"
    exit 1
fi

# Parse arguments
RUN_COVERAGE=false
RUN_VERBOSE=false
TEST_PATH="test"

while [[ $# -gt 0 ]]; do
    case $1 in
        --cov|--coverage)
            RUN_COVERAGE=true
            shift
            ;;
        -v|--verbose)
            RUN_VERBOSE=true
            shift
            ;;
        --unit)
            TEST_PATH="test -m unit"
            shift
            ;;
        --integration)
            TEST_PATH="test -m integration"
            shift
            ;;
        *)
            TEST_PATH="$1"
            shift
            ;;
    esac
done

# Build pytest command
PYTEST_CMD="$PYTHON_PATH -m pytest"

if [ "$RUN_VERBOSE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD -v"
fi

if [ "$RUN_COVERAGE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD --cov=app --cov-report=term-missing --cov-report=html:coverage_report"
fi

PYTEST_CMD="$PYTEST_CMD $TEST_PATH"

echo "실행 명령어: $PYTEST_CMD"
echo ""

# Run tests
$PYTEST_CMD

echo ""
echo "============================================="
echo "  테스트 완료"
echo "============================================="

if [ "$RUN_COVERAGE" = true ]; then
    echo ""
    echo "커버리지 리포트: coverage_report/index.html"
fi
