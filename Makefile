# Drone SITL — developer workflow entrypoints.
#
# This Makefile runs INSIDE the dev container. Get there from the host with
#
#   scripts/dev.sh shell             # start the container if needed + shell
#   scripts/dev.sh exec make build   # or run a single target from the host
#
# or open the repo in a VS Code dev container. The container itself (image,
# start/stop, GUI wiring) is managed by scripts/dev.sh, not by make.
#
#   make help        # list targets
#   make build       # colcon build the ROS 2 workspace
#   make sim         # launch Gazebo + PX4 SITL
#   make run         # bring up the full ROS 2 stack
#   make mission     # run a demo mission
#   make stop        # stop a running sim/run/mission
#   make test        # run tests
#   make fmt lint    # format / lint Rust + Python
#   make clean       # remove build artifacts

# DRONE_SITL_CONTAINER is set by the Containerfile.
ifndef DRONE_SITL_CONTAINER
define OUTSIDE_HINT
make: this Makefile runs inside the dev container, not on the host.

Open a shell in the container (starts it if needed), then run make there:
    scripts/dev.sh shell
    make $(or $(MAKECMDGOALS),help)

Or run it once from the host:
    scripts/dev.sh exec make $(or $(MAKECMDGOALS),help)

VS Code: "Dev Containers: Reopen in Container", then use its terminal.
endef
$(info $(OUTSIDE_HINT))
$(error not inside the dev container)
endif

WS ?= ros2_ws

# Recipes run in a bash login shell so /etc/profile.d (ROS 2 underlay, mise)
# is sourced even when make is started from a non-login `podman exec`.
SHELL       := /bin/bash
.SHELLFLAGS := -lc

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z0-9_.-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

# --- Build ----------------------------------------------------------------
.PHONY: build
build: ## colcon build the ROS 2 workspace
	cd $(WS) && colcon build --symlink-install

# --- Run ------------------------------------------------------------------
# Targets that run our own packages must also source the workspace overlay,
# which exists only after `make build`. QT_QPA_PLATFORM mirrors compose.yaml
# (X11 first — Gazebo needs it — Wayland fallback) so GUIs work in containers
# started before that setting existed; an explicit value in the environment
# wins.
ROS_ENV = if [ -f $(WS)/install/setup.bash ]; then source $(WS)/install/setup.bash; \
          else echo "make $@: $(WS)/install not found; run \`make build\` first." >&2; exit 1; fi; \
          export QT_QPA_PLATFORM="$${QT_QPA_PLATFORM:-xcb;wayland}";

# Gazebo allows one server per world name, so a second `make sim/run/mission`
# only produces a cryptic "Another world of the same name is running". Refuse
# up front and point at `make stop`.
SIM_GUARD = if ps -eo stat=,comm= | awk '$$1 !~ /^Z/ && $$2 == "gz-sim-main" {f=1} END {exit !f}'; then \
              echo "make $@: a simulator is already running (only one at a time); stop it with \`make stop\`." >&2; exit 1; fi;

# Patterns anchored at the start of the command line so they cannot match the
# shell running this recipe.
LAUNCH_RE = ^/usr/bin/python3 /opt/ros/[^ ]*/bin/ros2 launch
GZ_RE     = ^/opt/ros/[^ ]*/gz-sim-

.PHONY: sim run mission stop
sim: ## Launch Gazebo + PX4 SITL
	$(ROS_ENV) $(SIM_GUARD) ros2 launch drone_bringup sim.launch.py

run: ## Bring up the full ROS 2 stack (sim + perception + estimation)
	$(ROS_ENV) $(SIM_GUARD) ros2 launch drone_bringup bringup.launch.py

mission: ## Run a demo mission (with GNSS-loss scenario)
	$(ROS_ENV) $(SIM_GUARD) ros2 launch drone_mission demo_mission.launch.py

stop: ## Stop a running sim/run/mission
	@pids=$$(pgrep -f "$(LAUNCH_RE)"); n=0; \
	if [ -n "$$pids" ]; then n=1; kill -INT $$pids; \
	  for i in $$(seq 15); do pgrep -f "$(LAUNCH_RE)" >/dev/null || break; sleep 1; done; fi; \
	if pgrep -f "$(GZ_RE)" >/dev/null; then n=1; pkill -TERM -f "$(GZ_RE)"; sleep 1; fi; \
	if pgrep -f "$(GZ_RE)" >/dev/null; then echo "make stop: simulator still running" >&2; exit 1; \
	elif [ $$n = 1 ]; then echo "make stop: simulator stopped."; \
	else echo "make stop: nothing was running."; fi

# --- Quality --------------------------------------------------------------
.PHONY: test fmt lint
test: ## Run Rust + Python + ROS 2 tests
	$(ROS_ENV) cd $(WS) && colcon test && colcon test-result --verbose

fmt: ## Format Rust (cargo fmt) and Python (ruff format)
	cd $(WS) && cargo fmt --all 2>/dev/null; ruff format .

lint: ## Lint Rust (clippy) and Python (ruff)
	cd $(WS) && cargo clippy --all-targets 2>/dev/null; ruff check .

# --- Housekeeping ---------------------------------------------------------
.PHONY: clean
clean: ## Remove ROS 2 / cargo build artifacts
	cd $(WS) && rm -rf build install log && cargo clean 2>/dev/null || true
