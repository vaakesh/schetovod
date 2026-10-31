#!/usr/bin/env bash
set -Eeuo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
# the dumps hold the whole accounting and the password hashes
umask 077
BACKUPS_TO_KEEP=10
exec 9> .deploy.lock
flock -n 9 || { printf '%s\n' 'Другой деплой уже выполняется' >&2; exit 1; }

compose() {
    docker compose -f compose.yml -f compose.prod.yml "$@"
}

backup_database() {
    local version file

    mkdir -p backups
    # the schema in the dump belongs to the version deployed before this one
    version="$(cat backups/deployed-version 2>/dev/null || printf 'unknown')"
    file="backups/$(date +%Y%m%d-%H%M%S)-$version.dump"

    # a dump cut off halfway must not look like a finished one
    compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' > "$file.tmp"
    compose exec -T postgres pg_restore --list < "$file.tmp" > /dev/null
    mv -- "$file.tmp" "$file"
    printf 'Бэкап базы: %s (%s)\n' "$file" "$(du -h -- "$file" | cut -f1)"

    ls -1t backups/*.dump | tail -n +$((BACKUPS_TO_KEEP + 1)) | xargs -r rm --
}

on_error() {
    local result=$?
    trap - ERR
    compose ps --all || true
    compose logs --tail 30 || true
    exit "$result"
}
trap on_error ERR

compose config --quiet
test -d invoices
docker network inspect xray-egress >/dev/null
if ! git diff --quiet || ! git diff --cached --quiet; then
    printf '%s\n' 'На сервере есть изменения отслеживаемых файлов; деплой остановлен' >&2
    exit 1
fi

# build before stopping the current application
compose build app frontend
compose stop frontend scheduler worker app
compose up -d --wait --wait-timeout 120 postgres redis
# the app is stopped, nothing is written after the dump
backup_database
# only the app entrypoint applies migrations
compose up -d --no-deps --wait --wait-timeout 180 app
compose up -d --no-build --wait --wait-timeout 120 frontend worker scheduler
compose exec -T frontend wget -q -O - http://127.0.0.1/api/health
git rev-parse --short HEAD > backups/deployed-version
printf '\nВерсия: %s\n' "$(git rev-parse HEAD)"
compose ps
