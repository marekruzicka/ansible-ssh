#!/usr/bin/env python3
"""
ansible-ssh: Connect to a host using connection variables from an Ansible inventory,
with fallbacks to standard SSH configuration (e.g. ~/.ssh/config) for unspecified settings.
It also supports additional SSH options via ansible_ssh_common_args and ansible_ssh_extra_args,
which can be disabled by setting ENABLE_EXTRA_SSH_OPTIONS to False.

Usage:
    ansible-ssh.py -i <inventory_file> <host>
    
Requirements:
    - ansible (for ansible-inventory)
    - Python 3
    - sshpass (if using password-based SSH)
"""

import argparse
import json
import os
import shlex
import subprocess
import sys
import shutil

# Set this to False if you want to disable parsing of extra SSH options.
ENABLE_EXTRA_SSH_OPTIONS = False

def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Connect to a host using connection variables from an Ansible inventory."
    )
    parser.add_argument("-i", "--inventory", required=True, help="Path to the Ansible inventory file")
    parser.add_argument("host", help="Host to connect to")
    return parser.parse_args()

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
