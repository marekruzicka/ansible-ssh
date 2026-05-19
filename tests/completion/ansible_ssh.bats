#!/usr/bin/env bats

REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)"
INV_FILE="$REPO_ROOT/tests/fixtures/inventory"
INV_PROXY="$REPO_ROOT/tests/fixtures/hosts_proxy.yaml"

setup() {
    # Source the generated completion script so _ansible_ssh_completion is defined
    # shellcheck source=/dev/null
    source <(python3 "$REPO_ROOT/ansible-ssh.py" -C bash)
    COMPREPLY=()
}

# Helper: set COMP_WORDS to the given args; last arg is the word being completed
_complete() {
    COMP_WORDS=("$@")
    COMP_CWORD=$(( ${#COMP_WORDS[@]} - 1 ))
    COMPREPLY=()
    _ansible_ssh_completion
}

# ── option completion ─────────────────────────────────────────────────────────

@test "first arg: suggests -i, -C, --inventory when starting with -" {
    _complete "ansible-ssh" "-"
    [[ " ${COMPREPLY[*]} " == *" -i "* ]]
    [[ " ${COMPREPLY[*]} " == *" -C "* ]]
    [[ " ${COMPREPLY[*]} " == *" --inventory "* ]]
}

@test "-C: only suggests bash" {
    _complete "ansible-ssh" "-C" ""
    [[ "${#COMPREPLY[@]}" -eq 1 ]]
    [[ "${COMPREPLY[0]}" == "bash" ]]
}

@test "--complete: only suggests bash" {
    _complete "ansible-ssh" "--complete" ""
    [[ "${#COMPREPLY[@]}" -eq 1 ]]
    [[ "${COMPREPLY[0]}" == "bash" ]]
}

@test "-h: stops further completion" {
    _complete "ansible-ssh" "-h" ""
    [[ "${#COMPREPLY[@]}" -eq 0 ]]
}

@test "--help: stops further completion" {
    _complete "ansible-ssh" "--help" ""
    [[ "${#COMPREPLY[@]}" -eq 0 ]]
}

# ── post-host option deduplication ───────────────────────────────────────────

@test "after host: suggests both --print-only and -v" {
    _complete "ansible-ssh" "-i" "$INV_FILE" "server1" ""
    [[ " ${COMPREPLY[*]} " == *" --print-only "* ]]
    [[ " ${COMPREPLY[*]} " == *" -v "* ]]
}

@test "after host: --print-only not suggested again if already present" {
    _complete "ansible-ssh" "-i" "$INV_FILE" "server1" "--print-only" ""
    [[ " ${COMPREPLY[*]} " != *" --print-only "* ]]
}

@test "after host: -v not suggested again if already present" {
    _complete "ansible-ssh" "-i" "$INV_FILE" "server1" "-v" ""
    [[ " ${COMPREPLY[*]} " != *" -v "* ]]
}

@test "after host: no suggestions when both --print-only and -v are already present" {
    _complete "ansible-ssh" "-i" "$INV_FILE" "server1" "--print-only" "-v" ""
    [[ "${#COMPREPLY[@]}" -eq 0 ]]
}

# ── host completion (requires ansible-inventory + jq) ────────────────────────

@test "lists hosts from -i inventory" {
    command -v ansible-inventory >/dev/null 2>&1 || skip "ansible-inventory not available"
    command -v jq >/dev/null 2>&1 || skip "jq not available"
    _complete "ansible-ssh" "-i" "$INV_FILE" ""
    [[ " ${COMPREPLY[*]} " == *" server1 "* ]]
    [[ " ${COMPREPLY[*]} " == *" server5 "* ]]
}

@test "partial hostname filters completions" {
    command -v ansible-inventory >/dev/null 2>&1 || skip "ansible-inventory not available"
    command -v jq >/dev/null 2>&1 || skip "jq not available"
    _complete "ansible-ssh" "-i" "$INV_FILE" "server2"
    # server2 should match; server1 should not
    [[ " ${COMPREPLY[*]} " == *" server2 "* ]]
    [[ " ${COMPREPLY[*]} " != *" server1 "* ]]
}

@test "lists hosts from proxy inventory" {
    command -v ansible-inventory >/dev/null 2>&1 || skip "ansible-inventory not available"
    command -v jq >/dev/null 2>&1 || skip "jq not available"
    _complete "ansible-ssh" "-i" "$INV_PROXY" ""
    [[ " ${COMPREPLY[*]} " == *" gold_vm "* ]]
}
