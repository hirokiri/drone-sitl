#!/bin/bash
set -e

WORKSPACE_DIR="/home/$(whoami)/work/drone-sitl"
cd $WORKSPACE_DIR

echo "Setting up standard PX4 and ArduPilot SITL workspaces..."

sudo apt-get update

# --- PX4 ---
if [ ! -d "PX4-Autopilot" ]; then
    echo "Cloning PX4-Autopilot..."
    git clone https://github.com/PX4/PX4-Autopilot.git --recursive
fi

echo "Installing PX4 dependencies..."
pushd PX4-Autopilot >/dev/null
bash ./Tools/setup/ubuntu.sh --no-nuttx --no-sim-tools
popd >/dev/null

# --- ArduPilot ---
if [ ! -d "ardupilot" ]; then
    echo "Cloning ArduPilot..."
    git clone https://github.com/ArduPilot/ardupilot.git
fi

echo "Installing ArduPilot dependencies..."
pushd ardupilot >/dev/null
git submodule update --init --recursive
USER=$(whoami) ./Tools/environment_install/install-prereqs-ubuntu.sh -y
popd >/dev/null


echo "================================================="
echo "Setup Complete! You can now build and run SITL."
echo "For PX4:"
echo "  cd PX4-Autopilot && make px4_sitl gz_x500"
echo ""
echo "For ArduPilot:"
echo "  cd ardupilot/ArduCopter && sim_vehicle.py -v ArduCopter -f gazebo-iris --console"
echo "================================================="
