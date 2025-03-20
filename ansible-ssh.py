#!/usr/bin/env python3
"""
ansible-ssh: Connect to a host using connection variables from an Ansible inventory,
with fallbacks to standard SSH configuration (e.g. ~/.ssh/config) for unspecified settings.
It also supports additional SSH options via ansible_ssh_common_args and ansible_ssh_extra_args,
which can be disabled by setting ENABLE_EXTRA_SSH_OPTIONS to False.

Usage:
    ansible-ssh -i <inventory_file> <host>
    
Requirements:
    - ansible (for ansible-inventory)
    - Python 3
    - sshpass (if using password-based SSH)
    - jq (for bash_completion script)
"""

import argparse
import json
import os
import shlex
import subprocess
import sys
import shutil

# Set this to True to enable parsing of extra SSH options. (experimental)
ENABLE_EXTRA_SSH_OPTIONS = False

def print_bash_completion_script():
    script = r"""#!/bin/bash
# Bash completion script

_ansible_ssh_completion() {
    local cur prev inv_index inv_file hostlist
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    # If completing the -C/--complete flag, suggest only 'bash'
    if [[ "${prev}" == "-C" || "${prev}" == "--complete" ]]; then
        COMPREPLY=( $(compgen -W "bash" -- "$cur") )
        return 0
    fi

    # Locate the inventory file argument by finding "-i" or "--inventory"
    inv_index=-1
    for i in "${!COMP_WORDS[@]}"; do
        if [[ "${COMP_WORDS[i]}" == "-i" || "${COMP_WORDS[i]}" == "--inventory" ]]; then
            inv_index=$((i+1))
            break
        fi
    done

    # If no -i/--inventory flag is present, do nothing.
    if [ $inv_index -eq -1 ]; then
        return 0
    fi

    # If completing the inventory file argument itself, complete file paths.
    if [ $COMP_CWORD -eq $inv_index ]; then
        # Disable automatic space appending.
        compopt -o nospace
        local IFS=$'\n'
        local files=( $(compgen -f -- "$cur") )
        local completions=()
        for file in "${files[@]}"; do
            if [ -d "$file" ]; then
                completions+=( "${file}/" )
            else
                completions+=( "$file " )
            fi
        done
        COMPREPLY=( "${completions[@]}" )
        return 0
    fi

    # Otherwise, assume the inventory file argument has been provided.
    inv_file="${COMP_WORDS[$inv_index]}"

    # Check that the inventory file exists.
    if [[ ! -f "$inv_file" ]]; then
        return 0
    fi

    # Now complete hostnames from the provided inventory.
    hostlist=$(ansible-inventory -i "$inv_file" --list 2>/dev/null | jq -r '._meta.hostvars | keys[]' 2>/dev/null)
    COMPREPLY=( $(compgen -W "$hostlist" -- "$cur") )
}

complete -F _ansible_ssh_completion {basename}
"""
    script = script.replace("{basename}", os.path.basename(sys.argv[0]))
    print(script)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Connect to a host using connection variables from an Ansible inventory.",
        epilog="EXAMPLES:\n"
           "  Connect to a host:\n\t %(prog)s -i inventory myhost\n\n"
           "  Generate and install bash completion script:\n\t %(prog)s -C bash | sudo tee /etc/bash_completion.d/%(prog)s",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("-C", "--complete", choices=["bash"], help="Print bash completion script and exit")
    parser.add_argument("-i", "--inventory", help="Path to the Ansible inventory file")
    parser.add_argument("host", nargs="?", help="Host to connect to")
    args = parser.parse_args()

    # If not in completion mode, require both inventory and host.
    if not args.complete and (not args.inventory or not args.host):
        parser.error("the following arguments are required: -i/--inventory, host")
    return args

def get_host_vars(inventory_file, host):
    try:
        result = subprocess.run(
            ["ansible-inventory", "-i", inventory_file, "--host", host],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Error running ansible-inventory:\n{e.stderr}", file=sys.stderr)
        sys.exit(1)
    
    try:
        host_vars = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON from ansible-inventory: {e}", file=sys.stderr)
        sys.exit(1)

    if not host_vars:
        print(f"No host information found for '{host}' in inventory '{inventory_file}'.", file=sys.stderr)
        sys.exit(1)
    
    return host_vars

def parse_extra_ssh_options(host_vars):
    """
    Parses extra SSH options from the inventory.
    Processes ansible_ssh_common_args and ansible_ssh_extra_args.
    Returns a list of extra SSH options.
    """
    options = []
    common_args = host_vars.get("ansible_ssh_common_args")
    extra_args = host_vars.get("ansible_ssh_extra_args")
    
    if common_args:
        try:
            options.extend(shlex.split(common_args))
        except Exception as e:
            print(f"Error parsing ansible_ssh_common_args: {e}", file=sys.stderr)
            sys.exit(1)
    if extra_args:
        try:
            options.extend(shlex.split(extra_args))
        except Exception as e:
            print(f"Error parsing ansible_ssh_extra_args: {e}", file=sys.stderr)
            sys.exit(1)
    return options

def build_ssh_command(host_vars, host):
    # Extract variables with fallbacks
    host_ip = host_vars.get("ansible_host", host)
    # For user, check ansible_ssh_user then ansible_user.
    user = host_vars.get("ansible_ssh_user") or host_vars.get("ansible_user")
    port = host_vars.get("ansible_port")
    key = host_vars.get("ansible_private_key_file")
    # For password, check ansible_ssh_pass then ansible_password.
    ssh_pass = host_vars.get("ansible_ssh_pass") or host_vars.get("ansible_password")
    
    # Build the base SSH command as a list
    ssh_cmd = ["ssh"]

    if port:
        ssh_cmd.extend(["-p", str(port)])
    if key:
        ssh_cmd.extend(["-i", key])
    
    if ENABLE_EXTRA_SSH_OPTIONS:
        extra_options = parse_extra_ssh_options(host_vars)
        ssh_cmd.extend(extra_options)
    
    # Build the target string
    if user:
        target = f"{user}@{host_ip}"
    else:
        target = host_ip

    ssh_cmd.append(target)

    return ssh_cmd, ssh_pass, target

def main():
    args = parse_arguments()

    # If --complete bash is requested, print the completion script and exit.
    if args.complete:
        if args.complete == "bash":
            print_bash_completion_script()
            sys.exit(0)

    # Check that the inventory file exists.
    if not os.path.exists(args.inventory):
        print(f"Error: Inventory file '{args.inventory}' does not exist.", file=sys.stderr)
        sys.exit(1)

    # Get host variables from ansible-inventory.
    host_vars = get_host_vars(args.inventory, args.host)

    # Build the SSH command and extract SSH password if any.
    ssh_cmd, ssh_pass, target = build_ssh_command(host_vars, args.host)

    # Show the connection target and options (excluding the final target)
    print("Connecting to {} with options: {}".format(target, " ".join(ssh_cmd[1:-1])))

    # If a password is provided, prepend sshpass to the command.
    if ssh_pass:
        if not shutil.which("sshpass"):
            print("Error: sshpass is required for password-based SSH. Please install sshpass.", file=sys.stderr)
            sys.exit(1)
        ssh_cmd = ["sshpass", "-p", ssh_pass] + ssh_cmd

    try:
        subprocess.run(ssh_cmd)
    except Exception as e:
        print(f"Error executing SSH: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
