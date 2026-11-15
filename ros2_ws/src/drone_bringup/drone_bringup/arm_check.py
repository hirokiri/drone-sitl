"""Check that the simulated vehicle can be armed from ROS 2 (milestone M0).

Usage (with `make sim` running in another shell):
    ros2 run drone_bringup arm_check
    ros2 run drone_bringup arm_check --ros-args -p timeout_s:=120.0

Waits for PX4's preflight checks to pass, sends an arm command over the
uXRCE-DDS bridge, confirms the vehicle reports ARMED, then disarms it again.
Exits 0 on success and 1 on timeout, so it can be used in scripts. This is a
bring-up check only; flying a mission is drone_mission's job.
"""

import sys

import rclpy
from px4_msgs.msg import VehicleCommand, VehicleStatus
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data

# PX4 versions the topics of messages whose definition changed (px4_msgs
# MESSAGE_VERSION): VehicleStatus is at version 1 in the pinned PX4 release.
STATUS_TOPIC = f"/fmu/out/vehicle_status_v{VehicleStatus.MESSAGE_VERSION}"
COMMAND_TOPIC = "/fmu/in/vehicle_command"


class ArmCheck(Node):
    """Arm, confirm, disarm; `result` becomes True/False when finished."""

    def __init__(self) -> None:
        super().__init__("arm_check")
        self.timeout_s = self.declare_parameter("timeout_s", 60.0).value
        self.result: bool | None = None
        self._status: VehicleStatus | None = None
        self._was_armed = False
        self._waiting_for = ""
        self._command_pub = self.create_publisher(VehicleCommand, COMMAND_TOPIC, 10)
        self.create_subscription(
            VehicleStatus, STATUS_TOPIC, self._on_status, qos_profile_sensor_data
        )
        self._deadline = self.get_clock().now().nanoseconds + int(self.timeout_s * 1e9)
        self.create_timer(1.0, self._step)

    def _on_status(self, msg: VehicleStatus) -> None:
        self._status = msg

    def _send_arm(self, arm: bool) -> None:
        msg = VehicleCommand()
        msg.timestamp = self.get_clock().now().nanoseconds // 1000
        msg.command = VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM
        msg.param1 = 1.0 if arm else 0.0
        msg.target_system = self._status.system_id
        msg.target_component = self._status.component_id
        msg.source_system = self._status.system_id
        msg.source_component = self._status.component_id
        msg.from_external = True
        self._command_pub.publish(msg)

    def _wait(self, what: str) -> None:
        if what != self._waiting_for:
            self._waiting_for = what
            self.get_logger().info(f"Waiting for {what}...")

    def _step(self) -> None:
        if self.result is not None:
            return
        if self.get_clock().now().nanoseconds > self._deadline:
            self.get_logger().error(
                f"Timed out after {self.timeout_s:.0f} s waiting for {self._waiting_for}."
            )
            self.result = False
            return

        status = self._status
        if status is None:
            self._wait(f"{STATUS_TOPIC} (is `make sim` running?)")
            return
        armed = status.arming_state == VehicleStatus.ARMING_STATE_ARMED

        if not self._was_armed:
            if armed:
                self._was_armed = True
                self.get_logger().info("Vehicle ARMED. Disarming again.")
                self._send_arm(False)
            elif not status.pre_flight_checks_pass:
                self._wait("PX4 preflight checks to pass")
            else:
                self._wait("the vehicle to arm")
                self._send_arm(True)
        elif armed:
            self._wait("the vehicle to disarm")
            self._send_arm(False)
        else:
            self.get_logger().info("Vehicle DISARMED. Arm check passed.")
            self.result = True


def main() -> None:
    rclpy.init()
    node = ArmCheck()
    try:
        while rclpy.ok() and node.result is None:
            rclpy.spin_once(node, timeout_sec=0.5)
    except KeyboardInterrupt:
        pass
    sys.exit(0 if node.result else 1)


if __name__ == "__main__":
    main()
