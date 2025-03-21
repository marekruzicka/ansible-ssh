#!/usr/bin/env python3
"""
ansible-ssh: Connect to a host using connection variables from an Ansible inventory.

Usage:
    ansible-ssh -i <inventory_file> <host> [--print-only]

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

# Set this to True to enable parsing of extra SSH options (experimental)
ENABLE_EXTRA_SSH_OPTIONS = False

def print_bash_completion_script():
    """
    Print a bash completion script for ansible-ssh.

    The script provides tab completion for options, inventory files, and hostnames.
    """
    script = r"""#!/bin/bash
# Bash completion script for {basename}

_ansible_ssh_completion() {
    local cur prev inv_index inv_file hostlist
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    # Available options at the top level
    if [[ $COMP_CWORD -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "-C --complete -h --help -i --inventory" -- "$cur") )
        return 0
    fi

    # Stop completion if -h/--help is used
    if [[ " ${COMP_WORDS[@]} " =~ " -h " || " ${COMP_WORDS[@]} " =~ " --help " ]]; then
        return 0
    fi

    # Stop completion if --print-only was used
    if [[ " ${COMP_WORDS[@]} " =~ " --print-only " ]]; then
        return 0
    fi

    # If completing the -C/--complete flag, suggest only 'bash' and stop further completion
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

    # If completing the inventory file argument, complete file paths
    if [ $COMP_CWORD -eq $inv_index ]; then
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

    # Complete hostnames from the provided inventory if it exists
    if [ $inv_index -ne -1 ] && [[ -f "${COMP_WORDS[$inv_index]}" ]]; then
        inv_file="${COMP_WORDS[$inv_index]}"
    else
        return 0
    fi

    # If host has been selected from the inventory, suggest additional argument completions.
    if [ $COMP_CWORD -ge $((inv_index+2)) ]; then
        COMPREPLY=( $(compgen -W "--print-only" -- "$cur") )
        return 0
    fi

    hostlist=$(ansible-inventory -i "$inv_file" --list 2>/dev/null | jq -r '._meta.hostvars | keys[]' 2>/dev/null)
    COMPREPLY=( $(compgen -W "$hostlist" -- "$cur") )
}

complete -F _ansible_ssh_completion {basename}
"""
    script = script.replace("{basename}", os.path.basename(sys.argv[0]))
    print(script)

def parse_arguments():
    """
    Parse command-line arguments for ansible-ssh.

    Returns:
        argparse.Namespace: Parsed arguments with inventory file, host, and optional flags.
        The optional flags include:
            - --complete: Print bash completion script.
            - --print-only: Print SSH command instead of executing it.
    
    Raises:
        SystemExit: If required arguments are missing.
    """
    parser = argparse.ArgumentParser(
        description="Connect to a host using connection variables from an Ansible inventory.",
        epilog="EXAMPLES:\n"
               "  Connect to a host:\n\t %(prog)s -i inventory myhost\n\n"
               "  Generate and install bash completion script:\n\t %(prog)s -C bash | sudo tee /etc/bash_completion.d/%(prog)s",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("-C", "--complete", choices=["bash"], help="Print bash completion script and exit")
    parser.add_argument("-i", "--inventory", help="Path to the Ansible inventory file")
    parser.add_argument("--print-only", action="store_true", help="Print SSH command instead of executing it")
    parser.add_argument("host", nargs="?", help="Host to connect to")
    args = parser.parse_args()

    if not args.complete and (not args.inventory or not args.host):
        parser.error("the following arguments are required: -i/--inventory, host")
    return args

def get_host_vars(inventory_file, host):
    """
    Retrieve host variables from the inventory using ansible-inventory.

    Args:
        inventory_file (str): Path to the Ansible inventory file.
        host (str): Host name.

    Returns:
        dict: Host variables.

    Raises:
        SystemExit: If the inventory file is missing, host is not found, or parsing fails.
    """
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
    Parse extra SSH options from host variables.

    Args:
        host_vars (dict): Host variables from the inventory.

    Returns:
        list: Extra SSH options.
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
    """
    Build the SSH command and target from host variables.

    Args:
        host_vars (dict): Host variables from the inventory.
        host (str): Host name.

    Returns:
        tuple: (ssh_cmd (list), ssh_pass (str or None), target (str))
    """
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
    """
    Main entry point for ansible-ssh.

    Parses arguments, retrieves host variables, builds the SSH command,
    and executes the SSH connection (using sshpass if a password is provided).
    If the --print-only flag is provided, prints the SSH command instead of executing it.
    """
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

    # If --print-only flag is provided, just print the SSH command instead of executing it.
    if args.debug:
        print("DEBUG: SSH command to be executed:")
        print(" ".join(shlex.quote(arg) for arg in ssh_cmd))
        sys.exit(0)

    try:
        subprocess.run(ssh_cmd)
    except Exception as e:
        print(f"Error executing SSH: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
