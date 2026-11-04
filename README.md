# Drone SITL

A **Software-In-The-Loop (SITL)** simulation of a multirotor drone that keeps
flying and holding position **after losing its GNSS/GPS signal**, by estimating
its global position from its camera via **visual map-matching**.

- **Autopilot:** PX4 SITL · **Simulator:** Gazebo Jetty · **Middleware:** ROS 2 Lyrical
- **Perf core:** Rust (perception / estimation) · **Glue:** Python (orchestration, analysis)
- **Environment:** Podman container (`scripts/dev.sh`), workflows via a `Makefile` run inside it (dev tooling via `mise`)

> 📄 Full specification: [`docs/specs/overview.md`](docs/specs/overview.md)

## How it works

Gazebo simulates the drone and its sensors (GNSS, camera, LiDAR, IMU, baro). PX4
SITL runs the autopilot and talks to ROS 2 over the uXRCE-DDS bridge. A **Rust
map-matching node** matches the live camera view against a pre-built,
georeferenced map to recover a **global position**, which is fused into PX4's
**EKF2** as external vision. When a **Python GNSS-loss injector** degrades or
drops GNSS, the drone falls back to IMU + visual map-matching and keeps flying.

See the [system diagram and data flow](docs/specs/overview.md#3-system-overview).

## Prerequisites

- [Podman](https://podman.io/) with `podman compose` (or Docker Compose)
- A Linux host with a Wayland or X11 display for the Gazebo / RViz GUIs
  (optional: `headless:=true` runs the simulator without a GUI)
- `make`

Everything else (ROS 2, Gazebo, PX4, Rust, Python) lives inside the container.

## Quickstart

On the host, build the image, start the dev container and open a shell in it
(on a Wayland desktop this also wires your display into it):

```bash
scripts/dev.sh shell
```

Everything below runs **inside the container**:

```bash
# Build the ROS 2 workspace
make build

# Launch the simulator only (Gazebo + PX4 SITL) ...
make sim
# ... or the full stack, or the demo mission (each includes the simulator;
# only one of the three can run at a time)
make run
make mission

# Stop whichever of those is running
make stop
```

Run `make help` to see all targets. The Makefile only runs inside the dev
container; on the host it refuses and prints how to get in. The container
itself is managed from the host with `scripts/dev.sh`:

| Command | What it does |
|---------|--------------|
| `scripts/dev.sh up` | build the image and start the container (detects the GUI display) |
| `scripts/dev.sh shell` | open a shell in the container, starting it if needed |
| `scripts/dev.sh exec CMD...` | run one command in it, e.g. `scripts/dev.sh exec make build` |
| `scripts/dev.sh down` | stop and remove the container |

A VS Code dev container (`.devcontainer/`) works too: use its terminal.

## Repository layout

```text
docs/specs/     Specification documents (start with overview.md)
ros2_ws/src/    ROS 2 packages (Rust perception + Python orchestration)
sim/            Gazebo worlds and drone/sensor models
maps/           Offline-built georeferenced feature maps
tools/          Offline pipelines (e.g. map builder)
compose.yaml         Podman Compose dev/sim environment
Containerfile        Dev/sim image (container runtime = source of version truth)
rust-toolchain.toml  Pinned Rust toolchain (rustup)
mise.toml            Dev tools (pre-commit, linters) for host and container
Makefile             Developer workflow entrypoints (run inside the container)
scripts/dev.sh       Host-side dev container control (up / shell / exec / down)
```

> The `ros2_ws/`, `sim/`, `maps/`, and `tools/` trees are the planned layout
> from the spec and are populated as components land — see the
> [milestones](docs/specs/overview.md#10-milestones-indicative).

## GUI (Gazebo / RViz) notes

Qt GUIs (Gazebo, RViz) use X11 first and fall back to Wayland
(`QT_QPA_PLATFORM=xcb;wayland` in `compose.yaml`). Gazebo's GUI requires X11:
on native Wayland its render engine fails to initialise, so on a Wayland
desktop it runs through Xwayland.

- **Wayland desktop (GNOME etc.):** nothing to do. `scripts/dev.sh up` finds your
  Xwayland server (display and per-session cookie file) and your compositor
  socket, and mounts them into the container, so no `xhost` step is needed.
  It also works from a tty/SSH shell on the same machine. Override with
  `DISPLAY=:1 XAUTH_FILE=/path/to/cookie scripts/dev.sh up`. Mounts are fixed when the
  container is created, so run `scripts/dev.sh down && scripts/dev.sh up` after logging into a
  new graphical session (Xwayland gets a new cookie file each login).
- **Plain X11 session:** `scripts/dev.sh up` uses your shell's `$DISPLAY` and
  `$XAUTHORITY` (or `~/.Xauthority`). If neither cookie exists, run
  `xhost +local:` on the host instead (rootless Podman may need
  `xhost +SI:localuser:root`).
- **VS Code dev container:** VS Code forwards your Wayland socket itself, so
  GUIs work without the steps above.
- **No display at all:** `ros2 launch drone_bringup sim.launch.py
  headless:=true` runs the Gazebo server without the GUI.

`compose.yaml` passes `/dev/dri` into the container for GPU-accelerated
rendering (Intel/AMD via Mesa). If the host has no `/dev/dri`, remove the
`devices` block; Gazebo then falls back to software rendering. NVIDIA hosts
additionally need the NVIDIA Container Toolkit / CDI setup. Changes to
`compose.yaml` take effect only after the container is recreated (`scripts/dev.sh down
&& scripts/dev.sh up`, or "Rebuild Container" in VS Code).

## Development

- Format / lint: `make fmt` · `make lint`
- Test: `make test`
- Contributor & agent conventions: [`AGENTS.md`](AGENTS.md)

### Git & SSH inside the container

`compose.yaml` mounts your host git/SSH configuration **read-only** into the
container (which runs as `root`, so paths land under `/root`):

| Host | Purpose |
|------|---------|
| `~/.ssh` | keys, `config`, `known_hosts` |
| `~/.gitconfig` | identity, aliases, credential helpers |
| `~/.config/gh`, `~/.git-credentials` | tokens for the `gh` / `store` credential helpers |
| `$SSH_AUTH_SOCK` | forwarded `ssh-agent` (passphrase-protected / hardware keys) |

`gh` and `openssh-client` are installed in the image, so `git commit` /
`git push` (HTTPS or SSH) and private `cargo` git dependencies work inside
the container exactly as on the host. Notes:

- Every path in the table must exist on the host or the bind mount fails;
  `touch ~/.git-credentials` / `mkdir -p ~/.config/gh` if you don't use them.
- Start the agent and `ssh-add` your key **before** `scripts/dev.sh up`; the socket path
  is captured when the container is created. Without an agent, ssh falls back
  to the key files in `~/.ssh`.
- `~/.ssh` is read-only, so ssh cannot append to `known_hosts` for hosts you
  have never connected to from the host. Connect once from the host first.
- GPG commit signing is not set up in the image.

### Tools inside the container

Besides the ROS 2 / Rust / Python toolchains, the image ships `tmux`, `git`,
`gh`, `mise` and the **Claude Code CLI** (`claude`). Your host `~/.claude` and
`~/.claude.json` are mounted read-write, so `claude` inside the container is
already logged in and shares settings, plugins and memory with the host.
`mise` is activated in interactive shells and trusts the repo's `mise.toml`;
run `mise install` once to fetch pre-commit and the linters (they persist in
the `drone-sitl-mise` volume). `mise.toml` must never pin python or rust — the
system Python belongs to ROS 2 and Rust comes from `rust-toolchain.toml`.

## Status

Early scaffolding. The specification is drafted; components are implemented
against the milestones in [`docs/specs/overview.md`](docs/specs/overview.md).
