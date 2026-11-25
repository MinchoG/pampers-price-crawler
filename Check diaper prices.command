#!/bin/bash
cd "$(dirname "$0")" || exit 1
run_check() {
    if ! command -v python3 >/dev/null || ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
        echo "Install Python 3.11 or newer from https://www.python.org/downloads/macos/ and open this file again."
        return 1
    fi
    if [ ! -x .venv/bin/price-check ]; then
        python3 -m venv .venv && .venv/bin/python -m pip install -e . || return 1
    fi
    if [ ! -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]; then
        .venv/bin/playwright install chromium || return 1
    fi
    .venv/bin/python -m pampers_prices.quick_check
}
run_check
read -r -p "Press Enter to close."
