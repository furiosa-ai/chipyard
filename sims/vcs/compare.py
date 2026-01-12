#!/usr/bin/env python3
import os
import sys
import subprocess
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description='Compare RTL and Spike dumps')
    parser.add_argument('--rtl', '-r', required=True, help='RTL dump file')
    parser.add_argument('--spike', '-s', required=True, help='Spike dump file')
    args = parser.parse_args()
    
    # Get riscv-dv directory using relative path
    script_dir = Path(__file__).parent
    riscv_dv_dir = script_dir / '../../toolchains/riscv-tools/riscv-dv'
    
    if not riscv_dv_dir.exists():
        print(f"Error: riscv-dv directory not found at {riscv_dv_dir}")
        sys.exit(1)
    
    rtl_csv = f"{args.rtl}.csv"
    spike_csv = f"{args.spike}.csv"
    
    print(f"Converting RTL dump to CSV: {args.rtl} -> {rtl_csv}")
    subprocess.run([
        'python3',
        str(riscv_dv_dir / 'scripts/rocket_log_to_trace_csv.py'),
        '--log', args.rtl,
        '--csv', rtl_csv,
        '--rv32'
    ], check=True)
    
    print(f"Converting Spike dump to CSV: {args.spike} -> {spike_csv}")
    subprocess.run([
        'python3',
        str(riscv_dv_dir / 'scripts/spike_log_to_trace_csv.py'),
        '--log', args.spike,
        '--csv', spike_csv,
        '-f'
    ], check=True)
    
    print(f"Comparing traces: {rtl_csv} vs {spike_csv}")
    subprocess.run([
        'python3',
        str(riscv_dv_dir / 'scripts/instr_trace_compare.py'),
        '--csv_file_1', rtl_csv,
        '--csv_file_2', spike_csv
    ], check=True)
    
    print("Comparison complete!")

if __name__ == '__main__':
    main()
