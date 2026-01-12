#!/usr/bin/env python3
"""
Compare all test results between Rocket and Spike

Usage:
    ./compare_all.py <asm_dir> <log_dir>
    ./compare_all.py /path/to/asm_test output/chipyard.harness.TestHarness.RV32RocketConfig
"""

import sys
import subprocess
from pathlib import Path
from typing import List, Tuple

def main():
    if len(sys.argv) != 3:
        print("Usage: compare_all.py <asm_dir> <log_dir>")
        print("Example: ./compare_all.py /root/riscv-dv/out/asm_test output/chipyard.harness.TestHarness.RV32RocketConfig")
        sys.exit(1)
    
    asm_dir = Path(sys.argv[1])
    log_dir = Path(sys.argv[2])
    
    # Get spike log directory
    spike_log_dir = asm_dir.parent / 'spike_sim'
    
    # Validate directories
    if not asm_dir.exists():
        print(f"Error: ASM directory not found: {asm_dir}", file=sys.stderr)
        sys.exit(1)
    
    if not log_dir.exists():
        print(f"Error: Log directory not found: {log_dir}", file=sys.stderr)
        sys.exit(1)
    
    # Get compare script
    script_dir = Path(__file__).parent
    compare_script = script_dir / 'compare.py'
    
    if not compare_script.exists():
        sys.exit(1)
    
    # Collect all .o files
    test_objects = sorted(asm_dir.glob('*.o'))
    
    if not test_objects:
        print(f"Warning: No .o files found in {asm_dir}")
        sys.exit(0)
    
    print(f"Found {len(test_objects)} tests to compare")
    print(f"ASM dir:       {asm_dir}")
    print(f"Rocket logs:   {log_dir}")
    print(f"Spike logs:    {spike_log_dir}")
    print(f"Compare tool:  {compare_script.name}")
    print("=" * 60)
    print()
    
    # Run comparisons
    results: List[Tuple[str, bool, str]] = []
    pass_count = 0
    fail_count = 0
    
    for obj in test_objects:
        test_name = obj.stem  # filename without extension
        rocket_log = log_dir / f"{test_name}.out"
        spike_log = spike_log_dir / f"{test_name}.log"
        compare_log = log_dir / f"compare_{test_name}.log"
        
        # Check if required files exist
        if not rocket_log.exists():
            results.append((test_name, False, f"Rocket log not found: {rocket_log}"))
            fail_count += 1
            continue
        
        if not spike_log.exists():
            results.append((test_name, False, f"Spike log not found: {spike_log}"))
            fail_count += 1
            continue
        
        # Run comparison
        try:
            if compare_script.suffix == '.py':
                cmd = [
                    str(compare_script),
                    '--rtl', str(rocket_log),
                    '--spike', str(spike_log)
                ]
            else:
                cmd = [
                    str(compare_script),
                    str(rocket_log),
                    str(spike_log)
                ]
            
            with open(compare_log, 'w') as log_f:
                result = subprocess.run(
                    cmd,
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    timeout=60
                )
            
            # Check if comparison passed
            with open(compare_log, 'r') as log_f:
                log_content = log_f.read()
                if '[PASSED]' in log_content:
                    import re
                    match = re.search(r'\[PASSED\]:\s*(\d+)\s*matched', log_content)
                    if match and int(match.group(1)) > 0:
                        results.append((test_name, True, "PASSED"))
                        pass_count += 1
                        print(f"[PASS] {test_name}")
                    else:
                        # PASSED but 0 matched - this is suspicious
                        results.append((test_name, False, "0 matched (empty trace?)"))
                        fail_count += 1
                        print(f"[FAIL] {test_name} (0 matched)")
                else:
                    results.append((test_name, False, f"FAILED or missing result in {compare_log}"))
                    fail_count += 1
                    print(f"[FAIL] {test_name}")
        
        except subprocess.TimeoutExpired:
            results.append((test_name, False, "Comparison timed out"))
            fail_count += 1
            print(f"[FAIL] {test_name} (timeout)")
        
        except Exception as e:
            results.append((test_name, False, f"Exception: {e}"))
            fail_count += 1
            print(f"[FAIL] {test_name} (error: {e})")
    
    # Print summary
    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Total:  {len(test_objects)}")
    print(f"Passed: {pass_count}")
    print(f"Failed: {fail_count}")
    print("=" * 60)
    
    if fail_count > 0:
        print("\nFailed tests:")
        for test_name, passed, reason in results:
            if not passed:
                print(f"  - {test_name}: {reason}")
    
    # Exit with appropriate code
    sys.exit(0 if fail_count == 0 else 1)

if __name__ == '__main__':
    main()
