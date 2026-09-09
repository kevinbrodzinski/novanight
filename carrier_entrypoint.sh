#!/bin/sh
set -eu
"$@" &
exec python3 /carrier_bridge.py
