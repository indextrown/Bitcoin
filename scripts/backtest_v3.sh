#!/usr/bin/env bash

# V3 백테스트 시각화 실행: develop/v3/backtesting/v3_backtest.png를 생성합니다.
# ``$@``: ``--from 2026-01-01 --to 2026-06-30``처럼 직접 전달한 CLI 인자를 시각화 도구에 넘깁니다.
set -euo pipefail

REPOSITORY_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPOSITORY_ROOT"

if [[ -x .venv/bin/python ]]; then
    PYTHON=.venv/bin/python
else
    PYTHON=python3
fi

exec "$PYTHON" develop/v3/backtesting/backtest_visualizer.py "$@"
