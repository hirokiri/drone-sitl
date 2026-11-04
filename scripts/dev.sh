#!/usr/bin/env bash
# Host-side helper for the Drone SITL dev container (defined in compose.yaml).
#
#   scripts/dev.sh up              # build the image and start the container
#   scripts/dev.sh shell           # open a shell in it (starts it if needed)
#   scripts/dev.sh exec CMD [ARG]  # run one command in it, e.g. `exec make build`
#   scripts/dev.sh down            # stop and remove it
#
# Everything else (make build / sim / test / ...) runs inside the container;
# see the Makefile.
#
# GUI: `up` detects the host's X display and its cookie file (on a Wayland
# desktop, the current user's Xwayland) and the Wayland compositor socket, and
# hands them to compose.yaml as DISPLAY, XAUTH_FILE and WAYLAND_SOCKET. Values
# already set in the environment win ($XAUTHORITY counts for XAUTH_FILE).
# Mounts are fixed when the container is created, so after logging into a new
# graphical session (Xwayland gets a new cookie file each login) run
# `scripts/dev.sh down && scripts/dev.sh up`.
#
# Set COMPOSE to use another compose front end (default: "podman compose").
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
read -r -a COMPOSE <<<"${COMPOSE:-podman compose}"
SERVICE=dev

die() {
	echo "dev.sh: $*" >&2
	exit 1
}

usage() {
	sed -n '4,7s/^# \{0,1\}//p' "${BASH_SOURCE[0]}" >&2
	exit 2
}

detect_gui() {
	local runtime=${XDG_RUNTIME_DIR:-/run/user/$(id -u)} sock="" s xdisp xauth

	if [[ -z ${WAYLAND_SOCKET:-} ]]; then
		if [[ -n ${WAYLAND_DISPLAY:-} ]]; then
			if [[ $WAYLAND_DISPLAY == /* ]]; then sock=$WAYLAND_DISPLAY; else sock=$runtime/$WAYLAND_DISPLAY; fi
		else
			for s in "$runtime"/wayland-*; do
				if [[ $s != *.lock ]]; then
					sock=$s
					break
				fi
			done
		fi
		if [[ -S $sock ]]; then WAYLAND_SOCKET=$sock; fi
	fi

	# First Xwayland of this user: its display (":N") and "-auth <file>".
	read -r xdisp xauth < <(pgrep -u "$(id -u)" -a Xwayland 2>/dev/null | awk '
		NR == 1 { d = "-"; a = "-"
		          for (i = 2; i <= NF; i++) { if ($i ~ /^:[0-9]+$/) d = $i; if ($i == "-auth") a = $(i + 1) }
		          print d, a }') || true
	[[ ${xdisp:--} != - ]] || xdisp=""
	[[ ${xauth:--} != - ]] || xauth=""

	DISPLAY=${DISPLAY:-${xdisp:-:0}}
	if [[ -z ${XAUTH_FILE:-} ]]; then
		XAUTH_FILE=${XAUTHORITY:-$xauth}
		if [[ -z $XAUTH_FILE && -f $HOME/.Xauthority ]]; then XAUTH_FILE=$HOME/.Xauthority; fi
	fi
	export DISPLAY XAUTH_FILE WAYLAND_SOCKET=${WAYLAND_SOCKET:-}
	echo "dev.sh: GUI: DISPLAY=$DISPLAY XAUTH_FILE=${XAUTH_FILE:-<none>} WAYLAND_SOCKET=${WAYLAND_SOCKET:-<none>}" >&2
}

is_running() {
	"${COMPOSE[@]}" exec -T "$SERVICE" true >/dev/null 2>&1
}

up() {
	detect_gui
	"${COMPOSE[@]}" build
	"${COMPOSE[@]}" up -d "$SERVICE"
}

ensure_up() {
	if ! is_running; then
		echo "dev.sh: dev container not running; starting it..." >&2
		up
	fi
}

[[ -z ${DRONE_SITL_CONTAINER:-} ]] || die "already inside the dev container; run make directly."

case "${1:-}" in
up) up ;;
down) "${COMPOSE[@]}" down ;;
shell)
	ensure_up
	exec "${COMPOSE[@]}" exec "$SERVICE" bash
	;;
exec)
	shift
	(($#)) || usage
	ensure_up
	# Allocate a TTY only when we have one, so Ctrl-C reaches the processes in
	# the container (podman exec does not forward signals without a TTY) while
	# pipes and CI still work. A login shell sources the ROS 2 environment.
	tty=()
	[[ -t 0 ]] || tty=(-T)
	exec "${COMPOSE[@]}" exec "${tty[@]}" "$SERVICE" bash -lc 'exec "$@"' bash "$@"
	;;
*) usage ;;
esac
