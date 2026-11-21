# Dev / sim image for Drone SITL
# Ubuntu 26.04 · ROS 2 Lyrical · Gazebo Jetty · Rust (rustup) + system Python
#
# This image is the single source of version truth for everything that runs
# inside the container. mise is installed only for the developer tools pinned
# in mise.toml (pre-commit, linters); it must never pin python or rust, so it
# cannot shadow the system Python that ROS 2 requires or the rustup toolchain.
#
# Build:  podman build -t drone-sitl:dev -f Containerfile .
# (usually invoked through `compose.yaml` / `make build`)

FROM docker.io/library/ros:lyrical-ros-base

ENV DEBIAN_FRONTEND=noninteractive \
    ROS_DISTRO=lyrical \
    # Lets the Makefile detect it is running inside this image.
    DRONE_SITL_CONTAINER=1

# --- System & ROS 2 <-> Gazebo / PX4 dependencies -------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake ninja-build bc curl wget ca-certificates \
        git gh openssh-client tmux \
        python3-pip python3-venv python-is-python3 \
        libclang-dev pkg-config libssl-dev \
        ros-lyrical-ros-gz \
        ros-lyrical-rmw-cyclonedds-cpp \
        ros-dev-tools \
    && rm -rf /var/lib/apt/lists/*

# The repo is bind-mounted at /drone-sitl (see compose.yaml) and may be
# owned by a different UID than the container user (e.g. rootful Podman). Tell
# git it is trusted so the host's identity/config (mounted via compose.yaml)
# works without "dubious ownership" errors.
RUN git config --system --add safe.directory /drone-sitl

# Python linter/formatter used by `make fmt` / `make lint`.
RUN pip install --no-cache-dir --break-system-packages ruff

# Use CycloneDDS (recommended for PX4 uXRCE-DDS interop).
ENV RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

# Where compose.yaml bind-mounts the host's ssh-agent socket. This lives here
# and NOT in compose.yaml's `environment:` on purpose: podman-compose resolves
# `${SSH_AUTH_SOCK:-/dev/null}` in compose.yaml against the service's own
# environment when the host variable is unset, which would turn the fallback
# into a bind of this path onto itself and fail to start the container.
ENV SSH_AUTH_SOCK=/run/host-services/ssh-auth.sock

# Where compose.yaml bind-mounts the host's Wayland socket and X11 cookie file
# (same reasoning as above for keeping these out of compose.yaml's
# `environment:`). Qt requires XDG_RUNTIME_DIR to be set to find
# $XDG_RUNTIME_DIR/$WAYLAND_DISPLAY.
ENV XDG_RUNTIME_DIR=/run/user/0 \
    WAYLAND_DISPLAY=wayland-0 \
    XAUTHORITY=/run/host-services/Xauthority

# --- PX4 SITL + uXRCE-DDS bridge --------------------------------------------
# The autopilot, its ROS 2 message definitions and the DDS agent are pinned
# here and nowhere else. px4_msgs must match the PX4 release (same tag), or
# the uXRCE-DDS topics silently fail to deserialize.
ARG PX4_VERSION=v1.17.0
ARG XRCE_AGENT_VERSION=v2.4.3

# Read by drone_bringup/launch/sim.launch.py to find the px4 binary, its
# ROMFS, and PX4's Gazebo models / worlds / plugins.
ENV PX4_DIR=/opt/PX4-Autopilot

# PX4's build-time Python packages go into their own venv: it needs empy 3,
# which must not replace the system empy that ROS 2's ament/rosidl use. The
# ROS underlay is sourced so CMake finds Gazebo Jetty (ROS vendor packages)
# and builds the gz_bridge module and PX4's Gazebo plugins.
RUN git clone --depth 1 --branch "${PX4_VERSION}" \
        --recurse-submodules --shallow-submodules \
        -c advice.detachedHead=false \
        https://github.com/PX4/PX4-Autopilot.git "${PX4_DIR}" \
    && python3 -m venv /opt/px4-venv \
    && /opt/px4-venv/bin/pip install --no-cache-dir \
        'empy>=3.3,<4' future jinja2 jsonschema kconfiglib lark numpy \
        packaging pyros-genmsg pyyaml 'setuptools<81' six toml \
    && . "/opt/ros/${ROS_DISTRO}/setup.sh" \
    && PATH="/opt/px4-venv/bin:${PATH}" make -C "${PX4_DIR}" px4_sitl_default

# Micro XRCE-DDS Agent: bridges PX4's uXRCE-DDS client to ROS 2 (DDS).
RUN git clone --depth 1 --branch "${XRCE_AGENT_VERSION}" \
        -c advice.detachedHead=false \
        https://github.com/eProsima/Micro-XRCE-DDS-Agent.git /tmp/xrce-agent \
    && cmake -S /tmp/xrce-agent -B /tmp/xrce-agent/build -GNinja \
        -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local \
    && cmake --build /tmp/xrce-agent/build \
    && cmake --install /tmp/xrce-agent/build \
    && ldconfig \
    && rm -rf /tmp/xrce-agent

# px4_msgs as a prebuilt underlay in /opt/px4_ros (sourced by the profile
# script below), so `make build` only builds this repo's own packages.
RUN git clone --depth 1 --branch "${PX4_VERSION}" \
        -c advice.detachedHead=false \
        https://github.com/PX4/px4_msgs.git /tmp/px4_ros_ws/src/px4_msgs \
    && . "/opt/ros/${ROS_DISTRO}/setup.sh" \
    && cd /tmp/px4_ros_ws \
    && colcon build --merge-install --install-base /opt/px4_ros \
        --cmake-args -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF \
    && rm -rf /tmp/px4_ros_ws

# --- Rust toolchain (rustup, pinned by rust-toolchain.toml) ----------------
# rustup reads rust-toolchain.toml from the workspace and auto-selects the
# pinned toolchain. Copying it here warms the toolchain into the image layer.
RUN curl --proto '=https' --tlsv1.2 -fsSL https://sh.rustup.rs \
        | sh -s -- -y --no-modify-path --profile minimal
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /workspace
COPY rust-toolchain.toml /workspace/rust-toolchain.toml
RUN rustup show

# --- Node.js (Ubuntu's packaged version) + pnpm ----------------------------
# For JS-based developer tooling (npx-run MCP servers, linters, ...); not part
# of the simulation runtime. Its own late layer so that changing it does not
# invalidate the expensive PX4 / px4_msgs build layers above.
RUN apt-get update && apt-get install -y --no-install-recommends \
        nodejs npm \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g pnpm \
    && npm cache clean --force

# --- Developer tools: mise + Claude Code CLI -------------------------------
# mise runs the dev tools pinned in mise.toml (pre-commit, shellcheck,
# yamllint) inside the container as well as on the host. mise.toml must not
# pin python/rust — see the header comment there. The repo's config is
# trusted up-front so `mise` works non-interactively from `make`.
# Claude Code's native installer puts the binary in /root/.local/bin; its
# login/settings come from the host's ~/.claude mounted by compose.yaml.
RUN curl -fsSL https://mise.run | sh \
    && curl -fsSL https://claude.ai/install.sh | bash
ENV PATH="/root/.local/bin:${PATH}" \
    MISE_TRUSTED_CONFIG_PATHS=/drone-sitl

# Source the ROS 2 + px4_msgs underlays and activate mise in every shell.
#
# This goes in /etc/profile.d, NOT only in /root/.bashrc: the base image's
# .bashrc starts with the usual "[ -z "$PS1" ] && return" guard, so anything
# appended to it is skipped by the non-interactive login shells (`bash -lc`)
# the Makefile uses for `make build` / `make test`. Login shells source
# /etc/profile.d regardless of interactivity; .bashrc then pulls in the same
# file for interactive non-login shells (`podman exec ... bash`, IDE
# terminals). Both parts are guarded so double-sourcing is a no-op.
RUN printf '%s\n' \
      '# Drone SITL dev shell setup (see Containerfile).' \
      '# /run is a tmpfs; make sure the (mounted-into) runtime dir has the mode Qt expects.' \
      'if [ -n "${XDG_RUNTIME_DIR:-}" ]; then mkdir -p "$XDG_RUNTIME_DIR" 2>/dev/null; chmod 700 "$XDG_RUNTIME_DIR" 2>/dev/null; fi' \
      'if [ -z "${AMENT_PREFIX_PATH:-}" ]; then' \
      '  if [ -n "${BASH_VERSION:-}" ]; then . "/opt/ros/${ROS_DISTRO}/setup.bash"; else . "/opt/ros/${ROS_DISTRO}/setup.sh"; fi' \
      '  # px4_msgs underlay (built above), on top of the ROS 2 underlay.' \
      '  if [ -n "${BASH_VERSION:-}" ]; then . /opt/px4_ros/setup.bash; else . /opt/px4_ros/setup.sh; fi' \
      'fi' \
      'if [ -n "${BASH_VERSION:-}" ] && [ -z "${MISE_SHELL:-}" ] && command -v mise >/dev/null 2>&1; then' \
      '  eval "$(mise activate bash)"' \
      'fi' \
      > /etc/profile.d/drone-sitl.sh \
    && echo '. /etc/profile.d/drone-sitl.sh' >> /root/.bashrc

CMD ["bash"]
