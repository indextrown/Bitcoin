#!/usr/bin/env bash

# V4 백테스트 시각화 실행: develop/v4/backtesting/v4_backtest.png를 생성합니다.
# ``$@``: ``--from 2026-01-01 --to 2026-08-03``처럼 make가 전달한 CLI 인자를 넘깁니다.
set -euo pipefail

REPOSITORY_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPOSITORY_ROOT"

if [[ -x .venv/bin/python ]]; then
    PYTHON=.venv/bin/python
else
    PYTHON=python3
fi

exec "$PYTHON" develop/v4/backtesting/backtest_visualizer.py "$@"
