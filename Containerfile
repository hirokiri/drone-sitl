FROM docker.io/osrf/ros:jazzy-desktop

# Install basic requirements
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y \
    curl wget git sudo nano bash-completion \
    software-properties-common lsb-release \
    python3-pip python3-venv x11-apps mesa-utils \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Add Gazebo Harmonic repository
RUN curl -sSL https://packages.osrfoundation.org/gazebo.gpg --output /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable $(lsb_release -cs) main" | tee /etc/apt/sources.list.d/gazebo-stable.list > /dev/null

RUN apt-get update && apt-get install -y \
    gz-harmonic ros-jazzy-ros-gz ros-jazzy-actuator-msgs \
    && rm -rf /var/lib/apt/lists/*

# Setup user
ARG USERNAME=hirokiri
ARG USER_UID=1000
ARG USER_GID=1000

RUN if ! getent group $USER_GID; then groupadd --gid $USER_GID $USERNAME; else groupmod -n $USERNAME $(getent group $USER_GID | cut -d: -f1); fi \
    && if ! getent passwd $USER_UID; then useradd --uid $USER_UID --gid $USER_GID -m $USERNAME -s /bin/bash; else usermod -l $USERNAME -g $USER_GID -u $USER_UID -m -d /home/$USERNAME $(getent passwd $USER_UID | cut -d: -f1); fi \
    && echo "$USERNAME ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME \
    && chown -R $USER_UID:$USER_GID /home/$USERNAME

# Switch to standard user
USER $USERNAME
WORKDIR /home/$USERNAME/work/drone-sitl

# Ensure ROS 2 workspace is sourced
RUN echo "source /opt/ros/jazzy/setup.bash" >> /home/$USERNAME/.bashrc

CMD ["/bin/bash"]
