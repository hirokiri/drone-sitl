# AGENTS.md

Guidance for AI coding agents (and humans) working in this repository.

## What this project is

Drone SITL is a Software-In-The-Loop simulation of a multirotor that navigates
**GPS-denied** by estimating global position from its camera (**visual
map-matching**) and fusing that into **PX4 EKF2**. Read
[`docs/specs/overview.md`](docs/specs/overview.md) before making changes — it is
the source of truth for scope, architecture, and requirements.

## Tech stack (do not swap without updating the spec)

| Concern | Choice |
|---------|--------|
| Autopilot | PX4 SITL |
| Simulator | Gazebo Jetty |
| Middleware | ROS 2 Lyrical |
| Perf core | Rust (`rclrs`/`r2r`) — perception & estimation nodes |
| Glue / tooling | Python 3.14 — orchestration, injection, analysis, launch |
| Environment | Podman container (runtime source of truth) + `mise` for dev tools; `scripts/dev.sh` (host) manages it, `Makefile` runs inside it |

## Language boundary (important)

- **Rust** = real-time performance core: feature extraction, visual
  map-matching, pose gating. Keep it allocation-light and deterministic.
- **Python** = glue only: launch files, mission/scenario control, GNSS-loss
  injection, logging, metrics, analysis. Do **not** put real-time estimation in
  Python.
- If a Python node becomes a proven bottleneck on the estimation path, propose
  moving it to Rust rather than optimizing Python in place.

## Working conventions

- **Build & run through the `Makefile`** (`make build`, `make sim`, `make run`,
  `make test`) **inside the dev container** — the Makefile refuses to run on
  the host. From the host, use `scripts/dev.sh exec make <target>` (or
  `scripts/dev.sh shell`). Container lifecycle and GUI wiring live in
  `scripts/dev.sh`, not in make. Don't assume host-installed ROS 2 / Gazebo /
  PX4.
- **Toolchain versions live in one place each:** the container runtime
  (Ubuntu, ROS 2, Gazebo, system Python) in `Containerfile`, the Rust version in
  `rust-toolchain.toml`, and auxiliary dev tools (pre-commit, linters) in
  `mise.toml`. Don't hardcode versions elsewhere; update the owning file and
  the spec's stack table together. `mise` is available on the host and in the
  container, but `mise.toml` must never pin python or rust.
- **The dev container reuses host config:** `~/.ssh`, `~/.gitconfig`, git
  credential stores and `~/.claude` are bind-mounted (see `compose.yaml`), and
  `git`, `gh`, `tmux`, `mise` and the Claude Code CLI are installed in the
  image.
- **Everything crosses node boundaries as ROS 2 topics/services** so it is
  recordable (`ros2 bag`) and introspectable. No hidden side-channels.
- **Ground-truth from the simulator is for evaluation only** — never feed it
  into the estimator or controller.
- **Determinism:** scenarios (GNSS-loss timing, mission plan, RNG seeds) come
  from config, not hardcoded literals.

## Before you finish a change

- `make fmt` and `make lint` are clean.
- `make build` and `make test` pass.
- If you changed architecture, topics, the stack, or the repo layout, update the
  relevant doc under `docs/specs/` in the same change.
- Keep new packages within the [proposed layout](docs/specs/overview.md#8-proposed-repository-layout);
  if you deviate, update the spec and say why.

## Docs map

- `docs/specs/overview.md` — top-level spec (read first).
- `docs/specs/architecture.md` — node graph, topics/QoS, PX4↔ROS 2 mapping *(planned)*.
- `docs/specs/simulation.md` — world, drone model, sensors *(planned)*.
- `docs/specs/estimation.md` — map-matching + EKF2 fusion *(planned)*.
- `docs/specs/evaluation.md` — metrics, scenarios, acceptance *(planned)*.
