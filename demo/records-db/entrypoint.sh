#!/bin/sh
set -eu
install -o postgres -g postgres -m 600 /keys/server.key /var/lib/postgresql/server.key
install -o postgres -g postgres -m 644 /keys/server.crt /var/lib/postgresql/server.crt
exec /usr/local/bin/docker-entrypoint.sh "$@"
