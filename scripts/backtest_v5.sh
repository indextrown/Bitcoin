#!/usr/bin/env bash

# V5 단타 백테스트 시각화 실행: develop/v5/backtesting/v5_backtest.png를 생성합니다.
# ``$@``: ``--from 2026-07-01 --to 2026-08-02``처럼 make가 전달한 CLI 인자를 넘깁니다.
set -euo pipefail

REPOSITORY_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPOSITORY_ROOT"

if [[ -x .venv/bin/python ]]; then
    PYTHON=.venv/bin/python
else
    PYTHON=python3
fi

exec "$PYTHON" develop/v5/backtesting/backtest_visualizer.py "$@"
