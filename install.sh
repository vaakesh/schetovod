#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd -- "$PROJECT_DIR"
umask 077

production=0
case "${1:-}" in
    --prod) production=1 ;;
    "") ;;
    *) printf '%s\n' 'Использование: bash install.sh [--prod]' >&2; exit 1 ;;
esac

copy_example() {
    local source_file="$1"
    local target_file="$2"

    if [[ -e "$target_file" || -L "$target_file" ]]; then
        printf '%s уже существует, сохранён\n' "$target_file"
        return
    fi

    cp -- "$source_file" "$target_file"
    printf 'Создан %s\n' "$target_file"
}

add_missing() {
    local name="$1"
    local value="$2"

    if grep -q "^${name}=" .env; then
        return
    fi

    # an old .env may end without a line break
    if [[ -n "$(tail -c 1 .env)" ]]; then
        printf '\n' >> .env
    fi
    printf '%s=%s\n' "$name" "$value" >> .env
    printf 'В .env добавлен %s\n' "$name"
}

if [[ "$production" == 1 && ! -e .env && ! -L .env ]]; then
    # generate production secrets only for a new installation
    while IFS= read -r line || [[ -n "$line" ]]; do
        case "$line" in
            POSTGRES_PASSWORD=*) line="POSTGRES_PASSWORD=$(openssl rand -hex 32)" ;;
            INCLUDE_API_OPENAI=*) line="INCLUDE_API_OPENAI=1" ;;
            OPENAI_PROXY_URL=*) line="OPENAI_PROXY_URL=http://xray:3128" ;;
        esac
        printf '%s\n' "$line"
    done < .env.example > .env
else
    copy_example ".env.example" ".env"
fi
copy_example ".openai-token.example" ".openai-token"
add_missing "JWT_SECRET" "$(openssl rand -hex 32)"
add_missing "CADDY_PORT" "11200"
add_missing "PROD_PORT" "11300"
if [[ "$production" == 1 ]]; then
    add_missing "OPENAI_PROXY_URL" "http://xray:3128"
    mkdir -p invoices
    printf '\nProduction-настройки готовы. После переноса данных: make prod-deploy\n'
    exit 0
fi

printf '\nНастройки готовы. Запустите контейнеры: make up\n'
