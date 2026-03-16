#!/bin/bash
# Script to launch the SITL container
# Note: --in-pod 0 disables podman-compose's automatic pod creation,
# which would otherwise conflict with userns_mode: keep-id in compose.yml.

# Parse arguments
REBOOT=false
while [[ "$#" -gt 0 ]]; do
    case $1 in
        -r|--reboot) REBOOT=true ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

# Allow local X11 connections for GUI (Gazebo/Rviz)
xhost +local:root || true

# Check if podman-compose exists
if ! command -v podman-compose &> /dev/null; then
    # Try adding pipx bin to path
    export PATH="$PATH:$HOME/.local/bin"
    if ! command -v podman-compose &> /dev/null; then
        echo "podman-compose not found in PATH. Please run ./scripts/install_host_deps.sh first."
        exit 1
    fi
fi

if [ "$REBOOT" = true ]; then
    echo "Rebooting: Stopping and removing existing containers..."
    podman-compose --in-pod 0 -f compose.yml down
fi

echo "Building and starting the SITL container..."
podman-compose --in-pod 0 -f compose.yml up -d --build

echo "Container started. Attaching to the terminal..."
podman exec -it drone_sitl_dev /bin/bash
