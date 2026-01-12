# RISC-V DV Test Automation Scripts

이 디렉토리는 Chipyard Rocket Core의 RISC-V DV (Design Verification) 테스트를 자동화하는 Python 스크립트들을 포함하고 있습니다.

## 📋 Overview

RISC-V DV 테스트는 다음 단계로 진행됩니다:

```
1. generate_test_vector.py  → 테스트 벡터 생성 (어셈블리 + Spike golden reference)
2. run_parallel_tests.py    → RTL 시뮬레이션 (병렬 실행)
3. compare.py               → 개별 테스트 비교 (RTL vs Spike)
4. compare_all.py           → 전체 테스트 비교 및 리포트
```

---

## 🚀 Quick Start

### 전체 플로우 실행
```bash
# 1. 테스트 벡터 생성
./generate_test_vector.py --out-dir my_test

# 2. RTL 시뮬레이션 (병렬 20개)
./run_parallel_tests.py --out-dir my_test

# 완료! run_parallel_tests.py가 자동으로 compare_all.py 호출
```

---

## 📝 Script Details

### 1. generate_test_vector.py

**기능**: RISC-V DV를 사용하여 랜덤 어셈블리 테스트와 Spike ISS golden reference를 생성합니다.

**사용법**:
```bash
# 기본 사용 (out 디렉토리에 생성)
./generate_test_vector.py

# 출력 디렉토리 지정
./generate_test_vector.py --out-dir out_2025-12-29

# ISA 타겟 변경
./generate_test_vector.py --target rv64imc

# 특정 testlist 사용
./generate_test_vector.py --testlist target/rv32imc/testlist.yaml

# ISS 타임아웃 설정
./generate_test_vector.py --iss-timeout 2000
```

**주요 옵션**:
- `--out-dir, -o`: 출력 디렉토리 (기본값: `out`)
- `--target`: ISA 타겟 (기본값: `rv32imc`)
- `--iss-timeout`: ISS 타임아웃 초 (기본값: 1000)
- `--testlist, -tl`: YAML testlist 파일

**출력**:
```
riscv-dv/
└── <out-dir>/
    ├── asm_test/           # 어셈블리 테스트 (.o 파일들)
    └── spike_sim/          # Spike golden reference (.log 파일들)
```

---

### 2. run_parallel_tests.py

**기능**: 생성된 테스트들을 RTL 시뮬레이터에서 병렬로 실행하고 결과를 수집합니다.

**사용법**:
```bash
# 기본 사용 (20개 병렬 실행)
./run_parallel_tests.py

# 출력 디렉토리 지정
./run_parallel_tests.py --out-dir out_2025-12-29

# 병렬 작업 수 조정
./run_parallel_tests.py --parallel 30

# 특정 패턴만 실행
./run_parallel_tests.py --pattern "riscv_arithmetic*.o"

# 특정 테스트 제외
./run_parallel_tests.py --exclude "^riscv_rand_instr_test"

# 디버그 모드 (파형 생성)
./run_parallel_tests.py --debug

# 타임아웃 설정
./run_parallel_tests.py --timeout-cycles 5000000 --wall-timeout 1800

# 비교 단계 스킵
./run_parallel_tests.py --no-compare
```

**주요 옵션**:
- `--out-dir`: RISCV-DV 출력 디렉토리 (기본값: `out`)
- `--config, -c`: Rocket config (기본값: `RV32RocketConfig`)
- `--parallel, -j`: 병렬 작업 수 (기본값: 20)
- `--timeout-cycles, -t`: 최대 시뮬레이션 사이클 (기본값: 10000000)
- `--wall-timeout, -w`: Wall-clock 타임아웃 초 (기본값: 3600)
- `--pattern, -p`: 테스트 파일 glob 패턴 (기본값: `*.o`)
- `--exclude, -e`: 제외할 테스트 정규식 패턴
- `--debug, -d`: 파형 생성 활성화
- `--log-dir`: 로그 파일 디렉토리 (기본값: `logs`)
- `--no-compare`: 비교 단계 스킵

**Process Pool 동작**:
```
최대 20개 프로세스가 동시 실행
[Test 1] [Test 2] ... [Test 20]
   ↓ 완료
[Test 21] 시작
   ↓ 계속 반복
```

**출력**:
```
logs/
├── test_name_1.log         # 각 테스트 시뮬레이션 로그
├── test_name_2.log
└── ...

output/chipyard.harness.TestHarness.RV32RocketConfig/
├── test_name_1.out         # RTL 실행 trace
├── test_name_2.out
└── ...
```

---

### 3. compare.py

**기능**: 단일 테스트의 RTL trace와 Spike golden reference를 비교합니다.

**사용법**:
```bash
# RTL과 Spike 로그 비교
./compare.py --rtl output/.../test.out --spike riscv-dv/.../test.log

# 짧은 옵션
./compare.py -r rocket.out -s spike.log
```

**동작 과정**:
1. RTL 로그를 CSV로 변환 (`rocket_log_to_trace_csv.py`)
2. Spike 로그를 CSV로 변환 (`spike_log_to_trace_csv.py`)
3. 두 CSV 파일 비교 (`instr_trace_compare.py`)

**주요 옵션**:
- `--rtl, -r`: RTL dump 파일 (필수)
- `--spike, -s`: Spike dump 파일 (필수)

---

### 4. compare_all.py

**기능**: 모든 테스트의 RTL vs Spike 비교를 자동으로 수행합니다.

**사용법**:
```bash
./compare_all.py <asm_dir> <log_dir>

# 예시
./compare_all.py \
  ../../toolchains/riscv-tools/riscv-dv/out/asm_test \
  output/chipyard.harness.TestHarness.RV32RocketConfig
```

**출력 예시**:
```
Found 50 tests to compare
============================================================
[PASS] test_1
[PASS] test_2
[FAIL] test_3
...
============================================================
Summary
============================================================
Total:  50
Passed: 48
Failed: 2
============================================================
```

---
