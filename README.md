# ansible-ssh

**ansible-ssh** is a command-line utility that enables SSH connection to a host, utilizing connection variables retrieved from an Ansible inventory file.  
It provides user-friendly bash command completion (inlcuding completing hosts from Ansible inventory file).
It supports connection details (such as host, port, user, key, and even password), including extra SSH options via `ansible_ssh_common_args` and `ansible_ssh_extra_args`.

## Features

Simply run  `ansible-ssh -i inventory <host>`

- **Automated Connection Parameters:** Extracts connection details from an Ansible inventory.
- **Fallback Mechanism:** Uses standard SSH configuration (e.g., `~/.ssh/config`) for any unspecified settings.
- **Bash Completion:** Generates a bash completion script that auto-completes host names based on your inventory.
- **Extra SSH Options:** Incorporates additional SSH arguments defined in your inventory. (eg ProxyCommand)

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

# Install package using pip (yes pypi package has the name reversed)
pip install ssh-ansible

# Generate bash_completion script
ansible-ssh -C bash | sudo tee /etc/bash_completion.d/ansible-ssh
source /etc/bash_completion.d/ansible-ssh
```


## Usage
```bash
$ ansible-ssh --help
usage: ansible-ssh.py [-h] [-C {bash}] [-i INVENTORY] [host] [--print-only] [--debug]

Connect to a host using connection variables from an Ansible inventory.

positional arguments:
  host                  Host to connect to

options:
  -h, --help            show this help message and exit
  -C {bash}, --complete {bash}
                        Print bash completion script and exit
  -i INVENTORY, --inventory INVENTORY
                        Path to the Ansible inventory file
  --print-only          Print SSH command instead of executing it
  --debug               Increase verbosity (can be used up to 3 times)

EXAMPLES:
  Connect to a host:
         ansible-ssh.py -i inventory myhost

  Connect to a host with ssh verbosity:
         ansible-ssh.py -i inventory myhost --debug --debug

  Print SSH command:
         ansible-ssh.py -i inventory myhost --print-only

  Generate and install bash completion script:
         ansible-ssh.py -C bash | sudo tee /etc/bash_completion.d/ansible-ssh.py

```
