#!/bin/bash

DEFAULT_RISCV_DV_OUT_DIR="out"
RISCV_DV_OUT_DIR="${RISCV_DV_OUT_DIR:-${DEFAULT_RISCV_DV_OUT_DIR}}"
cd $RISCV_DV_DIR
python3 run.py -tl ./yaml/base_testlist.yaml  --target=rv32imc --iss_timeout 1000 -o $RISCV_DV_OUT_DIR