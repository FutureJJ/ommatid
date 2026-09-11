#!/usr/bin/env python3
"""Ommatid body agent. Runs inside the `rospider` container on the Raspberry Pi (ROS 2 Humble, Python 3.10).

Every ~100 ms: grab the latest camera frame, shrink it to grey 320x200 JPEG, POST it to the brain with the body's
telemetry, receive the current command and publish it as /controller/cmd_vel. Reflexes the brain cannot override:
  - watchdog: no fresh command for 500 ms → stop
  - LiDAR: anything closer than the stop distance in the front sector → no forward motion
  - battery below the floor → stop
The stock Hiwonder stack does the gait; this only tells it how fast to go and turn.
"""
from __future__ import annotations
import json, math, os, sys, threading, time, urllib.request
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import Twist
from sensor_msgs.msg import Image, Imu, LaserScan
from std_msgs.msg import UInt16

BRAIN_URL = os.environ.get("OMMATID_BRAIN_URL", "https://ommatid.org/body/frame")
TOKEN = os.environ.get("OMMATID_TOKEN", "")
PERIOD_S = float(os.environ.get("OMMATID_PERIOD_S", "0.1"))
WATCHDOG_S = 0.5
OBSTACLE_STOP_M = 0.20
BATTERY_FLOOR_V = 10.3
MAX_LINEAR = 0.08       # m/s, stock clamp is 0.12
MAX_YAW = 0.5           # rad/s, stock clamp is 0.6
DRY_RUN = os.environ.get("OMMATID_DRY_RUN", "1") == "1"   # 1: talk to the brain but publish zero velocity


def clamp(v, lo, hi): return max(lo, min(hi, v))


class Body(Node):
    def __init__(self):
        super().__init__("ommatid_body")
        self.lock = threading.Lock()
        self.rgb = None; self.rgb_ts = 0.0
        self.battery_v = None; self.yaw = None; self.scan_front = None
        self.cmd = None; self.cmd_ts = 0.0
        self.stats = {"frames": 0, "errors": 0, "watchdog_stops": 0, "obstacle_blocks": 0, "last_error": ""}
        self.create_subscription(Image, "/depth_cam/rgb/image_raw", self._on_rgb, qos_profile_sensor_data)
        self.create_subscription(LaserScan, "/scan", self._on_scan, qos_profile_sensor_data)
        self.create_subscription(Imu, "/imu", self._on_imu, qos_profile_sensor_data)
        self.create_subscription(UInt16, "/ros_robot_controller/battery", self._on_batt, 5)
        self.pub_vel = self.create_publisher(Twist, "/controller/cmd_vel", 5)
        self.create_timer(PERIOD_S, self._tick)
        self.create_timer(0.1, self._drive)

    def _on_rgb(self, m): self.rgb, self.rgb_ts = m, time.time()
    def _on_batt(self, m): self.battery_v = m.data / 1000.0
    def _on_imu(self, m):
        q = m.orientation
        self.yaw = math.degrees(math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z)))
    def _on_scan(self, m):
        r = list(m.ranges); n = len(r)
        front = [x for x in r[: n // 8] + r[-n // 8:] if x and 0.05 < x < 12.0]
        self.scan_front = min(front) if front else None

    def _jpeg(self):
        import cv2, numpy as np
        m = self.rgb
        if m is None: return None
        img = np.frombuffer(bytes(m.data), dtype=np.uint8).reshape(m.height, m.width, 3)
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY if m.encoding == "rgb8" else cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (320, 200), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", gray, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        return buf.tobytes() if ok else None

    def _tick(self):
        jpeg = self._jpeg()
        if jpeg is None or time.time() - self.rgb_ts > 1.0:
            return
        tele = {"ts": time.time(), "dry_run": DRY_RUN, "battery_v": self.battery_v, "yaw_deg": self.yaw, "lidar_front_m": self.scan_front,
                "frames": self.stats["frames"], "watchdog_stops": self.stats["watchdog_stops"],
                "obstacle_blocks": self.stats["obstacle_blocks"]}
        req = urllib.request.Request(BRAIN_URL, data=jpeg, method="POST",
                                     headers={"Content-Type": "image/jpeg", "Authorization": f"Bearer {TOKEN}",
                                              "User-Agent": "Ommatid-Body/0.1", "X-Ommatid-Telemetry": json.dumps(tele)})
        try:
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                cmd = json.loads(resp.read())
            with self.lock:
                self.cmd, self.cmd_ts = cmd, time.time()
            self.stats["frames"] += 1
        except Exception as e:
            self.stats["errors"] += 1; self.stats["last_error"] = str(e)[:120]

    def _drive(self):
        with self.lock:
            cmd, ts = self.cmd, self.cmd_ts
        t = Twist()
        if cmd is None or time.time() - ts > WATCHDOG_S:
            if cmd is not None: self.stats["watchdog_stops"] += 1
        elif not cmd.get("stop") and (self.battery_v is None or self.battery_v >= BATTERY_FLOOR_V):
            lin = clamp(float(cmd.get("linear_mps", 0.0)), -MAX_LINEAR, MAX_LINEAR)
            yaw = clamp(float(cmd.get("yaw_rps", 0.0)), -MAX_YAW, MAX_YAW)
            if lin > 0 and self.scan_front is not None and self.scan_front < OBSTACLE_STOP_M:
                lin = 0.0; self.stats["obstacle_blocks"] += 1
            self.stats["would"] = {"linear": round(lin, 3), "yaw": round(yaw, 3)}
            if not DRY_RUN:
                t.linear.x = lin; t.angular.z = yaw
        self.pub_vel.publish(t)


def main():
    rclpy.init()
    node = Body()
    try:
        rclpy.spin(node)
    finally:
        node.pub_vel.publish(Twist()); node.destroy_node(); rclpy.shutdown()


if __name__ == "__main__":
    main()
