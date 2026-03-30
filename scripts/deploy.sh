#!/usr/bin/env bash
set -euo pipefail

# NAS Docker service deploy script
# Placed on NAS by Ansible bootstrap. Called by GitHub Actions CI.
#
# Usage:
#   deploy.sh <service> [<service> ...]   Deploy specific services
#   deploy.sh all                          Deploy all services
#   deploy.sh                              Deploy all services (default)

DOCKER_DIR="${HOME}/docker"
BASE_COMPOSE="${DOCKER_DIR}/compose.base.yml"

# Discover all services: subdirectories of ~/docker/ containing a compose.yml
discover_services() {
    local services=()
    for dir in "${DOCKER_DIR}"/*/; do
        if [[ -f "${dir}compose.yml" ]]; then
            services+=("$(basename "$dir")")
        fi
    done
    echo "${services[@]}"
}

# Deploy a single service
deploy_service() {
    local service="$1"
    local service_compose="${DOCKER_DIR}/${service}/compose.yml"

    if [[ ! -f "$service_compose" ]]; then
        echo "ERROR: No compose.yml found for service '${service}' at ${service_compose}" >&2
        return 1
    fi

    echo "Deploying ${service}..."
    docker compose \
        --project-directory "${DOCKER_DIR}" \
        -f "${BASE_COMPOSE}" \
        -f "${service_compose}" \
        up -d "${service}"
    echo "Done: ${service}"
}

# Main
main() {
    if [[ ! -f "$BASE_COMPOSE" ]]; then
        echo "ERROR: Base compose file not found at ${BASE_COMPOSE}" >&2
        exit 1
    fi

    local services=("$@")

    # Default to "all" if no arguments
    if [[ ${#services[@]} -eq 0 ]] || [[ "${services[0]}" == "all" ]]; then
        read -ra services <<< "$(discover_services)"
        echo "Deploying all services: ${services[*]}"
    fi

    local failed=0
    for service in "${services[@]}"; do
        if ! deploy_service "$service"; then
            echo "FAILED: ${service}" >&2
            failed=1
        fi
    done

    if [[ $failed -ne 0 ]]; then
        echo "Some services failed to deploy" >&2
        exit 1
    fi

    echo "All deployments complete"
}

main "$@"
