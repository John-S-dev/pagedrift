#!/bin/bash
# Test script for CLI options - Parallel execution
# Tests -u, -uN, -r, -b flags

set -u  # Exit on undefined variables

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test results directory (for parallel safety)
TEST_RESULTS_DIR="/tmp/cli-test-results-$$"
mkdir -p "$TEST_RESULTS_DIR"

# Cleanup function
cleanup() {
    echo ""
    echo "=== Cleaning up test directories ==="
    rm -rf /tmp/cli-test-* 2>/dev/null || true
    rm -rf "$TEST_RESULTS_DIR" 2>/dev/null || true
    # Kill any hanging processes
    pkill -f "changedetection.py.*cli-test" 2>/dev/null || true
}
trap cleanup EXIT

# Helper to record test result
record_result() {
    local test_num=$1
    local status=$2  # pass or fail
    local message=$3

    echo "$status|$message" > "$TEST_RESULTS_DIR/test_${test_num}.result"
}

# Run a test in background
run_test() {
    local test_num=$1
    local test_name=$2
    local test_func=$3

    (
        echo -e "${YELLOW}[Test $test_num]${NC} $test_name"
        if $test_func "$test_num"; then
            record_result "$test_num" "pass" "$test_name"
            echo -e "${GREEN}✓ PASS${NC}: $test_name"
        else
            record_result "$test_num" "fail" "$test_name"
            echo -e "${RED}✗ FAIL${NC}: $test_name"
        fi
    ) &
}

# =============================================================================
# Test Functions (each runs independently)
# =============================================================================

test_help_flag() {
    local test_id=$1
    timeout 3 python3 changedetection.py --help 2>&1 | grep -q "Add URLs on startup"
}

test_version_flag() {
    local test_id=$1
    timeout 3 python3 changedetection.py --version 2>&1 | grep -qE "changedetection.io [0-9]+\.[0-9]+"
}

test_single_url() {
    local test_id=$1
    local dir="/tmp/cli-test-single-${test_id}-$$"
    timeout 10 python3 changedetection.py -d "$dir" -C -u https://example.com -b &>/dev/null
    # Count watch directories (UUID directories containing watch.json)
    [ "$(find "$dir" -mindepth 2 -maxdepth 2 -name 'watch.json' | wc -l)" -eq 1 ]
}

test_multiple_urls() {
    local test_id=$1
    local dir="/tmp/cli-test-multi-${test_id}-$$"
    timeout 12 python3 changedetection.py -d "$dir" -C \
        -u https://example.com \
        -u https://github.com \
        -u https://httpbin.org \
        -b &>/dev/null
    # Count watch directories (UUID directories containing watch.json)
    [ "$(find "$dir" -mindepth 2 -maxdepth 2 -name 'watch.json' | wc -l)" -eq 3 ]
}

test_url_with_options() {
    local test_id=$1
    local dir="/tmp/cli-test-opts-${test_id}-$$"
    timeout 10 python3 changedetection.py -d "$dir" -C \
        -u https://example.com \
        -u0 '{"title":"Test Site","processor":"text_json_diff"}' \
        -b &>/dev/null
    # Check that at least one watch.json contains the title "Test Site"
    python3 -c "
import json, glob, sys
watch_files = glob.glob('$dir/*/watch.json')
for wf in watch_files:
    with open(wf) as f:
        data = json.load(f)
        if data.get('title') == 'Test Site':
            sys.exit(0)
sys.exit(1)
"
}

test_multiple_urls_with_options() {
    local test_id=$1
    local dir="/tmp/cli-test-multi-opts-${test_id}-$$"
    timeout 12 python3 changedetection.py -d "$dir" -C \
        -u https://example.com \
        -u0 '{"title":"Site One"}' \
        -u https://github.com \
        -u1 '{"title":"Site Two"}' \
        -b &>/dev/null
    # Check that we have 2 watches and both titles are present
    python3 -c "
import json, glob, sys
watch_files = glob.glob('$dir/*/watch.json')
if len(watch_files) != 2:
    sys.exit(1)
titles = []
for wf in watch_files:
    with open(wf) as f:
        data = json.load(f)
        titles.append(data.get('title'))
sys.exit(0 if 'Site One' in titles and 'Site Two' in titles else 1)
"
}

test_batch_mode_exit() {
    local test_id=$1
    local dir="/tmp/cli-test-batch-${test_id}-$$"
    local start=$(date +%s)
    timeout 15 python3 changedetection.py -d "$dir" -C \
        -u https://example.com \
        -b &>/dev/null
    local end=$(date +%s)
    local elapsed=$((end - start))
    [ $elapsed -lt 14 ]
}

test_recheck_all() {
    local test_id=$1
    local dir="/tmp/cli-test-recheck-all-${test_id}-$$"
    # Create a watch using CLI, then recheck it
    timeout 10 python3 changedetection.py -d "$dir" -C -u https://example.com -b &>/dev/null
    # Now recheck all watches
    timeout 10 python3 changedetection.py -d "$dir" -r all -b 2>&1 | grep -q "Queuing"
}

test_recheck_specific() {
    local test_id=$1
    local dir="/tmp/cli-test-recheck-uuid-${test_id}-$$"
    # Create 2 watches using CLI
    timeout 12 python3 changedetection.py -d "$dir" -C \
        -u https://example.com \
        -u https://github.com \
        -b &>/dev/null
    # Get the UUIDs that were created
    local uuids=$(find "$dir" -mindepth 2 -maxdepth 2 -name 'watch.json' -exec dirname {} \; | xargs -n1 basename | tr '\n' ',' | sed 's/,$//')
    # Now recheck specific UUIDs
    timeout 10 python3 changedetection.py -d "$dir" -r "$uuids" -b 2>&1 | grep -q "Queuing"
}

test_combined_operations() {
    local test_id=$1
    local dir="/tmp/cli-test-combined-${test_id}-$$"
    timeout 12 python3 changedetection.py -d "$dir" -C \
        -u https://example.com \
        -u https://github.com \
        -r all \
        -b &>/dev/null
    # Count watch directories (UUID directories containing watch.json)
    [ "$(find "$dir" -mindepth 2 -maxdepth 2 -name 'watch.json' | wc -l)" -eq 2 ]
}

test_invalid_json() {
    local test_id=$1
    local dir="/tmp/cli-test-invalid-${test_id}-$$"
    timeout 5 python3 changedetection.py -d "$dir" -C \
        -u https://example.com \
        -u0 'invalid json here' \
        2>&1 | grep -qi "invalid json\|json decode error"
}

test_create_directory() {
    local test_id=$1
    local dir="/tmp/cli-test-create-${test_id}-$$/nested/path"
    timeout 10 python3 changedetection.py -d "$dir" -C \
        -u https://example.com \
        -b &>/dev/null
    [ -d "$dir" ]
}

# =============================================================================
# Main Test Execution
# =============================================================================

echo "=========================================="
echo "  CLI Options Test Suite (Parallel)"
echo "=========================================="
echo ""

for result_file in "$TEST_RESULTS_DIR"/test_*.result; do
    if [ -f "$result_file" ]; then
        TESTS_RUN=$((TESTS_RUN + 1))
        status=$(cut -d'|' -f1 < "$result_file")
        if [ "$status" = "pass" ]; then
            TESTS_PASSED=$((TESTS_PASSED + 1))
        else
            TESTS_FAILED=$((TESTS_FAILED + 1))
        fi
    fi
done

echo "Tests run:    $TESTS_RUN"
echo -e "${GREEN}Tests passed: $TESTS_PASSED${NC}"
if [ $TESTS_FAILED -gt 0 ]; then
    echo -e "${RED}Tests failed: $TESTS_FAILED${NC}"
else
    echo -e "${GREEN}Tests failed: $TESTS_FAILED${NC}"
fi
echo "=========================================="
echo ""

# Exit with appropriate code
if [ $TESTS_FAILED -gt 0 ]; then
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
else
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
fi
