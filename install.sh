#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd -- "$PROJECT_DIR"
umask 077

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

copy_example ".env.example" ".env"
copy_example ".openai-token.example" ".openai-token"

printf '\nНастройки готовы. Запустите контейнеры: make up\n'
