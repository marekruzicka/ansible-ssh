# ansible-ssh

**ansible-ssh** is a command-line utility that enables SSH connection to a host, utilizing connection variables retrieved from an Ansible inventory file.  
It provides user-friendly bash command completion (including completing hosts from Ansible inventory file).
It supports connection details (such as host, port, user, key, and password) as well as advanced SSH options like ProxyJump/ProxyCommand for bastion host configurations.

## Features

Simply run `ansible-ssh <host>` (if ansible.cfg exists) or `ansible-ssh -i inventory <host>`

- **Automated Connection Parameters:** Extracts connection details from an Ansible inventory.
- **ansible.cfg Integration:** Automatically detects and uses inventory file from ansible.cfg when present.
- **Advanced SSH Options:** Supports ProxyJump, ProxyCommand, and other SSH options via `ansible_ssh_common_args` and `ansible_ssh_extra_args`.
- **Fallback Mechanism:** Uses standard SSH configuration (e.g., `~/.ssh/config`) for any unspecified settings.
- **Smart Bash Completion:** Auto-completes inventory files from `ansible.cfg` and host names from your inventory.
- **Multiple Inventory Formats:** Works with both YAML and INI inventory formats.

## Requirements

- **Python3**
- **Ansible:** Required for running `ansible-inventory`.
- **sshpass:** (Optional) Required for password-based SSH connections.
- **bash-completion:** This is pretty much 50% of the functionality.
- **jq:** Required for parsing JSON output in the bash completion script.


## Installation
### shell

Clone the repository, link/copy somewhere into `$PATH`, and install bash completion script.  


```bash
# Probably don't need to install anything, but for the reference...
sudo apt-get update
sudo apt-get install git python3 ansible-core sshpass jq bash-completion -y

git clone https://github.com/marekruzicka/ansible-ssh.git
cd ansible-ssh
chmod +x ansible-ssh/ansible-ssh.py

# Link/copy somewhere within $PATH
ln -s $PWD/ansible-ssh.py ~/.local/bin/ansible-ssh

# Generate bash_completion script
ansible-ssh -C bash | sudo tee /etc/bash_completion.d/ansible-ssh
source /etc/bash_completion.d/ansible-ssh
```

### pip
Create or activate virtual env, install it using `pip`, and install bash completion script.
```bash
# Create, activate python virtual environment
virtualenv myvenv
source myvenv/bin/activate

# Install package using pip (yes, pypi package has the name reversed. ansible-ssh is taken :-( )
pip install ssh-ansible

# Generate bash_completion script
ansible-ssh -C bash | sudo tee /etc/bash_completion.d/ansible-ssh
source /etc/bash_completion.d/ansible-ssh
```


## Usage
```bash
$ ansible-ssh --help
usage: ansible-ssh [-h] [-C {bash}] [-i INVENTORY] [host] [--print-only] [--debug]

Connect to a host using connection variables from an Ansible inventory.

positional arguments:
  host                  Host to connect to

options:
  -h, --help            show this help message and exit
  -C {bash}, --complete {bash}
                        Print bash completion script and exit
  -i INVENTORY, --inventory INVENTORY
                        Path to the Ansible inventory file (optional if ansible.cfg exists)
  --print-only          Print SSH command instead of executing it
  --debug               Increase verbosity (can be used up to 3 times)

EXAMPLES:
  Connect to a host (using ansible.cfg):
         ansible-ssh myhost

  Connect to a host with specific inventory:
         ansible-ssh -i inventory myhost

  Connect to a host with ssh verbosity:
         ansible-ssh -i inventory myhost --debug --debug

  Print SSH command without executing:
         ansible-ssh myhost --print-only

  Generate and install bash completion script:
         ansible-ssh -C bash | sudo tee /etc/bash_completion.d/ansible-ssh

```

## ansible.cfg Integration

ansible-ssh automatically detects and uses inventory configuration from `ansible.cfg` files, following Ansible's standard configuration hierarchy:

1. `$ANSIBLE_CONFIG` environment variable
2. `./ansible.cfg` (current directory)
3. `~/.ansible.cfg` (user home directory)  
4. `/etc/ansible/ansible.cfg` (system-wide)

### Example Configuration

```ini
# ansible.cfg
[defaults]
inventory = ./hosts.ini
```

With this configuration, you can simply run:
```bash
# No need to specify -i inventory
ansible-ssh myhost
```

### Smart Bash Completion

The bash completion is ansible.cfg-aware:
- When you type `ansible-ssh -i <TAB>`, it suggests the inventory file from ansible.cfg first
- When no `-i` is specified, it uses the inventory from ansible.cfg for host completion

```bash
# Tab completion suggests ./hosts.ini from ansible.cfg
ansible-ssh -i <TAB>

# Tab completion shows hosts from the configured inventory
ansible-ssh <TAB>
```
