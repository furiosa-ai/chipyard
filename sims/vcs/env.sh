#!/bin/bash
source /nfs/tools/asic/stork_dv.env

CY_DIR=$(dirname $(readlink -f $0))/../..

export RISCV=$CY_DIR/.conda-env/riscv-tools
export RISCV_GCC=$RISCV/bin/riscv64-unknown-elf-gcc
export RISCV_OBJCOPY=$RISCV/bin/riscv64-unknown-elf-objcopy
export SPIKE_PATH=$RISCV/bin

export RISCV_DV_DIR=$CY_DIR/toolchains/riscv-tools/riscv-dv

PATH=$CY_DIR/software/firemarshal:$PATH

if ! type conda >& /dev/null; then
    echo "::ERROR:: you must have conda in your environment first"
    return 1  # don't want to exit here because this file is sourced
fi

source $(conda info --base)/etc/profile.d/conda.sh
conda activate $CY_DIR/.conda-env
source $CY_DIR/scripts/fix-open-files.sh

PATH=$CY_DIR/software/firemarshal:$PATH
