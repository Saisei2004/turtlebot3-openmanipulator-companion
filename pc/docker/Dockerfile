# PC 側のサーバー（操作画面 + rosbridge + ドライバ + MuJoCo）を、ROS 2 Humble 入りのコンテナで動かす。
# Linux のホストだけで使える（--network host が要る。Windows / macOS の Docker Desktop では、DDS のマルチキャストと UDP が
# 機体に届かないので、WSL2 の Ubuntu に setup_pc.sh で入れる）。
# 状態: 未ビルド（この Dockerfile は書いただけ。docs/01-quickstart-new-pc.md の「Docker」を参照）
FROM ros:humble-ros-base
RUN apt-get update && apt-get install -y --no-install-recommends \
      ros-humble-rosbridge-server ros-humble-teleop-twist-keyboard ros-humble-control-msgs ros-humble-trajectory-msgs \
      ros-humble-rmw-cyclonedds-cpp python3-pip python3-numpy python3-yaml iproute2 libc-bin \
    && pip3 install --no-cache-dir mujoco \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/tb3-companion
COPY pc/ pc/
COPY config/ config/
# 設定は /opt/tb3-companion/config/tb3.env をボリュームで差し替える（docker-compose.yml 参照）
ENV TB3_DATA_DIR=/data
VOLUME /data
CMD ["bash", "pc/scripts/start_server.sh"]
