#!/bin/sh
# Platform-neutral CI entry point. GitHub Actions, Forgejo/Codeberg and any
# other CI system should call this instead of duplicating the commands.
#
#   build-aux/ci/check.sh lint | test | all
set -eu

cd "$(dirname "$0")/../.."

setup() {
    uv venv --system-site-packages
    uv pip install --group dev
}

lint() {
    uv run --no-sync pre-commit run --all-files --show-diff-on-failure
}

tests() {
    xvfb-run -a uv run --no-sync pytest
}

case "${1:-all}" in
    setup) setup ;;
    lint) setup; lint ;;
    test) setup; tests ;;
    all) setup; lint; tests ;;
    *) echo "usage: $0 [setup|lint|test|all]" >&2; exit 2 ;;
esac
