.PHONY: help install-deps build start shell run reboot stop clean setup-workspace px4-sitl ardupilot-sitl dds-agent foxglove-bridge

# --in-pod 0: disable automatic pod creation, which conflicts with userns_mode: keep-id
COMPOSE := podman-compose --in-pod 0

# Default target
help:
	@echo "Available commands:"
	@echo "  make install-deps    - Install host dependencies for podman and compose"
	@echo "  make build           - Build the SITL container"
	@echo "  make start           - Start the SITL container in the background"
	@echo "  make shell           - Attach an interactive shell to the running container"
	@echo "  make run             - Enable X11 access, build, start, and attach to the container"
	@echo "  make reboot          - Restart the container (runs ./run.sh --reboot)"
	@echo "  make stop            - Stop the running SITL container"
	@echo "  make clean           - Stop the container and remove the image/volumes"
	@echo "  make setup-workspace - Clone and configure PX4 and ArduPilot"
	@echo "  make px4-sitl        - Build and launch PX4 Gazebo SITL"
	@echo "  make ardupilot-sitl  - Build and launch ArduPilot Gazebo SITL"
	@echo "  make foxglove-bridge - Launch Foxglove Bridge (WebSocket on port 8765)"

install-deps:
	./scripts/install_host_deps.sh

build:
	$(COMPOSE) build

start:
	@podman rm -f drone_sitl_dev 2>/dev/null || true
	$(COMPOSE) up -d --build

shell:
	podman exec -it drone_sitl_dev /bin/bash

run:
	./run.sh $(ARGS)

reboot:
	$(MAKE) run ARGS="--reboot"

stop:
	$(COMPOSE) down

clean:
	$(COMPOSE) down -v
	podman rmi drone-sitl-jazzy || true

setup-workspace:
	@if command -v podman >/dev/null 2>&1; then \
		echo "Running via Podman exec..."; \
		podman exec -it drone_sitl_dev /bin/bash -c "./scripts/setup_workspace.sh"; \
	else \
		./scripts/setup_workspace.sh; \
	fi

dds-agent:
	@if command -v podman >/dev/null 2>&1; then \
		echo "Running via Podman exec..."; \
		podman exec -it drone_sitl_dev /bin/bash -c "MicroXRCEAgent udp4 -p 8888"; \
	else \
		MicroXRCEAgent udp4 -p 8888; \
	fi

px4-sitl:
	@if command -v podman >/dev/null 2>&1; then \
		echo "Running via Podman exec..."; \
		podman exec -it drone_sitl_dev /bin/bash -c "cd PX4-Autopilot && make px4_sitl gz_x500"; \
	else \
		cd PX4-Autopilot && make px4_sitl gz_x500; \
	fi

ardupilot-sitl:
	@if command -v podman >/dev/null 2>&1; then \
		echo "Running via Podman exec..."; \
		podman exec -it drone_sitl_dev /bin/bash -c "cd ardupilot/ArduCopter && sim_vehicle.py -v ArduCopter -f gazebo-iris --console"; \
	else \
		cd ardupilot/ArduCopter && sim_vehicle.py -v ArduCopter -f gazebo-iris --console; \
	fi
foxglove-bridge:
	@if command -v podman >/dev/null 2>&1; then \
		echo "Running via Podman exec..."; \
		podman exec -it drone_sitl_dev /bin/bash -c "source /opt/ros/jazzy/setup.bash && ros2 launch foxglove_bridge foxglove_bridge_launch.xml port:=8765"; \
	else \
		ros2 launch foxglove_bridge foxglove_bridge_launch.xml port:=8765; \
	fi
