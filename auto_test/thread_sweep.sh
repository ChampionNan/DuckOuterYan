#!/usr/bin/env bash
# Shared validation for sequential multi-thread experiment sweeps.
oy_parse_thread_counts() {
    local specification="${1//,/ }" count previous
    specification="${specification//$'\n'/ }"
    OY_THREAD_VALUES=()
    read -r -a OY_THREAD_VALUES <<< "$specification"
    if [ "${#OY_THREAD_VALUES[@]}" -eq 0 ]; then
        echo "--threads/OY_THREAD_COUNTS requires at least one thread count" >&2
        return 2
    fi
    local -a seen=()
    for count in "${OY_THREAD_VALUES[@]}"; do
        if ! [[ "$count" =~ ^[1-9][0-9]*$ ]] || [ "$count" = 1 ]; then
            echo "Thread counts must be integers greater than 1 (got: $count)" >&2
            return 2
        fi
        for previous in "${seen[@]:-}"; do
            if [ "$count" = "$previous" ]; then
                echo "Duplicate thread count: $count" >&2
                return 2
            fi
        done
        seen+=("$count")
    done
}
