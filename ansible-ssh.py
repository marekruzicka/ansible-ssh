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
try:
    from importlib.metadata import version as _pkg_version, PackageNotFoundError as _PkgNotFound
except ImportError:  # Python < 3.8
    from importlib_metadata import version as _pkg_version, PackageNotFoundError as _PkgNotFound  # type: ignore


def get_version():
    """Return the installed package version, including git commit for dev builds."""
    try:
        return _pkg_version("ssh-ansible")
    except _PkgNotFound:
        return "unknown"

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
    local cur prev inv_index inv_file hostlist verbose_count options
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    _find_ansible_cfg_inventory() {
        local cfg inv
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

    # Available options at the top level
    if [[ $COMP_CWORD -eq 1 ]]; then
        # If current word starts with -, complete options
        if [[ "$cur" == -* ]]; then
            COMPREPLY=( $(compgen -W "-C --complete -h --help -i --inventory --vault-password-file" -- "$cur") )
            return 0
        else
            # Try to complete hosts from ansible.cfg inventory if available
            local cfg_inv=$(_find_ansible_cfg_inventory)
            if [ -n "$cfg_inv" ]; then
                hostlist=$(ansible-inventory -i "$cfg_inv" --list 2>/dev/null | jq -r '
                    (._meta.hostvars | keys[]) // empty,
                    (.[] | select(type == "object" and has("hosts")) | .hosts[]?) // empty
                ' 2>/dev/null | sort -u)
                COMPREPLY=( $(compgen -W "$hostlist" -- "$cur") )
                return 0
            fi
            
            # If no ansible.cfg inventory, complete options
            COMPREPLY=( $(compgen -W "-C --complete -h --help -i --inventory --vault-password-file" -- "$cur") )
            return 0
        fi
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
    # Locate the --vault-password-file argument
    vault_pw_index=-1
    for i in "${!COMP_WORDS[@]}"; do
        if [[ "${COMP_WORDS[i]}" == "--vault-password-file" ]]; then
            vault_pw_index=$((i+1))
            break
        fi
    done

    # If completing the vault password file path, do plain file completion
    if [ $COMP_CWORD -eq $vault_pw_index ]; then
        COMPREPLY=( $(compgen -f -- "$cur") )
        return 0
    fi
    # If completing the inventory file argument, check for ansible.cfg in standard locations
    if [ $COMP_CWORD -eq $inv_index ]; then
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
        inv_file=$(_find_ansible_cfg_inventory)
        if [ -z "$inv_file" ]; then
            return 0
        fi
    fi

    # If host has been selected from the inventory, suggest additional argument completions.
    if [ $COMP_CWORD -ge $((inv_index+2)) ] || ([ $inv_index -eq -1 ] && [ $COMP_CWORD -ge 2 ]); then
        verbose_count=0
        print_only_count=0
        for word in "${COMP_WORDS[@]}"; do
            if [ "$word" == "-v" ]; then
                verbose_count=$((verbose_count+1))
            fi
            if [ "$word" == "--print-only" ]; then
                print_only_count=$((print_only_count+1))
            fi
        done
        options=""
        if [ $print_only_count -eq 0 ]; then
            options="--print-only"
        fi
        if [ $verbose_count -eq 0 ]; then
            if [ -z "$options" ]; then
                options="-v"
            else
                options="$options -v"
            fi
        fi
        if [ -n "$options" ]; then
            COMPREPLY=( $(compgen -W "$options" -- "$cur") )
        else
            COMPREPLY=()
        fi
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


def get_vault_password_file_from_cfg(cfg_path):
    """
    Parse ansible.cfg and return the vault_password_file path if set.
    """
    parser = configparser.ConfigParser()
    parser.read(cfg_path)
    if parser.has_section("defaults") and parser.has_option("defaults", "vault_password_file"):
        path = parser.get("defaults", "vault_password_file")
        return os.path.expanduser(path)
    return None

def parse_arguments():
    """
    Parse command-line arguments for ansible-ssh.

    Returns:
        argparse.Namespace: Parsed arguments with inventory file, host, and optional flags.
        The optional flags include:
            - --complete: Print bash completion script.
            - --print-only: Print SSH command instead of executing it.
            - -v/--verbose: Increase SSH verbosity (stackable: -v, -vv, -vvv).
    
    Raises:
        SystemExit: If required arguments are missing.
    """
    parser = argparse.ArgumentParser(
        usage="%(prog)s [-h] [-C {bash}] [-i INVENTORY] [host] [--print-only] [-v]",
        description="Connect to a host using connection variables from an Ansible inventory.",
        epilog="EXAMPLES:\n"
               "  Connect to a host:\n\t %(prog)s -i inventory myhost\n\n"
               "  Connect to a host with ssh verbosity:\n\t %(prog)s -i inventory myhost -vv\n\n"
               "  Print SSH command:\n\t %(prog)s -i inventory myhost --print-only\n\n"
               "  Generate and install bash completion script:\n\t %(prog)s -C bash | sudo tee /etc/bash_completion.d/%(prog)s",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("-C", "--complete", choices=["bash"], help="Print bash completion script and exit")
    parser.add_argument("-i", "--inventory", help="Path to the Ansible inventory file")
    parser.add_argument("--vault-password-file", metavar="FILE",
                        help="Vault password file (overrides ansible.cfg vault_password_file)")
    parser.add_argument("--print-only", action="store_true", help="Print SSH command instead of executing it")
    parser.add_argument("-v", "--verbose", action="count", default=0, help="Increase SSH verbosity, stackable up to -vvv")
    parser.add_argument("--version", action="version", version=f"%(prog)s {get_version()}")
    parser.add_argument("host", nargs="?", help="Host to connect to")
    args = parser.parse_args()

    # If inventory is not provided, try to get it from ansible.cfg
    if not args.inventory and not args.complete:
        cfg_path = find_ansible_cfg()
        if cfg_path:
            inv = get_default_inventory_from_cfg(cfg_path)
            if inv:
                args.inventory = inv

    # If --vault-password-file is not provided, try to get it from ansible.cfg
    if not args.vault_password_file and not args.complete:
        cfg_path = find_ansible_cfg()
        if cfg_path:
            vpf = get_vault_password_file_from_cfg(cfg_path)
            if vpf and os.path.isfile(vpf):
                args.vault_password_file = vpf

    if not args.complete and (not args.inventory or not args.host):
        parser.error("the following arguments are required: -i/--inventory (or ansible.cfg must exist in one of the standard locations), host")
    return args

def get_host_vars(inventory_file, host, vault_password_file=None):
    """
    Retrieve host variables from the inventory using ansible-inventory.

    Args:
        inventory_file (str): Path to the Ansible inventory file.
        host (str): Host name.
        vault_password_file (str, optional): Path to a vault password file.

    Returns:
        dict: Host variables. Returns empty dict if host exists but has no variables.
              Vault-encrypted values that could not be decrypted are returned as-is
              (dicts with a ``__ansible_vault`` key).

    Raises:
        SystemExit: If ansible-inventory command fails, host is not found, or produces invalid JSON.
    """
    cmd = ["ansible-inventory", "-i", inventory_file]
    if vault_password_file:
        cmd += ["--vault-password-file", vault_password_file]
    cmd.append("--list")
    try:
        list_result = subprocess.run(
            cmd,
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

    # Collect all known hosts: from _meta.hostvars and from group hosts lists
    known_hosts = set()
    if "_meta" in inventory_data and "hostvars" in inventory_data["_meta"]:
        known_hosts.update(inventory_data["_meta"]["hostvars"].keys())
    for value in inventory_data.values():
        if isinstance(value, dict) and "hosts" in value:
            hosts_entry = value["hosts"]
            if isinstance(hosts_entry, list):
                known_hosts.update(hosts_entry)
            elif isinstance(hosts_entry, dict):
                known_hosts.update(hosts_entry.keys())

    if host not in known_hosts:
        print(f"Error: Host '{host}' not found in inventory '{inventory_file}'.", file=sys.stderr)
        sys.exit(1)

    host_vars = inventory_data.get("_meta", {}).get("hostvars", {}).get(host, {})

    if vault_password_file:
        host_vars = _decrypt_vault_vars(host_vars, vault_password_file)

    return host_vars


def _decrypt_vault_vars(vars_dict, vault_password_file):
    """Return a copy of vars_dict with any ``{__ansible_vault: ...}`` values decrypted.

    Uses ansible's own VaultLib so the same encryption format is always supported.
    Values that fail to decrypt (wrong password, corrupted data) are left as-is.
    """
    try:
        from ansible.parsing.vault import VaultLib, VaultSecret  # noqa: PLC0415
    except ImportError:
        return vars_dict  # ansible-core not importable; skip decryption

    try:
        with open(vault_password_file) as fh:
            password = fh.read().strip().encode()
    except OSError as exc:
        print(f"Warning: could not read vault password file '{vault_password_file}': {exc}",
              file=sys.stderr)
        return vars_dict

    vault = VaultLib(secrets=[("default", VaultSecret(password))])
    result = {}
    for key, val in vars_dict.items():
        if isinstance(val, dict) and "__ansible_vault" in val:
            try:
                decrypted = vault.decrypt(val["__ansible_vault"])
                result[key] = decrypted.decode("utf-8").strip()
            except Exception:
                result[key] = val  # keep encrypted form on failure
        else:
            result[key] = val
    return result

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

def _is_vault_encrypted(value):
    """Return True if value is an unresolved ansible-vault encrypted object."""
    return isinstance(value, dict) and "__ansible_vault" in value


def _scalar_or_none(value, var_name):
    """Return value if it is a plain scalar, else None (warning printed for vault objects)."""
    if _is_vault_encrypted(value):
        print(
            f"Warning: '{var_name}' is vault-encrypted and could not be decrypted. "
            "Use --vault-password-file.",
            file=sys.stderr,
        )
        return None
    return value


def build_ssh_command(host_vars, host):
    """
    Build the SSH command and target from host variables.

    Args:
        host_vars (dict): Host variables from the inventory.
        host (str): Host name.

    Returns:
        tuple: (ssh_cmd (list), ssh_pass (str or None), target (str))
    """
    # For host, check ansible_ssh_host then ansible_host, then fall back to the original host name
    host_ip = (
        _scalar_or_none(host_vars.get("ansible_ssh_host"), "ansible_ssh_host")
        or _scalar_or_none(host_vars.get("ansible_host"), "ansible_host")
        or host
    )
    # For user, check ansible_ssh_user then ansible_user.
    user = (
        _scalar_or_none(host_vars.get("ansible_ssh_user"), "ansible_ssh_user")
        or _scalar_or_none(host_vars.get("ansible_user"), "ansible_user")
    )
    port = _scalar_or_none(host_vars.get("ansible_port"), "ansible_port")
    key = _scalar_or_none(host_vars.get("ansible_private_key_file"), "ansible_private_key_file")
    # For password, check ansible_ssh_pass then ansible_password.
    ssh_pass = (
        _scalar_or_none(host_vars.get("ansible_ssh_pass"), "ansible_ssh_pass")
        or _scalar_or_none(host_vars.get("ansible_password"), "ansible_password")
    )
    
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

    # Check that ansible-inventory is available.
    if not shutil.which("ansible-inventory"):
        print("Error: ansible-inventory is required. Please install ansible.", file=sys.stderr)
        sys.exit(1)

    # Check that the inventory file exists.
    if not os.path.exists(args.inventory):
        print(f"Error: Inventory file '{args.inventory}' does not exist.", file=sys.stderr)
        sys.exit(1)

    # Get host variables from ansible-inventory.
    host_vars = get_host_vars(args.inventory, args.host, vault_password_file=args.vault_password_file)

    # Build the SSH command and extract SSH password if any.
    ssh_cmd, ssh_pass, target = build_ssh_command(host_vars, args.host)
    ssh_env = None

    # Insert the verbosity flags after "ssh"
    if args.verbose > 0:
        verbose_flags = ["-v"] * min(args.verbose, 3)
        ssh_cmd[1:1] = verbose_flags
        print("Connecting to {} with options: {}".format(target, " ".join(ssh_cmd[1:-1])))

    # If a password is provided, prepend sshpass to the command.
    if ssh_pass:
        if not shutil.which("sshpass"):
            print("Error: sshpass is required for password-based SSH. Please install sshpass.", file=sys.stderr)
            sys.exit(1)
        # Use sshpass -e (reads from SSHPASS env var) instead of -p to avoid
        # exposing the password in the process list (/proc/<pid>/cmdline).
        ssh_env = os.environ.copy()
        ssh_env["SSHPASS"] = ssh_pass
        ssh_cmd = ["sshpass", "-e"] + ssh_cmd

    # If --print-only flag is provided, just print the SSH command instead of executing it.
    if args.print_only:
        print("SSH command to be executed:")
        print(" ".join(shlex.quote(arg) for arg in ssh_cmd))
        sys.exit(0)

    try:
        result = subprocess.run(ssh_cmd, env=ssh_env)
        sys.exit(result.returncode)
    except Exception as e:
        print(f"Error executing SSH: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
