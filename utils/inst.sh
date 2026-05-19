#!/bin/bash

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ln -s "${REPO_ROOT}/ansible-ssh.py" ~/.local/bin/ansible-ssh

ansible-ssh -C bash | sudo tee /etc/bash_completion.d/ansible-ssh

source /etc/bash_completion.d/ansible-ssh
