#!/usr/bin/env bash
set -Eeuo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
exec 9> .deploy.lock
flock -n 9 || { printf '%s\n' 'Другой деплой уже выполняется' >&2; exit 1; }

compose() {
    docker compose -f docker-compose-prod.yml "$@"
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
test -f .openai-token
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
# only the app entrypoint applies migrations
compose up -d --no-deps --wait --wait-timeout 180 app
compose up -d --no-build --wait --wait-timeout 120 frontend worker scheduler
compose exec -T frontend wget -q -O - http://127.0.0.1/api/health
printf '\nВерсия: %s\n' "$(git rev-parse HEAD)"
compose ps
