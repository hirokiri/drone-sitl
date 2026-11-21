"""Carry the simulated GNSS receiver's output to PX4, with scenario faults.

Usage (started by drone_bringup's sim.launch.py):
    ros2 run gnss_injector gnss_injector --ros-args \\
        -p world:=default -p model:=x500_sitl_0 -p scenario:=/path/to.yaml

The vehicle model publishes its NavSat sensor on a tap topic instead of the
one PX4's Gazebo bridge listens on. This node sits on that wire: it forwards
every message to PX4 while GNSS is healthy, forwards nothing during a
`dropout`, and adds a position error during a `degrade` (FR3). Without a
scenario it only forwards.

The schedule counts seconds after takeoff on the simulation clock (the
receiver's own message stamps), so a run is reproducible whatever the
real-time factor.

What it is doing is published on /gnss_injector/mode (std_msgs/String:
healthy | dropout | degrade), latched, so it can be recorded with the rest.
"""

import threading

import rclpy
from drone_scenario.scenario import load_scenario
from gz.msgs.navsat_pb2 import NavSat
from gz.transport import Node as GzNode
from px4_msgs.msg import VehicleLandDetected
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from std_msgs.msg import String

from gnss_injector.loss_model import GnssMode, PositionError, mode_at, offset_position

# The Gazebo topic the vehicle model's NavSat sensor publishes on (see
# drone_sim/models/x500_sitl) ...
RAW_TOPIC = "/navsat_raw"
# ... and the one PX4's gz_bridge subscribes to.
PX4_TOPIC = "/world/{world}/model/{model}/link/base_link/sensor/navsat_sensor/navsat"
LAND_DETECTED_TOPIC = "/fmu/out/vehicle_land_detected"
MODE_TOPIC = "/gnss_injector/mode"
MODE_PERIOD_S = 0.1


def stamp_s(msg: NavSat) -> float:
    return msg.header.stamp.sec + msg.header.stamp.nsec * 1e-9


class GnssInjector(Node):
    def __init__(self) -> None:
        super().__init__("gnss_injector")
        scenario_path = self.declare_parameter("scenario", "").value
        world = self.declare_parameter("world", "default").value
        model = self.declare_parameter("model", "x500_sitl_0").value

        self._loss = None
        self._error: PositionError | None = None
        if scenario_path:
            scenario = load_scenario(scenario_path)
            self._loss = scenario.gnss_loss
            self._error = PositionError(self._loss.degrade, scenario.seed)

        # Shared between the Gazebo transport thread (_on_navsat) and the ROS
        # executor (_on_status, _publish_mode).
        self._lock = threading.Lock()
        self._sim_time_s: float | None = None
        self._takeoff_sim_time_s: float | None = None
        self._mode = GnssMode.HEALTHY
        self._announced: GnssMode | None = None

        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self._mode_pub = self.create_publisher(String, MODE_TOPIC, latched)
        self.create_subscription(
            VehicleLandDetected,
            LAND_DETECTED_TOPIC,
            self._on_land_detected,
            qos_profile_sensor_data,
        )
        self.create_timer(MODE_PERIOD_S, self._publish_mode)

        self._gz = GzNode()
        px4_topic = PX4_TOPIC.format(world=world, model=model)
        self._px4_pub = self._gz.advertise(px4_topic, NavSat)
        if not self._gz.subscribe(NavSat, RAW_TOPIC, self._on_navsat):
            raise RuntimeError(f"cannot subscribe to Gazebo topic {RAW_TOPIC}")

        if self._loss is not None and self._loss.enabled:
            plan = (
                f"{self._loss.mode} from {self._loss.start_s:g} s to "
                f"{self._loss.end_s:g} s after takeoff"
            )
        else:
            plan = "no loss scheduled"
        self.get_logger().info(f"Relaying {RAW_TOPIC} -> {px4_topic}; {plan}.")

    # --- PX4 -> ROS 2: when did the vehicle take off? ----------------------
    def _on_land_detected(self, msg: VehicleLandDetected) -> None:
        """Takeoff is the moment PX4's land detector lets go of the ground.

        It is placed on the simulation clock by the stamp of the latest
        receiver message, the clock the schedule runs on.
        """
        with self._lock:
            if msg.landed:
                self._takeoff_sim_time_s = None
            elif self._takeoff_sim_time_s is None:
                self._takeoff_sim_time_s = self._sim_time_s

    # --- Gazebo -> PX4: the receiver's wire --------------------------------
    def _on_navsat(self, msg: NavSat) -> None:
        now_s = stamp_s(msg)
        with self._lock:
            dt_s = 0.0 if self._sim_time_s is None else now_s - self._sim_time_s
            self._sim_time_s = now_s
            flight_time_s = (
                None
                if self._takeoff_sim_time_s is None
                else now_s - self._takeoff_sim_time_s
            )
            previous, self._mode = self._mode, mode_at(self._loss, flight_time_s)
            mode = self._mode

        if mode is GnssMode.DROPOUT:
            return
        if mode is GnssMode.DEGRADE:
            if previous is not GnssMode.DEGRADE:
                self._error.reset()
            north_m, east_m = self._error.step(dt_s)
            msg.latitude_deg, msg.longitude_deg = offset_position(
                msg.latitude_deg, msg.longitude_deg, north_m, east_m
            )
        self._px4_pub.publish(msg)

    # --- ROS 2: say what is being done -------------------------------------
    def _publish_mode(self) -> None:
        with self._lock:
            mode = self._mode
        if mode is self._announced:
            return
        if self._announced is not None:
            self.get_logger().info(f"GNSS is now {mode.value}.")
        self._announced = mode
        self._mode_pub.publish(String(data=mode.value))


def main() -> None:
    rclpy.init()
    node = GnssInjector()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass


if __name__ == "__main__":
    main()
