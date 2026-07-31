#!/usr/bin/env bash

set -euo pipefail

REPOSITORY_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPOSITORY_ROOT"

git add .

if git diff --cached --quiet; then
    echo "커밋할 변경사항이 없습니다."
    exit 0
fi

git commit -m "update"
git push
