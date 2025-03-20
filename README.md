# ansible-ssh

**ansible-ssh** is a command-line utility that connects to a host using connection variables retrieved from an Ansible inventory file.  
It leverages Ansible’s inventory system to extract connection details (such as host, port, user, key, and even password) and then invokes SSH with the proper parameters.  
It supports extra SSH options via `ansible_ssh_common_args` and `ansible_ssh_extra_args` (*still experimental and not working properly*) and can generate a bash completion script for convenience.

## Features

`ansible-ssh -i inventory host`

- **Automated Connection Parameters:** Extracts connection details from an Ansible inventory.
- **Fallback Mechanism:** Uses standard SSH configuration (e.g., `~/.ssh/config`) for any unspecified settings.
- **Extra SSH Options:** Incorporates additional SSH arguments defined in your inventory. (disabled for now)
- **Bash Completion:** Generates a bash completion script that auto-completes host names based on your inventory.

## Requirements

- **Python3**
- **Ansible:** For running `ansible-inventory`.
- **sshpass:** (Optional) Required for password-based SSH connections.
- **bash-completion:** This is pretty much 50% of the functionality.
- **jq:** Required for parsing JSON output in the bash completion script.


## Installation

Clone the repository, link/copy somewhere into $PATH, and install bash completion script. Make it executable and most likely rerun bash to load completion script.
```bash
git clone https://your.repo.url/ansible-ssh.git
cd ansible-ssh
chmod +x ansible-ssh.py

ln -s ansible-ssh.py ~/.local/bin/ansible-ssh

ansible-ssh -C bash | sudo tee /etc/bash_completion.d/ansible-ssh
```

**On Debian/Ubuntu:**
```bash
sudo apt-get update
sudo apt-get install python3 ansible-core sshpass jq bash-completion -y
```
**On RHEL/CentOS:**
```bash
sudo yum install python3 ansible-core sshpass jq bash-completion -y
```

## Usage
```bash
$ ansible-ssh --help
usage: ansible-ssh [-h] [-C {bash}] [-i INVENTORY] [host]

Connect to a host using connection variables from an Ansible inventory.

positional arguments:
  host                  Host to connect to

options:
  -h, --help            show this help message and exit
  -C {bash}, --complete {bash}
                        Print bash completion script and exit
  -i INVENTORY, --inventory INVENTORY
                        Path to the Ansible inventory file

EXAMPLES:
  Connect to a host:
	 ansible-ssh -i inventory myhost

  Generate and install bash completion script:
	 ansible-ssh -C bash | sudo tee /etc/bash_completion.d/ansible-ssh

```
