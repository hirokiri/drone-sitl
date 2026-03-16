#!/bin/bash
echo "Installing host dependencies for Podman SITL..."
sudo apt-get update
sudo apt-get install -y podman podman-compose
echo "Installation complete. You can now use podman and podman-compose natively on Ubuntu."
