#!/bin/bash
#
# Post-create script for the development container
#

sudo su - vscode -c 'mkdir -pv /home/vscode/.omp && chown vscode:vscode /home/vscode/.omp'

curl -fsSL https://omp.sh/install | sh

mkdir -pv ~/.local/bin/
ln -s ~/.bun/bin/omp ~/.local/bin/