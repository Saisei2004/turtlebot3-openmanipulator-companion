#!/bin/bash
# 互換のための別名。run_ros.sh と同じ
exec bash "$(dirname "${BASH_SOURCE[0]}")/run_ros.sh" "$@"
