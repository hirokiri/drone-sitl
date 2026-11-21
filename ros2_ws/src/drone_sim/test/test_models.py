"""The vehicle model keeps the wiring the rest of the stack relies on."""

import xml.etree.ElementTree as ET
from pathlib import Path

MODELS = Path(__file__).resolve().parents[1] / "models"


def _model(name: str) -> ET.Element:
    return ET.parse(MODELS / name / "model.sdf").getroot().find("model")


def test_every_model_has_a_config():
    for sdf in MODELS.glob("*/model.sdf"):
        assert (sdf.parent / "model.config").is_file(), sdf.parent.name


def test_gnss_is_tapped_not_wired_to_px4():
    sdf = (MODELS / "x500_sitl" / "model.sdf").read_text()
    root = ET.fromstring(sdf.replace("experimental:", "experimental_"))
    sensor = root.find(".//sensor[@name='navsat_sensor']")
    assert sensor.get("action") == "replace"
    assert sensor.findtext("topic") == "navsat_raw"


def test_ground_truth_stays_off_the_topics_px4_reads():
    plugin = _model("x500_sitl").find("plugin")
    for tag in ("odom_topic", "odom_covariance_topic", "tf_topic"):
        assert plugin.findtext(tag).startswith("/sim/ground_truth/"), tag
