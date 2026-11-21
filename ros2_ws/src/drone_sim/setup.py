from pathlib import Path

from setuptools import find_packages, setup

package_name = "drone_sim"


def asset_files(root: str) -> list[tuple[str, list[str]]]:
    """Install every file under `root`, keeping the directory structure."""
    by_dir: dict[str, list[str]] = {}
    for path in sorted(Path(root).rglob("*")):
        if path.is_file() and path.name != ".gitkeep":
            by_dir.setdefault(str(path.parent), []).append(str(path))
    return [(f"share/{package_name}/{d}", files) for d, files in by_dir.items()]


setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        *asset_files("models"),
        *asset_files("worlds"),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="hirokiri",
    maintainer_email="koromo.tani.e@gmail.com",
    description="Gazebo models and worlds for the Drone SITL stack.",
    license="Apache-2.0",
    extras_require={"test": ["pytest"]},
)
