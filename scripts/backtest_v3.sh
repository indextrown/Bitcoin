#!/usr/bin/env bash

# V3 백테스트 시각화 실행: develop/v3/backtesting/v3_backtest.png를 생성합니다.
# ``$@``: ``make backtest`` 뒤에 전달한 티커·수수료·크론 가정 등의 CLI 인자를 그대로 전달합니다.
set -euo pipefail

REPOSITORY_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPOSITORY_ROOT"

if [[ -x .venv/bin/python ]]; then
    PYTHON=.venv/bin/python
else
    PYTHON=python3
fi

exec "$PYTHON" develop/v3/backtesting/backtest_visualizer.py "$@"
