#!/usr/bin/env bash
exec bash "${VIBE:?VIBE nicht gesetzt}/_toolchain/verify/verify.sh" "$(cd "$(dirname "$0")/.." && pwd)" "${1:-quick}"
