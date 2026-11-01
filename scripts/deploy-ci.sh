#!/usr/bin/env bash
# the forced command of the GitHub Actions key in authorized_keys
set -Eeuo pipefail

# errexit does not work in a function called from a condition, so every step is checked
deploy() {
    local commit="$1"

    # a server left on another commit after a rollback is put back by hand
    if [[ "$(git branch --show-current)" != main ]]; then
        printf '%s\n' 'Деплой возможен только из ветки main' >&2
        return 1
    fi

    git fetch --quiet origin main || return 1

    if [[ "$(git rev-parse origin/main)" != "$commit" ]]; then
        printf 'Пропущен устаревший коммит %s\n' "$commit" >&3
        return 0
    fi

    git merge --quiet --ff-only "$commit" || return 1
    bash scripts/deploy-prod.sh || return 1
    printf 'Развёрнут коммит %s\n' "$commit" >&3
}

main() {
    local commit="${SSH_ORIGINAL_COMMAND:-}"

    # the value comes from the network, only a full commit hash goes through
    if [[ ! "$commit" =~ ^[0-9a-f]{40}$ ]]; then
        printf '%s\n' 'Ожидается полный хеш коммита' >&2
        exit 2
    fi

    cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
    umask 077
    mkdir -p backups

    # the Actions log of a public repository is open to everyone, the container logs stay here
    exec 3>&1
    if ! deploy "$commit" > backups/deploy.log 2>&1; then
        printf '%s\n' 'Деплой не удался, лог на сервере: backups/deploy.log' >&2
        exit 1
    fi
}

# git can replace this file while it runs, bash has to read all of it first
main
exit
