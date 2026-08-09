#!/bin/sh

# shellcheck disable=SC1091
. /usr/local/lib/hermes-ha/environment.sh

if [ -d /config ]; then
  cd /config || return 1
fi
