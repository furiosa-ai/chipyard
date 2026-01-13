#!/usr/bin/env python3
"""
RISC-V Unit Tests Parallel Runner

Usage examples:
    ./run_parallel_unit_tests.py
    ./run_parallel_unit_tests.py --config RV32RocketConfig --parallel 20
    ./run_parallel_unit_tests.py --pattern "rv32ui-p-*" --timeout-cycles 10000000
    ./run_parallel_unit_tests.py --exclude ".*-v-.*"
"""

import os
import sys
import subprocess
import argparse
import tempfile
import shutil
import re
import signal
import time
from pathlib import Path
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Tuple, Dict

# Global process tracking for cleanup
active_processes = []

def timestamp():
    """Return formatted timestamp"""
    return datetime.now().strftime('%H:%M:%S')

def get_simv_path(script_dir: Path, config: str, debug: bool = False) -> Path:
    """Get the simv binary path for the given config"""
    suffix = "-debug" if debug else ""
    return script_dir / f"simv-chipyard.harness-{config}{suffix}"

def check_and_build_simv(script_dir: Path, config: str, debug: bool = False) -> bool:
    """
    Check if simv exists, build if not.
    Returns True if simv is ready, False if build failed.
    """
    simv_path = get_simv_path(script_dir, config, debug)
    simv_type = "debug" if debug else "default"
    
    if simv_path.exists():
        print(f"[{timestamp()}] Found existing simv ({simv_type}): {simv_path.name}")
        return True
    
    print(f"[{timestamp()}] simv not found: {simv_path.name}")
    print(f"[{timestamp()}] Building simv for {config} ({simv_type})...")
    print("=" * 50)
    
    make_target = "debug" if debug else "default"
    cmd = ['make', f'CONFIG={config}', make_target]
    
    try:
        proc = subprocess.run(cmd, cwd=script_dir, check=False)
        
        if proc.returncode != 0:
            print(f"[{timestamp()}] ERROR: simv build failed with exit code {proc.returncode}")
            return False
        
        if not simv_path.exists():
            print(f"[{timestamp()}] ERROR: Build completed but simv not found at {simv_path}")
            return False
        
        print("=" * 50)
        print(f"[{timestamp()}] simv build complete: {simv_path.name}")
        return True
        
    except Exception as e:
        print(f"[{timestamp()}] ERROR: Build failed with exception: {e}")
        return False

def cleanup_handler(signum, frame):
    """Handle SIGINT/SIGTERM and cleanup processes"""
    print("\n\nCleaning up...")
    
    for proc in active_processes:
        try:
            proc.terminate()
        except:
            pass
    
    time.sleep(1)
    
    for proc in active_processes:
        try:
            proc.kill()
        except:
            pass
    
    sys.exit(130)

def check_log_for_pattern(log_file: Path, pattern: str) -> bool:
    """Check if pattern exists in log file."""
    if not log_file.exists():
        return False
    
    try:
        regex = re.compile(pattern, re.IGNORECASE if 'error' in pattern.lower() else 0)
        with open(log_file, 'r', errors='ignore') as f:
            for line in f:
                if regex.search(line):
                    return True
        return False
    except Exception as e:
        print(f"[WARNING] Error reading log file {log_file}: {e}")
        return False

def run_single_test(test_file: Path, config: str, timeout_cycles: int, 
                   debug: bool, log_dir: Path, result_dir: Path,
                   wall_timeout: int, script_dir: Path) -> Tuple[str, str]:
    """
    Run a single test and return (test_name, result_status)
    """
    test_name = test_file.name  # filename (no extension for unit tests)
    log_file = log_dir / f"{test_name}.log"
    result_file = result_dir / f"{test_name}.result"
    output_dir = script_dir / "output" / f"chipyard.harness.TestHarness.{config}"
    out_file = output_dir / f"{test_name}.out"
    
    print(f"[{timestamp()}] Starting: {test_name}")
    
    # Choose make target
    make_target = "run-binary-debug" if debug else "run-binary"
    
    # Build command
    cmd = [
        'make',
        f'CONFIG={config}',
        f'BINARY={test_file}',
        f'TIMEOUT_CYCLES={timeout_cycles}',
        'BREAK_SIM_PREREQ=1',
        make_target
    ]
    
    # Run with timeout
    try:
        with open(log_file, 'w') as log_f:
            proc = subprocess.Popen(
                cmd,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                cwd=script_dir,
                preexec_fn=os.setsid
            )
            active_processes.append(proc)
            
            try:
                exit_code = proc.wait(timeout=wall_timeout)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                time.sleep(1)
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except:
                    pass
                exit_code = 124
            finally:
                if proc in active_processes:
                    active_processes.remove(proc)
    except Exception as e:
        print(f"[{timestamp()}] ERROR: {test_name} - {e}")
        result_file.write_text(f"FAILED:{test_name}")
        return test_name, "FAILED"
    
    # Determine result by checking .out file first, then log file
    if exit_code == 124:
        status = "TIMEOUT"
        reason = "(wall-clock)"
    elif out_file.exists() and check_log_for_pattern(out_file, r'\*\*\* PASSED \*\*\*'):
        status = "PASSED"
        reason = ""
    elif out_file.exists() and check_log_for_pattern(out_file, r'\*\*\* FAILED \*\*\*'):
        status = "FAILED"
        reason = "(test failed)"
    elif check_log_for_pattern(log_file, r'Fatal:'):
        status = "FAILED"
        reason = "(Fatal error)"
    elif check_log_for_pattern(log_file, r'Fatal:.*TestDriver.*at time.*ps'):
        status = "TIMEOUT"
        reason = "(max-cycles)"
    elif exit_code != 0:
        status = "FAILED"
        reason = f"(exit: {exit_code})"
    else:
        # exit_code == 0 but no explicit pass pattern
        status = "FAILED"
        reason = "(no pass pattern)"
    
    # Write result
    result_file.write_text(f"{status}:{test_name}")
    print(f"[{timestamp()}] {status}: {test_name} {reason}")
    
    return test_name, status

def collect_tests(binary_dir: Path, pattern: str, exclude_pattern: str) -> List[Path]:
    """Collect test files matching pattern and not matching exclude pattern"""
    tests = []
    
    for test_file in sorted(binary_dir.glob(pattern)):
        if not test_file.is_file():
            continue
        
        # Skip .dump files
        if test_file.suffix == '.dump':
            continue
        
        # Check exclude pattern
        if exclude_pattern:
            try:
                if re.search(exclude_pattern, test_file.name):
                    continue
            except re.error as e:
                print(f"[WARNING] Invalid exclude pattern '{exclude_pattern}': {e}")
                sys.exit(1)
        
        tests.append(test_file)
    
    return tests

def main():
    parser = argparse.ArgumentParser(
        description='RISC-V Unit Tests Parallel Runner',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    script_dir = Path(__file__).parent.resolve()
    default_binary_dir = script_dir / '../../toolchains/riscv-tools/riscv-tests/isa'
    
    parser.add_argument('--binary-dir', '-b',
                        default=str(default_binary_dir),
                        help=f'Binary directory (default: {default_binary_dir})')
    parser.add_argument('--config', '-c',
                        default='RV32RocketConfig',
                        help='Rocket config (default: RV32RocketConfig)')
    parser.add_argument('--timeout-cycles', '-t',
                        type=int,
                        default=10000000,
                        help='Max simulation cycles (default: 10000000)')
    parser.add_argument('--wall-timeout', '-w',
                        type=int,
                        default=1000,
                        help='Wall-clock timeout in seconds (default: 1000)')
    parser.add_argument('--parallel', '-j',
                        type=int,
                        default=20,
                        help='Number of parallel jobs (default: 20)')
    parser.add_argument('--pattern', '-p',
                        default='rv32*',
                        help='Test file pattern (default: rv32*)')
    parser.add_argument('--exclude', '-e',
                        default='',
                        help='Regex pattern to exclude tests (applied to basename)')
    parser.add_argument('--debug', '-d',
                        action='store_true',
                        help='Enable waveform generation')
    parser.add_argument('--log-dir',
                        default='logs_unit',
                        help='Directory for log files (default: logs_unit)')
    
    args = parser.parse_args()
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, cleanup_handler)
    signal.signal(signal.SIGTERM, cleanup_handler)
    
    # Resolve paths
    binary_dir = Path(args.binary_dir)
    
    if not binary_dir.exists():
        print(f"Error: Binary directory not found: {binary_dir}")
        sys.exit(1)
    
    # Collect tests
    tests = collect_tests(binary_dir, args.pattern, args.exclude)
    
    if not tests:
        print(f"No tests found matching pattern '{args.pattern}'!")
        sys.exit(1)
    
    # Check and build simv if needed
    if not check_and_build_simv(script_dir, args.config, args.debug):
        print("Error: Failed to build simv. Cannot run tests.")
        sys.exit(1)
    
    # Create directories
    log_dir = Path(args.log_dir)
    log_dir.mkdir(exist_ok=True)
    result_dir = Path(tempfile.mkdtemp(prefix='unit_test_results_'))
    
    try:
        # Print configuration
        print("=" * 60)
        print("RISC-V Unit Tests Parallel Runner")
        print("=" * 60)
        print(f"Config:         {args.config}")
        print(f"Binary dir:     {binary_dir}")
        print(f"Log dir:        {log_dir.absolute()}")
        print(f"Tests:          {len(tests)}")
        print(f"Parallel:       {args.parallel}")
        print(f"Timeout cycles: {args.timeout_cycles}")
        print(f"Wall timeout:   {args.wall_timeout}s")
        print(f"Pattern:        {args.pattern}")
        print(f"Exclude:        {args.exclude or '(none)'}")
        print(f"Debug mode:     {args.debug}")
        print("=" * 60)
        print()
        
        # Run tests in parallel
        results = {}
        with ProcessPoolExecutor(max_workers=args.parallel) as executor:
            futures = {
                executor.submit(
                    run_single_test,
                    test_file,
                    args.config,
                    args.timeout_cycles,
                    args.debug,
                    log_dir,
                    result_dir,
                    args.wall_timeout,
                    script_dir
                ): test_file for test_file in tests
            }
            
            for future in as_completed(futures):
                try:
                    test_name, status = future.result()
                    results[test_name] = status
                except Exception as e:
                    test_file = futures[future]
                    print(f"[ERROR] Exception for {test_file.name}: {e}")
                    results[test_file.name] = "FAILED"
        
        print("\nWaiting for all tests to complete...")
        time.sleep(1)
        
        # Collect and categorize results
        passed = []
        failed = []
        timeouts = []
        
        for test_name, status in results.items():
            if status == "PASSED":
                passed.append(test_name)
            elif status == "TIMEOUT":
                timeouts.append(test_name)
            else:
                failed.append(test_name)
        
        # Print summary
        print()
        print("=" * 60)
        print(f"Summary: {args.config}")
        print("=" * 60)
        print(f"Total:      {len(tests)}")
        print(f"Passed:     {len(passed)}")
        print(f"Failed:     {len(failed)}")
        print(f"Timed Out:  {len(timeouts)}")
        print("=" * 60)
        
        if failed:
            print("\nFailed tests:")
            for test in sorted(failed):
                print(f"  - {test}")
        
        if timeouts:
            print("\nTimed Out tests:")
            for test in sorted(timeouts):
                print(f"  - {test}")
        
        # Exit with appropriate code
        if failed or timeouts:
            sys.exit(1)
        else:
            print("\nAll tests passed! ✓")
            sys.exit(0)
    
    finally:
        # Cleanup temp directory
        if result_dir.exists():
            shutil.rmtree(result_dir)

if __name__ == '__main__':
    main()
