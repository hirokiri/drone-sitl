from setuptools import find_packages, setup

package_name = "drone_eval"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="hirokiri",
    maintainer_email="koromo.tani.e@gmail.com",
    description="Logging, metrics and plots for the Drone SITL stack.",
    license="Apache-2.0",
    extras_require={"test": ["pytest"]},
    entry_points={
        "console_scripts": [
            "flight_recorder = drone_eval.flight_recorder:main",
            "report = drone_eval.report:main",
        ],
    },
)
