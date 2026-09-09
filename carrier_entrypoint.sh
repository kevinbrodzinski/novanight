#!/bin/sh
set -eu
/entrypoint.sh &
exec python3 /carrier_bridge.py
