#!/usr/bin/env python3
import os
import sys
import subprocess
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description='Generate RISC-V test vectors')
    parser.add_argument('--out-dir', '-o', 
                        default='out',
                        help='Output directory (default: out)')
    parser.add_argument('--target', 
                        default='rv32imc',
                        help='Target ISA (default: rv32imc)')
    parser.add_argument('--iss-timeout', 
                        type=int,
                        default=1000,
                        help='ISS timeout in seconds (default: 1000)')
    parser.add_argument('--testlist', '-tl',
                        help='Test list YAML file (e.g., ./yaml/base_testlist.yaml)')
    args = parser.parse_args()
    
    # Get riscv-dv directory using relative path
    script_dir = Path(__file__).parent
    riscv_dv_dir = script_dir / '../../toolchains/riscv-tools/riscv-dv'
    
    if not riscv_dv_dir.exists():
        print(f"Error: riscv-dv directory not found at {riscv_dv_dir}")
        sys.exit(1)
    
    # Change to riscv-dv directory
    os.chdir(riscv_dv_dir)
    
    # Build command
    cmd = [
        'python3', 'run.py',
        '--target', args.target,
        '--iss_timeout', str(args.iss_timeout),
        '-o', args.out_dir
    ]
    
    # Add testlist if specified
    if args.testlist:
        cmd.extend(['-tl', args.testlist])
    
    print(f"Running: {' '.join(cmd)}")
    print(f"Working directory: {os.getcwd()}")
    
    # Run the command
    subprocess.run(cmd, check=True)
    
    print("Test vector generation complete!")

if __name__ == '__main__':
    main()
