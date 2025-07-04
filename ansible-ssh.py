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
import configparser

ANSIBLE_CONFIG_LOCATIONS = [
    lambda: os.environ.get("ANSIBLE_CONFIG"),
    lambda: os.path.join(os.getcwd(), "ansible.cfg"),
    lambda: os.path.expanduser("~/.ansible.cfg"),
    lambda: "/etc/ansible/ansible.cfg",
]

def print_bash_completion_script():
    """
    Print a bash completion script for ansible-ssh.

    The script provides tab completion for options, inventory files, and hostnames.
    """
    script = r"""#!/bin/bash
# Bash completion script for {basename}

_ansible_ssh_completion() {
    local cur prev inv_index inv_file hostlist debug_count options
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

    # If completing the inventory file argument, check for ansible.cfg in standard locations
    if [ $COMP_CWORD -eq $inv_index ]; then
        # Bash function to find ansible.cfg and extract inventory
        _find_ansible_cfg_inventory() {
            local cfg
            local inv
            # 1. ANSIBLE_CONFIG env
            if [ -n "$ANSIBLE_CONFIG" ] && [ -f "$ANSIBLE_CONFIG" ]; then
                cfg="$ANSIBLE_CONFIG"
            elif [ -f "./ansible.cfg" ]; then
                cfg="./ansible.cfg"
            elif [ -f "$HOME/.ansible.cfg" ]; then
                cfg="$HOME/.ansible.cfg"
            elif [ -f "/etc/ansible/ansible.cfg" ]; then
                cfg="/etc/ansible/ansible.cfg"
            fi
            if [ -n "$cfg" ]; then
                inv=$(awk -F '=' '/^[[:space:]]*inventory[[:space:]]*=/ {gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); print $2; exit}' "$cfg")
                if [ -n "$inv" ]; then
                    echo "$inv"
                    return 0
                fi
            fi
            return 1
        }
        
        local inv_path=$(_find_ansible_cfg_inventory)
            
        # If we found an inventory in ansible.cfg and no input yet, suggest only that
        if [ -n "$inv_path" ] && [ -z "$cur" ]; then
            COMPREPLY=( "$inv_path" )
            return 0
        fi
        
        # If there's partial input, do normal file completion but prioritize config inventory
        local completions=()
        
        # Add config inventory first if it matches the current input
        if [ -n "$inv_path" ] && [[ "$inv_path" == "$cur"* ]]; then
            completions+=( "$inv_path" )
        fi
        
        # Add file completion for other inventory files, but avoid duplicates
        compopt -o nospace
        local IFS=$'\n'
        local files=( $(compgen -f -- "$cur") )
        for file in "${files[@]}"; do
            # Skip if this file is already in completions (avoid duplicates)
            local skip=false
            for existing in "${completions[@]}"; do
                # Compare canonical paths to avoid ./file vs file duplicates
                local canonical_file canonical_existing
                canonical_file=$(readlink -f "$file" 2>/dev/null || echo "$file")
                canonical_existing=$(readlink -f "$existing" 2>/dev/null || echo "$existing")
                if [ "$canonical_file" = "$canonical_existing" ]; then
                    skip=true
                    break
                fi
            done
            
            if [ "$skip" = false ]; then
                if [ -d "$file" ]; then
                    completions+=( "${file}/" )
                else
                    completions+=( "$file " )
                fi
            fi
        done
        
        COMPREPLY=( "${completions[@]}" )
        return 0
    fi

    # Complete hostnames from the provided inventory if it exists
    if [ $inv_index -ne -1 ] && [[ -f "${COMP_WORDS[$inv_index]}" ]]; then
        inv_file="${COMP_WORDS[$inv_index]}"
    else
        # If no explicit inventory provided, try to find one from ansible.cfg
        _find_ansible_cfg_inventory() {
            local cfg
            local inv
            if [ -n "$ANSIBLE_CONFIG" ] && [ -f "$ANSIBLE_CONFIG" ]; then
                cfg="$ANSIBLE_CONFIG"
            elif [ -f "./ansible.cfg" ]; then
                cfg="./ansible.cfg"
            elif [ -f "$HOME/.ansible.cfg" ]; then
                cfg="$HOME/.ansible.cfg"
            elif [ -f "/etc/ansible/ansible.cfg" ]; then
                cfg="/etc/ansible/ansible.cfg"
            fi
            if [ -n "$cfg" ]; then
                inv=$(awk -F '=' '/^[[:space:]]*inventory[[:space:]]*=/ {gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); print $2; exit}' "$cfg")
                if [ -n "$inv" ] && [ -f "$inv" ]; then
                    echo "$inv"
                    return 0
                fi
            fi
            return 1
        }
        
        inv_file=$(_find_ansible_cfg_inventory)
        if [ -z "$inv_file" ]; then
            return 0
        fi
    fi

    # If host has been selected from the inventory, suggest additional argument completions.
    if [ $COMP_CWORD -ge $((inv_index+2)) ] || ([ $inv_index -eq -1 ] && [ $COMP_CWORD -ge 2 ]); then
        # Count the number of --debug and --print-only occurrences
        # Allow 3 --debug occurrences and 1 --print-only
        debug_count=0
        print_only_count=0
        for word in "${COMP_WORDS[@]}"; do
            if [ "$word" == "--debug" ]; then
                debug_count=$((debug_count+1))
            fi
            if [ "$word" == "--print-only" ]; then
                print_only_count=$((print_only_count+1))
            fi
        done
        options=""
        if [ $print_only_count -eq 0 ]; then
            options="--print-only"
        fi
        if [ $debug_count -lt 3 ]; then
            if [ -z "$options" ]; then
                options="--debug"
            else
                options="$options --debug"
            fi
        fi
        COMPREPLY=( $(compgen -W "$options" -- "$cur") )
        return 0
    fi

    # Complete hostnames from the inventory
    if [ -n "$inv_file" ] && [ -f "$inv_file" ]; then
        # Try to get hostnames from both ._meta.hostvars (YAML format) and from all groups (INI format)
        hostlist=$(ansible-inventory -i "$inv_file" --list 2>/dev/null | jq -r '
            (._meta.hostvars | keys[]) // empty,
            (.[] | select(type == "object" and has("hosts")) | .hosts[]?) // empty
        ' 2>/dev/null | sort -u)
        COMPREPLY=( $(compgen -W "$hostlist" -- "$cur") )
    fi
}

complete -F _ansible_ssh_completion {basename}
"""
    script = script.replace("{basename}", os.path.basename(sys.argv[0]))
    print(script)


def find_ansible_cfg():
    """
    Find ansible.cfg in the standard locations.
    Returns the path if found, else None.
    """
    for loc in ANSIBLE_CONFIG_LOCATIONS:
        path = loc()
        if path and os.path.isfile(path):
            return path
    return None

def get_default_inventory_from_cfg(cfg_path):
    """
    Parse ansible.cfg and return the default inventory file if set.
    """
    parser = configparser.ConfigParser()
    parser.read(cfg_path)
    if parser.has_section("defaults") and parser.has_option("defaults", "inventory"):
        return parser.get("defaults", "inventory")
    return None

def parse_arguments():
    """
    Parse command-line arguments for ansible-ssh.

    Returns:
        argparse.Namespace: Parsed arguments with inventory file, host, and optional flags.
        The optional flags include:
            - --complete: Print bash completion script.
            - --print-only: Print SSH command instead of executing it.
            - --debug: Increase verbosity (can be used up to 3 times).
    
    Raises:
        SystemExit: If required arguments are missing.
    """
    parser = argparse.ArgumentParser(
        usage="%(prog)s [-h] [-C {bash}] [-i INVENTORY] [host] [--print-only] [--debug]",
        description="Connect to a host using connection variables from an Ansible inventory.",
        epilog="EXAMPLES:\n"
               "  Connect to a host:\n\t %(prog)s -i inventory myhost\n\n"
               "  Connect to a host with ssh verbosity:\n\t %(prog)s -i inventory myhost --debug --debug\n\n"
               "  Print SSH command:\n\t %(prog)s -i inventory myhost --print-only\n\n"
               "  Generate and install bash completion script:\n\t %(prog)s -C bash | sudo tee /etc/bash_completion.d/%(prog)s",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("-C", "--complete", choices=["bash"], help="Print bash completion script and exit")
    parser.add_argument("-i", "--inventory", help="Path to the Ansible inventory file")
    parser.add_argument("--print-only", action="store_true", help="Print SSH command instead of executing it")
    parser.add_argument("--debug", action="count", default=0, help="Increase verbosity (can be used up to 3 times)")
    parser.add_argument("host", nargs="?", help="Host to connect to")
    args = parser.parse_args()

    # If inventory is not provided, try to get it from ansible.cfg
    if not args.inventory and not args.complete:
        cfg_path = find_ansible_cfg()
        if cfg_path:
            inv = get_default_inventory_from_cfg(cfg_path)
            if inv:
                args.inventory = inv

    if not args.complete and (not args.inventory or not args.host):
        parser.error("the following arguments are required: -i/--inventory (or ansible.cfg must exist in one of the standard locations), host")
    return args

def get_host_vars(inventory_file, host):
    """
    Retrieve host variables from the inventory using ansible-inventory.

    Args:
        inventory_file (str): Path to the Ansible inventory file.
        host (str): Host name.

    Returns:
        dict: Host variables. Returns empty dict if host exists but has no variables.

    Raises:
        SystemExit: If ansible-inventory command fails, host is not found, or produces invalid JSON.
    """
    # First check if the host exists in the inventory by listing all hosts
    try:
        list_result = subprocess.run(
            ["ansible-inventory", "-i", inventory_file, "--list"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Error running ansible-inventory --list:\n{e.stderr}", file=sys.stderr)
        sys.exit(1)
    
    try:
        inventory_data = json.loads(list_result.stdout)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON from ansible-inventory --list: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Check if host exists in the inventory (either in _meta.hostvars or in any group's hosts)
    host_exists = False
    if "_meta" in inventory_data and "hostvars" in inventory_data["_meta"] and host in inventory_data["_meta"]["hostvars"]:
        host_exists = True
    else:
        # Check in all groups for hosts arrays
        for key, value in inventory_data.items():
            if isinstance(value, dict) and "hosts" in value:
                if isinstance(value["hosts"], list) and host in value["hosts"]:
                    host_exists = True
                    break
                elif isinstance(value["hosts"], dict) and host in value["hosts"]:
                    host_exists = True
                    break
    
    if not host_exists:
        print(f"Error: Host '{host}' not found in inventory '{inventory_file}'.", file=sys.stderr)
        sys.exit(1)
    
    # Host exists, now get its variables
    try:
        result = subprocess.run(
            ["ansible-inventory", "-i", inventory_file, "--host", host],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Error running ansible-inventory --host:\n{e.stderr}", file=sys.stderr)
        sys.exit(1)
    
    try:
        host_vars = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON from ansible-inventory --host: {e}", file=sys.stderr)
        sys.exit(1)

    # Return the host variables (may be empty dict if no variables defined)
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
    # For host, check ansible_ssh_host then ansible_host, then fall back to the original host name
    host_ip = host_vars.get("ansible_ssh_host") or host_vars.get("ansible_host") or host
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
    
    # Parse and add extra SSH options (ProxyJump, etc.)
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

    # Insert the verbosity flags after "ssh"
    if args.debug > 0:
        debug_flags = ["-v"] * min(args.debug, 3)
        ssh_cmd[1:1] = debug_flags
        print("Connecting to {} with options: {}".format(target, " ".join(ssh_cmd[1:-1])))

    # If a password is provided, prepend sshpass to the command.
    if ssh_pass:
        if not shutil.which("sshpass"):
            print("Error: sshpass is required for password-based SSH. Please install sshpass.", file=sys.stderr)
            sys.exit(1)
        ssh_cmd = ["sshpass", "-p", ssh_pass] + ssh_cmd

    # If --print-only flag is provided, just print the SSH command instead of executing it.
    if args.print_only:
        print("SSH command to be executed:")
        print(" ".join(shlex.quote(arg) for arg in ssh_cmd))
        sys.exit(0)

    try:
        subprocess.run(ssh_cmd)
    except Exception as e:
        print(f"Error executing SSH: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
