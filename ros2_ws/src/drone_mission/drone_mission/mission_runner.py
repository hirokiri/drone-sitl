"""Fly the scenario's mission plan over PX4 offboard control (milestone M1).

Usage (started by `make mission`, or against a running `make sim`):
    ros2 run drone_mission mission_runner
    ros2 run drone_mission mission_runner --ros-args -p scenario:=/path/to.yaml

arm -> takeoff -> waypoints -> land (FR2). The plan comes from the scenario
file; positions in it are relative to where the vehicle stands when the
mission starts. Exits 0 once the vehicle has landed and disarmed, 1 on
timeout or if PX4 takes control away (failsafe) mid-flight. In that case it
stays until PX4 has brought the vehicle down and disarmed it, so whatever
records the run sees the whole of it.

This node is glue: it only tells PX4 where to go. It streams a position
setpoint that slides along each leg at the plan's cruise speed, and PX4's own
controllers fly the vehicle to it. The position it reads back is PX4's
estimate (EKF2), never simulator ground truth.
"""

import math
import sys
from enum import Enum, auto
from pathlib import Path

import rclpy
from ament_index_python.packages import get_package_share_directory
from drone_scenario.scenario import Ned, load_scenario
from px4_msgs.msg import (
    OffboardControlMode,
    TrajectorySetpoint,
    VehicleCommand,
    VehicleLocalPosition,
    VehicleStatus,
)
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data

# PX4 versions the topics of messages whose definition changed (px4_msgs
# MESSAGE_VERSION).
STATUS_TOPIC = f"/fmu/out/vehicle_status_v{VehicleStatus.MESSAGE_VERSION}"
LOCAL_POSITION_TOPIC = (
    f"/fmu/out/vehicle_local_position_v{VehicleLocalPosition.MESSAGE_VERSION}"
)
OFFBOARD_MODE_TOPIC = "/fmu/in/offboard_control_mode"
SETPOINT_TOPIC = "/fmu/in/trajectory_setpoint"
COMMAND_TOPIC = "/fmu/in/vehicle_command"

# PX4 drops out of offboard mode when setpoints arrive slower than 2 Hz, and
# only accepts the switch into it once they have been streaming for a while.
SETPOINT_RATE_HZ = 20.0
SETPOINT_WARMUP_S = 1.0
# Mode-switch / arm / land commands are repeated at this period until the
# vehicle status confirms them (the bridge is best effort).
COMMAND_PERIOD_S = 1.0
# VEHICLE_CMD_DO_SET_MODE arguments selecting PX4's offboard mode:
# param1 = MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, param2 = PX4_CUSTOM_MAIN_MODE_OFFBOARD.
# Before handing over to PX4's land mode the vehicle must have slowed to this
# speed over the landing point; switching while it still carries cruise speed
# makes it land metres further on.
LAND_SETTLE_SPEED_M_S = 0.3
PX4_CUSTOM_MODE_ENABLED = 1.0
PX4_MAIN_MODE_OFFBOARD = 6.0


def advance_setpoint(setpoint: Ned, target: Ned, step_m: float) -> Ned:
    """Move `setpoint` towards `target` by at most `step_m` metres."""
    delta = [t - s for s, t in zip(setpoint, target, strict=True)]
    distance = math.sqrt(sum(d * d for d in delta))
    if distance <= step_m:
        return target
    scale = step_m / distance
    return tuple(s + d * scale for s, d in zip(setpoint, delta, strict=True))


def distance_m(a: Ned, b: Ned) -> float:
    return math.dist(a, b)


class Phase(Enum):
    WAIT_READY = auto()  # preflight checks + a valid position estimate
    ENGAGE = auto()  # switch to offboard mode and arm
    FLY = auto()  # takeoff, waypoints, back over home
    LAND = auto()  # PX4's land mode, until it disarms itself
    ABORTED = auto()  # PX4 took over (failsafe): watch until it disarms


class MissionRunner(Node):
    """Fly the plan; `result` becomes True/False when finished."""

    def __init__(self) -> None:
        super().__init__("mission_runner")
        default_scenario = (
            Path(get_package_share_directory("drone_mission"))
            / "config"
            / "demo_mission.yaml"
        )
        scenario_path = self.declare_parameter("scenario", str(default_scenario)).value
        self.scenario = load_scenario(scenario_path)
        self.plan = self.scenario.mission
        self.result: bool | None = None

        self._status: VehicleStatus | None = None
        self._position: Ned | None = None
        self._speed_m_s = 0.0
        self._phase = Phase.WAIT_READY
        self._waiting_for = ""
        self._ready_since_ns: int | None = None
        self._last_command_ns = 0
        self._home: Ned = (0.0, 0.0, 0.0)
        self._setpoint: Ned | None = None
        self._legs: tuple[Ned, ...] = ()
        self._leg = 0
        self._abort_reason = ""

        self._offboard_mode_pub = self.create_publisher(
            OffboardControlMode, OFFBOARD_MODE_TOPIC, 10
        )
        self._setpoint_pub = self.create_publisher(
            TrajectorySetpoint, SETPOINT_TOPIC, 10
        )
        self._command_pub = self.create_publisher(VehicleCommand, COMMAND_TOPIC, 10)
        self.create_subscription(
            VehicleStatus, STATUS_TOPIC, self._on_status, qos_profile_sensor_data
        )
        self.create_subscription(
            VehicleLocalPosition,
            LOCAL_POSITION_TOPIC,
            self._on_local_position,
            qos_profile_sensor_data,
        )

        self._start_ns = self._now_ns()
        self._deadline_ns = self._start_ns + int(self.plan.timeout_s * 1e9)
        self.create_timer(1.0 / SETPOINT_RATE_HZ, self._step)
        self.get_logger().info(
            f"Scenario '{self.scenario.name}' from {scenario_path}: "
            f"{len(self.plan.waypoints_ned_m)} waypoints at "
            f"{self.plan.cruise_speed_m_s:g} m/s."
        )

    # --- PX4 -> ROS 2 -----------------------------------------------------
    def _on_status(self, msg: VehicleStatus) -> None:
        self._status = msg

    def _on_local_position(self, msg: VehicleLocalPosition) -> None:
        self._position = (msg.x, msg.y, msg.z) if msg.xy_valid and msg.z_valid else None
        self._speed_m_s = math.hypot(msg.vx, msg.vy, msg.vz)

    # --- ROS 2 -> PX4 -----------------------------------------------------
    def _now_ns(self) -> int:
        return self.get_clock().now().nanoseconds

    def _publish_setpoint(self) -> None:
        timestamp = self._now_ns() // 1000
        mode = OffboardControlMode()
        mode.timestamp = timestamp
        mode.position = True
        self._offboard_mode_pub.publish(mode)

        setpoint = TrajectorySetpoint()
        setpoint.timestamp = timestamp
        setpoint.position = [float(v) for v in self._setpoint]
        # NaN = not commanded: PX4 derives velocity/acceleration itself and
        # keeps the current heading.
        setpoint.velocity = [math.nan] * 3
        setpoint.acceleration = [math.nan] * 3
        setpoint.jerk = [math.nan] * 3
        setpoint.yaw = math.nan
        setpoint.yawspeed = math.nan
        self._setpoint_pub.publish(setpoint)

    def _send_command(self, command: int, param1: float = 0.0, param2: float = 0.0):
        msg = VehicleCommand()
        msg.timestamp = self._now_ns() // 1000
        msg.command = command
        msg.param1 = param1
        msg.param2 = param2
        msg.target_system = self._status.system_id
        msg.target_component = self._status.component_id
        msg.source_system = self._status.system_id
        msg.source_component = self._status.component_id
        msg.from_external = True
        self._command_pub.publish(msg)

    def _command_due(self) -> bool:
        """Rate-limit repeated commands to one per COMMAND_PERIOD_S."""
        now = self._now_ns()
        if now - self._last_command_ns < COMMAND_PERIOD_S * 1e9:
            return False
        self._last_command_ns = now
        return True

    # --- State machine ----------------------------------------------------
    def _wait(self, what: str) -> None:
        if what != self._waiting_for:
            self._waiting_for = what
            self.get_logger().info(f"Waiting for {what}...")

    def _fail(self, reason: str) -> None:
        self.get_logger().error(f"Mission failed: {reason}")
        self.result = False

    def _abort(self, reason: str) -> None:
        """PX4 has taken control away: stop commanding, keep watching."""
        self.get_logger().error(
            f"Mission aborted {self._flight_time_s():.0f} s into the run: {reason}"
        )
        self._abort_reason = reason
        self._phase = Phase.ABORTED

    def _flight_time_s(self) -> float:
        return (self._now_ns() - self._start_ns) / 1e9

    def _step(self) -> None:
        if self.result is not None:
            return
        if self._now_ns() > self._deadline_ns:
            self._fail(
                f"timed out after {self.plan.timeout_s:.0f} s waiting for "
                f"{self._waiting_for}."
            )
            return

        status, position = self._status, self._position
        if status is None:
            self._wait(f"{STATUS_TOPIC} (is the simulator running?)")
            return
        armed = status.arming_state == VehicleStatus.ARMING_STATE_ARMED
        offboard = status.nav_state == VehicleStatus.NAVIGATION_STATE_OFFBOARD

        if self._phase is Phase.ABORTED:
            # No setpoints: PX4's failsafe is flying. The run is over once it
            # has put the vehicle down.
            self._wait("PX4's failsafe to land and disarm the vehicle")
            if not armed:
                self._fail(f"{self._abort_reason} The vehicle is down and disarmed.")
            return
        if position is None:
            if self._phase in (Phase.FLY, Phase.LAND):
                # Without a position there is nothing left to navigate by.
                self._abort("PX4 lost its position estimate in flight.")
            else:
                self._wait("a valid local position estimate")
            return

        if self._phase is Phase.WAIT_READY:
            # Hold the setpoint on the vehicle while PX4 gets ready.
            self._setpoint = position
            self._publish_setpoint()
            if not status.pre_flight_checks_pass:
                self._ready_since_ns = None
                self._wait("PX4 preflight checks to pass")
            elif self._ready_since_ns is None:
                self._ready_since_ns = self._now_ns()
            elif self._now_ns() - self._ready_since_ns >= SETPOINT_WARMUP_S * 1e9:
                self._home = position
                self._legs = tuple(
                    tuple(h + v for h, v in zip(self._home, leg, strict=True))
                    for leg in self.plan.legs()
                )
                self._phase = Phase.ENGAGE

        elif self._phase is Phase.ENGAGE:
            self._publish_setpoint()
            if armed and offboard:
                self.get_logger().info(
                    f"Armed in offboard mode. Taking off to "
                    f"{self.plan.takeoff_altitude_m:g} m."
                )
                self._phase = Phase.FLY
            elif self._command_due():
                self._wait("offboard mode and arming")
                if not offboard:
                    self._send_command(
                        VehicleCommand.VEHICLE_CMD_DO_SET_MODE,
                        PX4_CUSTOM_MODE_ENABLED,
                        PX4_MAIN_MODE_OFFBOARD,
                    )
                if not armed:
                    self._send_command(
                        VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, 1.0
                    )

        elif self._phase is Phase.FLY:
            if not (armed and offboard):
                self._abort(
                    "PX4 left offboard mode or disarmed in flight "
                    f"(nav_state={status.nav_state}, failsafe={status.failsafe})."
                )
                return
            target = self._legs[self._leg]
            self._setpoint = advance_setpoint(
                self._setpoint, target, self.plan.cruise_speed_m_s / SETPOINT_RATE_HZ
            )
            self._publish_setpoint()
            self._wait(f"leg {self._leg + 1}/{len(self._legs)}")
            last = self._leg == len(self._legs) - 1
            if distance_m(position, target) <= self.plan.acceptance_radius_m and (
                not last or self._speed_m_s <= LAND_SETTLE_SPEED_M_S
            ):
                relative = [t - h for t, h in zip(target, self._home, strict=True)]
                self.get_logger().info(
                    f"Reached leg {self._leg + 1}/{len(self._legs)} "
                    f"(N {relative[0]:.1f}, E {relative[1]:.1f}, "
                    f"D {relative[2]:.1f} m from home)."
                )
                self._leg += 1
                if last:
                    self.get_logger().info("Plan flown. Landing.")
                    self._phase = Phase.LAND

        elif self._phase is Phase.LAND:
            # Keep the stream alive only until PX4 has switched to its land
            # mode. The bridge writes our setpoints straight onto the uORB
            # topic PX4's own flight modes use to command the position
            # controller, so streaming on would fight the landing: the vehicle
            # touches down but keeps trying to climb back and never disarms.
            if offboard:
                self._publish_setpoint()
            if not armed:
                elapsed_s = (self._now_ns() - self._start_ns) / 1e9
                home_error_m = math.dist(position[:2], self._home[:2])
                self.get_logger().info(
                    f"Landed and disarmed {home_error_m:.2f} m from home after "
                    f"{elapsed_s:.0f} s. Mission complete."
                )
                self.result = True
            elif status.nav_state != VehicleStatus.NAVIGATION_STATE_AUTO_LAND:
                self._wait("PX4 to enter land mode")
                if self._command_due():
                    self._send_command(VehicleCommand.VEHICLE_CMD_NAV_LAND)
            else:
                self._wait("touchdown and auto-disarm")


def main() -> None:
    rclpy.init()
    node = MissionRunner()
    try:
        while rclpy.ok() and node.result is None:
            rclpy.spin_once(node, timeout_sec=0.5)
    except KeyboardInterrupt:
        pass
    sys.exit(0 if node.result else 1)


if __name__ == "__main__":
    main()
