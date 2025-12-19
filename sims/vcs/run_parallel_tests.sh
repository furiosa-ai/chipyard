#!/bin/bash
# RISC-V DV Parallel Test Runner
#
# Usage: TIMEOUT_CYCLES=1000000 DEBUG=1 ./run_parallel_tests.sh
#
# Options:
#   RISCV_DV_OUT_DIR - Test binary directory (default: /root/riscv-dv/RV32IMC/asm_test)
#   CONFIG           - Rocket config (default: RV32RocketConfig)
#   TIMEOUT_CYCLES   - Max simulation cycles (default: 10000000)
#   MAX_PARALLEL     - Parallel jobs (default: nproc)
#   TEST_PATTERN     - File pattern (default: *.o)
#   EXCLUDE_PATTERN  - Regex pattern to exclude tests (default: none)
#   DEBUG            - Enable waveform: 1=on, 0=off (default: 0)

source ./env.sh

# Configuration
DEFAULT_RISCV_DV_OUT_DIR="out"
DEFAULT_CONFIG="RV32RocketConfig"
TIMEOUT_CYCLES=${TIMEOUT_CYCLES:-10000000}
TEST_PATTERN=${TEST_PATTERN:-"*.o"}
GEN_VECTOR=${GEN_VECTOR:-0}
DEBUG=${DEBUG:-0} # 파형 생성할 때

RISCV_DV_OUT_DIR="${RISCV_DV_OUT_DIR:-${DEFAULT_RISCV_DV_OUT_DIR}}"
CONFIG="${CONFIG:-${DEFAULT_CONFIG}}"
MAX_PARALLEL=${MAX_PARALLEL:-$(nproc)}
#EXCLUDE_PATTERN="^(riscv_rand_instr_test_|riscv_arithmetic_basic_test_)"
EXCLUDE_PATTERN=${EXCLUDE_PATTERN:-""}

BINARY_DIR="${RISCV_DV_DIR}/${RISCV_DV_OUT_DIR}/asm_test"

if [[ ${GEN_VECTOR} -eq 1 ]]; then
    export RISCV_DV_OUT_DIR
    ./generate_test_vector.sh "${RISCV_DV_OUT_DIR}"
fi

# Setup
RESULT_DIR=$(mktemp -d)
declare -a PIDS=()

# Cleanup handler
cleanup() {
    echo -e "\nCleaning up..."
    for pid in "${PIDS[@]}"; do
        pkill -TERM -P "$pid" 2>/dev/null || true
        kill -TERM "$pid" 2>/dev/null || true
    done
    pkill -f "simv-chipyard.*${CONFIG}" 2>/dev/null || true
    pkill -f "timeout.*make.*${CONFIG}" 2>/dev/null || true
    pkill -f "make.*CONFIG=${CONFIG}" 2>/dev/null || true
    sleep 1
    for pid in "${PIDS[@]}"; do
        pkill -KILL -P "$pid" 2>/dev/null || true
        kill -KILL "$pid" 2>/dev/null || true
    done
    rm -rf "${RESULT_DIR}"
    exit 130
}
trap cleanup SIGINT SIGTERM

# Run single test
run_test() {
    local test_file=$1
    local test_name=$(basename "$test_file" .o)
    local log_file="${test_name}.log"
    local result_file="${RESULT_DIR}/${test_name}.result"
    
    echo "[$(date '+%H:%M:%S')] Starting: ${test_name}"
    
    # Choose make target based on DEBUG flag
    local make_target="run-binary"
    [[ "${DEBUG}" == "1" ]] && make_target="run-binary-debug"
    
    timeout 3600 make CONFIG="${CONFIG}" BINARY="${test_file}" \
        TIMEOUT_CYCLES="${TIMEOUT_CYCLES}" ${make_target} > "${log_file}" 2>&1
    local exit_code=$?
    
    # Check result
    if [[ $exit_code -eq 124 ]]; then
        echo "TIMEOUT:${test_name}" > "${result_file}"
        echo "[$(date '+%H:%M:%S')] TIMEOUT: ${test_name} (wall-clock)"
    elif timeout 5 grep -qE 'Fatal:.*TestDriver.*at time.*ps' "${log_file}" 2>/dev/null; then
        echo "TIMEOUT:${test_name}" > "${result_file}"
        echo "[$(date '+%H:%M:%S')] TIMEOUT: ${test_name} (max-cycles)"
    elif timeout 5 grep -iE "Error:|Assertion failed" "${log_file}" | grep -qvE "Fatal:.*TestDriver.*at time" 2>/dev/null; then
        echo "FAILED:${test_name}" > "${result_file}"
        echo "[$(date '+%H:%M:%S')] FAILED: ${test_name}"
    elif [[ $exit_code -ne 0 ]]; then
        echo "FAILED:${test_name}" > "${result_file}"
        echo "[$(date '+%H:%M:%S')] FAILED: ${test_name} (exit: ${exit_code})"
    else
        echo "PASSED:${test_name}" > "${result_file}"
        echo "[$(date '+%H:%M:%S')] PASSED: ${test_name}"
    fi
}

# Collect tests
TESTS=()
while IFS= read -r file; do
    basename=$(basename "$file")
    [[ -z "${EXCLUDE_PATTERN}" ]] || ! echo "${basename}" | grep -qE "${EXCLUDE_PATTERN}" && TESTS+=("${basename}")
done < <(find "${BINARY_DIR}" -name "${TEST_PATTERN}" -type f | sort)

[[ ${#TESTS[@]} -eq 0 ]] && { echo "No tests found!"; exit 1; }

# Print config
echo "========================================"
echo "RISC-V DV Parallel Test Runner"
echo "========================================"
echo "Config:       ${CONFIG}"
echo "Binary dir:   ${BINARY_DIR}"
echo "Tests:        ${#TESTS[@]}"
echo "Parallel:     ${MAX_PARALLEL}"
echo "Cycles:       ${TIMEOUT_CYCLES}"
echo "Pattern:      ${TEST_PATTERN}"
echo "Debug mode:   ${DEBUG}"
echo "========================================"
echo ""

# Run tests in parallel
for test in "${TESTS[@]}"; do
    # Wait for available slot
    while [[ ${#PIDS[@]} -ge ${MAX_PARALLEL} ]]; do
        new_pids=()
        for pid in "${PIDS[@]}"; do
            kill -0 "$pid" 2>/dev/null && new_pids+=("$pid") || wait "$pid" 2>/dev/null || true
        done
        PIDS=("${new_pids[@]}")
        [[ ${#PIDS[@]} -ge ${MAX_PARALLEL} ]] && sleep 0.5
    done
    
    (run_test "${BINARY_DIR}/${test}") &
    PIDS+=($!)
done

# Wait for completion
echo -e "\nWaiting for tests to complete..."
for pid in "${PIDS[@]}"; do wait "$pid" 2>/dev/null || true; done

sleep 1

# Collect results
PASSED=0
FAILED=()
TIMEOUTS=()
for test in "${TESTS[@]}"; do
    test_name=$(basename "$test" .o)
    result_file="${RESULT_DIR}/${test_name}.result"
    if [[ -f "${result_file}" ]]; then
        if grep -q "^PASSED:" "${result_file}"; then
            ((PASSED++))
        elif grep -q "^TIMEOUT:" "${result_file}"; then
            TIMEOUTS+=("${test_name}")
        else
            FAILED+=("${test_name}")
        fi
    else
        echo "[ERROR] Result file not found for ${test_name}!"
        FAILED+=("${test_name}")
    fi
done

# Print summary
echo ""
echo "========================================"
echo "Summary: ${CONFIG}"
echo "========================================"
echo "Total:    ${#TESTS[@]}"
echo "Passed:   ${PASSED}"
echo "Failed:   ${#FAILED[@]}"
echo "Timed Out: ${#TIMEOUTS[@]}"
echo "========================================"

if [[ ${#FAILED[@]} -gt 0 ]]; then
    echo -e "\nFailed tests:"
    printf '  - %s\n' "${FAILED[@]}"
fi

if [[ ${#TIMEOUTS[@]} -gt 0 ]]; then
    echo -e "\nTimed Out tests:"
    printf '  - %s\n' "${TIMEOUTS[@]}"
fi

#rm -rf "${RESULT_DIR}"
#[[ ${#FAILED[@]} -eq 0 && ${#TIMEOUTS[@]} -eq 0 ]] && echo -e "\nAll tests passed! ✓" && exit 0 || exit 1

./compare_all.sh "${BINARY_DIR}" "output/chipyard.harness.TestHarness.${CONFIG}"