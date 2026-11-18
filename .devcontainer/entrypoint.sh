#!/bin/sh
# Start throwaway Postgres and MinIO for Polar's tests, then run the FixBugs
# command. Data lives on /tmp (tmpfs), so every command starts empty.
# Ports and credentials are Polar's test defaults (server/.env.testing).
PG_BIN=$(ls -d /usr/lib/postgresql/*/bin | head -n 1)
PG_DATA=/tmp/fixbugs-demo-pg
PG_LOG=/tmp/fixbugs-demo-pg.log
MINIO_LOG=/tmp/fixbugs-demo-minio.log

if ! { "$PG_BIN/initdb" -D "$PG_DATA" -U polar --auth=trust --encoding=UTF8 --locale=C.UTF-8 >"$PG_LOG" 2>&1 \
  && "$PG_BIN/pg_ctl" -D "$PG_DATA" -l "$PG_LOG" -w \
    -o "-c listen_addresses=127.0.0.1 -c unix_socket_directories=/tmp -c fsync=off -c max_locks_per_transaction=256" \
    start >/dev/null 2>&1; }; then
  echo "fixbugs-demo: Postgres did not start; see $PG_LOG" >&2
fi

MINIO_ROOT_USER=polar MINIO_ROOT_PASSWORD=polarpolar \
  minio server /tmp/fixbugs-demo-minio --address 127.0.0.1:9000 --console-address 127.0.0.1:9001 \
  >"$MINIO_LOG" 2>&1 &
for _ in $(seq 1 50); do
  curl -fsS http://127.0.0.1:9000/minio/health/live >/dev/null 2>&1 && break
  sleep 0.2
done

exec "$@"
