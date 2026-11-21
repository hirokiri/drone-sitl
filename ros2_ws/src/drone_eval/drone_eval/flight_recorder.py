"""Record PX4's position estimate next to simulator ground truth (FR7).

Usage (started by drone_mission's demo_mission.launch.py):
    ros2 run drone_eval flight_recorder --ros-args -p run_dir:=runs/demo

Writes `<run_dir>/flight.csv`, one row every 0.1 s of PX4 time, holding the
ground-truth position, PX4's estimate, and what the GNSS injector was doing.
`ros2 run drone_eval report <run_dir>` turns it into metrics and a plot.

Ground truth is read here and nowhere else in the stack: it is for evaluation
only and never reaches the estimator or the controller.
"""

import math
from pathlib import Path

import rclpy
from nav_msgs.msg import Odometry
from px4_msgs.msg import VehicleLandDetected, VehicleLocalPosition, VehicleStatus
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from std_msgs.msg import String

from drone_eval.flight_log import LogWriter, Sample, enu_to_ned

GROUND_TRUTH_TOPIC = "/sim/ground_truth/odometry"
STATUS_TOPIC = f"/fmu/out/vehicle_status_v{VehicleStatus.MESSAGE_VERSION}"
LOCAL_POSITION_TOPIC = (
    f"/fmu/out/vehicle_local_position_v{VehicleLocalPosition.MESSAGE_VERSION}"
)
LAND_DETECTED_TOPIC = "/fmu/out/vehicle_land_detected"
GNSS_MODE_TOPIC = "/gnss_injector/mode"
SAMPLE_PERIOD_S = 0.1


class FlightRecorder(Node):
    def __init__(self) -> None:
        super().__init__("flight_recorder")
        run_dir = Path(self.declare_parameter("run_dir", "runs/latest").value)
        self._writer = LogWriter(run_dir.resolve())

        self._truth: tuple[float, float, float] | None = None
        self._status: VehicleStatus | None = None
        self._gnss_mode = "healthy"
        # PX4 time at which the land detector reported takeoff; None on the
        # ground.
        self._takeoff_us: int | None = None
        self._first_us: int | None = None
        self._last_us = 0

        self.create_subscription(
            Odometry, GROUND_TRUTH_TOPIC, self._on_truth, qos_profile_sensor_data
        )
        self.create_subscription(
            VehicleStatus, STATUS_TOPIC, self._on_status, qos_profile_sensor_data
        )
        self.create_subscription(
            VehicleLocalPosition,
            LOCAL_POSITION_TOPIC,
            self._on_local_position,
            qos_profile_sensor_data,
        )
        self.create_subscription(
            VehicleLandDetected,
            LAND_DETECTED_TOPIC,
            self._on_land_detected,
            qos_profile_sensor_data,
        )
        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.create_subscription(String, GNSS_MODE_TOPIC, self._on_gnss_mode, latched)
        self.get_logger().info(f"Recording to {self._writer.path}")

    def _on_truth(self, msg: Odometry) -> None:
        p = msg.pose.pose.position
        self._truth = enu_to_ned(p.x, p.y, p.z)

    def _on_status(self, msg: VehicleStatus) -> None:
        self._status = msg

    def _on_land_detected(self, msg: VehicleLandDetected) -> None:
        if msg.landed:
            self._takeoff_us = None
        elif self._takeoff_us is None:
            self._takeoff_us = msg.timestamp

    def _on_gnss_mode(self, msg: String) -> None:
        self._gnss_mode = msg.data

    def _on_local_position(self, msg: VehicleLocalPosition) -> None:
        """Each estimate from PX4 is a candidate sample; keep one per period."""
        status, truth = self._status, self._truth
        if status is None or truth is None:
            return
        if self._first_us is None:
            self._first_us = msg.timestamp
        elif msg.timestamp - self._last_us < SAMPLE_PERIOD_S * 1e6:
            return
        self._last_us = msg.timestamp

        armed = status.arming_state == VehicleStatus.ARMING_STATE_ARMED
        self._writer.write(
            Sample(
                time_s=(msg.timestamp - self._first_us) * 1e-6,
                flight_time_s=math.nan
                if self._takeoff_us is None
                else (msg.timestamp - self._takeoff_us) * 1e-6,
                truth_n=truth[0],
                truth_e=truth[1],
                truth_d=truth[2],
                est_n=msg.x,
                est_e=msg.y,
                est_d=msg.z,
                est_xy_valid=int(msg.xy_valid),
                est_eph=msg.eph,
                gnss_mode=self._gnss_mode,
                nav_state=status.nav_state,
                armed=int(armed),
            )
        )

    def close(self) -> None:
        self._writer.close()


def main() -> None:
    rclpy.init()
    node = FlightRecorder()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        node.close()


if __name__ == "__main__":
    main()
