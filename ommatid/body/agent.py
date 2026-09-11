#!/usr/bin/env python3
"""Ommatid body agent. Runs inside the `rospider` container on the Raspberry Pi (ROS 2 Humble, Python 3.10).

A sender thread posts the latest camera frame (grey 320x200 JPEG) to the brain about 10 times a second, with the
body's telemetry and the frame's capture time, and receives the brain's current command. The ROS side never waits
on the network: sensor callbacks, the drive timer and the watchdog run on their own.

Reflexes the brain cannot override:
  - lease: motion is allowed only while commands keep arriving with an ADVANCING brain step; if no newer step has
    arrived for LEASE_S the body halts (a stalled brain that still answers HTTP cannot keep an old command alive)
  - LiDAR: anything closer than OBSTACLE_STOP_M within ±FRONT_HALF_ANGLE of straight ahead blocks forward motion;
    the sector is selected by scan angle, not by array position
  - battery below the floor → no motion
  - sensor freshness: no LiDAR scan for 1 s → no forward motion
The stock Hiwonder stack does the gait; this only tells it how fast to go and turn. A zero Twist is NOT a stop for
that stack (it steps in place), so idling publishes nothing and stopping sends an explicit Traveling gait=0.
"""
from __future__ import annotations
import json, math, os, threading, time, http.client, ssl
from urllib.parse import urlsplit
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import Twist
from sensor_msgs.msg import Image, Imu, LaserScan
from std_msgs.msg import UInt16
from kinematics_msgs.msg import Traveling
from servo_controller_msgs.msg import ServoPosition, ServosPosition, ServoStateList

BRAIN_URL = os.environ.get("OMMATID_BRAIN_URL", "https://ommatid.org/body/frame")
TOKEN = os.environ.get("OMMATID_TOKEN", "")
PERIOD_S = float(os.environ.get("OMMATID_PERIOD_S", "0.1"))
SENDERS = int(os.environ.get("OMMATID_SENDERS", "3"))       # parallel connections: the Wi-Fi round trip (~200 ms) exceeds the frame period
LEASE_S = 0.5                 # motion lease: newest advancing command must be younger than this
SCAN_FRESH_S = 1.0
OBSTACLE_STOP_M = 0.20
FRONT_HALF_ANGLE = math.radians(22.5)
FRONT_ANGLE_OFFSET = float(os.environ.get("OMMATID_LIDAR_FRONT_RAD", "0.0"))   # angle (rad) of straight-ahead in the scan frame
BATTERY_FLOOR_V = float(os.environ.get("OMMATID_BATTERY_FLOOR", "9.6"))   # 3S LiPo: 3.2 V/cell; below 3.0 V/cell cells are damaged
MAX_LINEAR = 0.08             # m/s, stock clamp is 0.12
MAX_YAW = 0.5                 # rad/s, stock clamp is 0.6
DRY_RUN = os.environ.get("OMMATID_DRY_RUN", "1") == "1"      # 1: talk to the brain but never move
CAM_TILT = float(os.environ.get("OMMATID_CAM_TILT", "275"))  # servo 22 pulse; 150 = floor, 275 ≈ 30° up = room
PHASE2 = os.environ.get("OMMATID_PHASE", "1") == "2"         # apply per-servo leg targets from the brain (nerve cord → legs)
STAND = os.environ.get("OMMATID_STAND", "0") == "1"          # robot on a stand: legs free, gait engine never used
MAX_PULSE_STEP = int(os.environ.get("OMMATID_MAX_PULSE_STEP", "40"))   # per 100 ms, ≈ 10°: joint rate limit
LEG_IDS = set(range(1, 19))


def clamp(v, lo, hi): return max(lo, min(hi, v))


class Body(Node):
    def __init__(self):
        super().__init__("ommatid_body")
        self.lock = threading.Lock()
        self.started = time.time()
        self.rgb = None; self.rgb_ts = 0.0; self.rgb_stamp = 0.0
        self.battery_v = None; self.yaw = None
        self.scan_front = None; self.scan_ts = 0.0; self.scan_meta = None
        self.cmd = None; self.cmd_recv_ts = 0.0; self.last_step = -1; self.lease_ts = 0.0
        self.stats = {"frames": 0, "errors": 0, "lease_stops": 0, "obstacle_blocks": 0, "stale_cmds": 0, "last_error": ""}
        self.create_subscription(Image, "/depth_cam/rgb/image_raw", self._on_rgb, qos_profile_sensor_data)
        self.create_subscription(LaserScan, "/scan", self._on_scan, qos_profile_sensor_data)
        self.create_subscription(Imu, "/imu", self._on_imu, qos_profile_sensor_data)
        self.create_subscription(UInt16, "/ros_robot_controller/battery", self._on_batt, 5)
        self.create_subscription(ServoStateList, "/controller_manager/servo_states", self._on_servos, 5)
        self.servos = {}; self.servo_ts = 0.0; self.omega = (0.0, 0.0, 0.0); self.leg_targets = {}
        self.pub_vel = self.create_publisher(Twist, "/controller/cmd_vel", 5)
        self.pub_travel = self.create_publisher(Traveling, "/controller/traveling", 5)
        self.pub_servo = self.create_publisher(ServosPosition, "/servo_controller", 5)
        self.moving = False
        self.frame_lock = threading.Lock()    # sender threads take turns so frames leave PERIOD_S apart
        self._halt()
        self._cam_timer = self.create_timer(2.0, self._aim_camera_once)
        self.create_timer(0.1, self._drive)
        self.last_cam_relaunch = 0.0
        self.create_timer(5.0, self._camera_watchdog)
        self.next_send = time.time()
        for i in range(SENDERS):
            threading.Thread(target=self._sender, name=f"brain-sender-{i}", daemon=True).start()

    # ---- sensors ----------------------------------------------------------------
    def _on_rgb(self, m):
        self.rgb, self.rgb_ts = m, time.time()
        self.rgb_stamp = m.header.stamp.sec + m.header.stamp.nanosec * 1e-9
    def _on_batt(self, m): self.battery_v = m.data / 1000.0
    def _on_imu(self, m):
        q = m.orientation
        self.yaw = math.degrees(math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z)))
        w = m.angular_velocity; self.omega = (math.degrees(w.x), math.degrees(w.y), math.degrees(w.z))
    def _on_servos(self, m):
        self.servos = {s.id: int(s.position) for s in m.servo_state if s.id in LEG_IDS}; self.servo_ts = time.time()
    def _on_scan(self, m):
        """Front sector by angle: beams whose angle (relative to the configured straight-ahead) is within ±22.5°."""
        n = len(m.ranges)
        front = []
        for i, r in enumerate(m.ranges):
            if not (r and 0.05 < r < 12.0): continue
            a = m.angle_min + i * m.angle_increment - FRONT_ANGLE_OFFSET
            a = (a + math.pi) % (2 * math.pi) - math.pi
            if abs(a) <= FRONT_HALF_ANGLE: front.append(r)
        self.scan_front = min(front) if front else None
        self.scan_ts = time.time()
        self.scan_meta = {"angle_min": round(m.angle_min, 3), "angle_max": round(m.angle_max, 3), "n": n, "front_beams": len(front)}

    def _aim_camera_once(self):
        self._aim_camera(); self.destroy_timer(self._cam_timer)
        self.create_timer(30.0, self._aim_camera)      # and re-assert every 30 s in case the stock stack moved the arm

    def _camera_watchdog(self):
        """The Aurora 930 occasionally drops off USB and its ROS driver dies with it. If no image has arrived for 20 s,
        relaunch the stock depth-camera launch file (at most once every 2 minutes)."""
        import subprocess
        now = time.time()
        if (self.rgb_ts and now - self.rgb_ts < 20.0) or (not self.rgb_ts and now - self.started < 60.0):
            return
        if now - self.last_cam_relaunch < 120.0:
            return
        self.last_cam_relaunch = now; self.stats["cam_relaunches"] = self.stats.get("cam_relaunches", 0) + 1
        subprocess.Popen(["/bin/zsh", "-c", "pkill -f aurora930_node; sleep 2; source ~/.zshrc >/dev/null 2>&1; "
                          "exec ros2 launch peripherals depth_camera.launch.py >> /tmp/depth_cam_relaunch.log 2>&1"],
                         cwd=os.path.expanduser("~"))

    def _aim_camera(self):
        m = ServosPosition(); m.duration = 1.0; m.position_unit = "pulse"
        m.position = [ServoPosition(id=22, position=float(clamp(CAM_TILT, 0, 1000)))]
        self.pub_servo.publish(m); self.stats["cam_tilt"] = CAM_TILT

    # ---- brain link (own thread) -----------------------------------------------
    def _jpeg(self):
        import cv2, numpy as np
        m = self.rgb
        if m is None: return None
        img = np.frombuffer(bytes(m.data), dtype=np.uint8).reshape(m.height, m.width, 3)
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY if m.encoding == "rgb8" else cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (320, 200), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", gray, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        return buf.tobytes() if ok else None

    def _sender(self):
        """Each sender owns one persistent connection; a shared schedule spaces departures PERIOD_S apart, so with
        SENDERS connections frames keep flowing at the period even when one round trip takes longer than it."""
        conn = [None]
        while rclpy.ok():
            with self.frame_lock:
                wait = self.next_send - time.time()
                self.next_send = max(self.next_send, time.time()) + PERIOD_S
            if wait > 0: time.sleep(wait)
            try:
                self._send_once(conn)
            except Exception as e:
                self.stats["errors"] += 1; self.stats["last_error"] = str(e)[:120]

    def _send_once(self, conn):
        t_enc = time.time()
        jpeg = self._jpeg()
        self.stats["encode_ms"] = round((time.time() - t_enc) * 1000)
        if jpeg is None or time.time() - self.rgb_ts > 1.0:
            return
        tele = {"ts": time.time(), "capture_ts": self.rgb_stamp, "capture_age_ms": round((time.time() - self.rgb_ts) * 1000, 1),
                "dry_run": DRY_RUN, "battery_v": self.battery_v, "yaw_deg": self.yaw, "lidar_front_m": self.scan_front,
                "lidar_age_ms": round((time.time() - self.scan_ts) * 1000) if self.scan_ts else None, "lidar": self.scan_meta,
                "frames": self.stats["frames"], "lease_stops": self.stats["lease_stops"], "obstacle_blocks": self.stats["obstacle_blocks"],
                "stale_cmds": self.stats["stale_cmds"], "moving": self.moving, "errors": self.stats["errors"],
                "servos": {str(k): v for k, v in self.servos.items()} if PHASE2 else None, "servo_age_ms": round((time.time() - self.servo_ts) * 1000) if self.servo_ts else None,
                "imu_omega_dps": [round(x, 1) for x in self.omega], "phase2": PHASE2, "stand": STAND,
                "last_error": self.stats["last_error"], "post_ms": self.stats.get("post_ms"), "send_ms": self.stats.get("send_ms"), "encode_ms": self.stats.get("encode_ms"), "reconnects": self.stats.get("reconnects", 0), "cam_relaunches": self.stats.get("cam_relaunches", 0)}
        u = urlsplit(BRAIN_URL)
        if conn[0] is None:
            self.stats["reconnects"] = self.stats.get("reconnects", 0) + 1
            conn[0] = (http.client.HTTPSConnection(u.hostname, u.port or 443, timeout=1.5, context=ssl.create_default_context())
                       if u.scheme == "https" else http.client.HTTPConnection(u.hostname, u.port or 80, timeout=1.5))
        t_post = time.time()
        try:
            conn[0].request("POST", u.path, body=jpeg,
                              headers={"Content-Type": "image/jpeg", "Authorization": f"Bearer {TOKEN}", "User-Agent": "Ommatid-Body/0.3",
                                       "X-Ommatid-Telemetry": json.dumps(tele), "Connection": "keep-alive"})
            self.stats["send_ms"] = round((time.time() - t_post) * 1000)
            resp = conn[0].getresponse(); data = resp.read()
            if resp.status != 200:
                raise RuntimeError(f"brain HTTP {resp.status}")
            cmd = json.loads(data)
            self.stats["post_ms"] = round((time.time() - t_post) * 1000)
        except Exception:
            try: conn[0].close()
            except Exception: pass
            conn[0] = None
            raise
        now = time.time()
        with self.lock:
            step = int(cmd.get("step", -1))
            if step > self.last_step:                 # only an ADVANCING brain step renews the motion lease
                self.last_step = step; self.lease_ts = now; self.cmd = cmd
            else:
                self.stats["stale_cmds"] += 1
            self.cmd_recv_ts = now
        self.stats["frames"] += 1

    # ---- motion (ROS timer, never blocks) ----------------------------------------
    def _halt(self):
        """Stop the gait engine: Traveling gait=0. NOT the stock 'stop' action group — that one also returns the arm
        (and with it the camera) to the rest pose, pointing it at the floor."""
        m = Traveling(); m.gait = 0; m.interrupt = True
        self.pub_travel.publish(m)
        self.moving = False

    def _drive_legs(self, cmd, lease_age):
        """Phase 2: the brain's per-servo targets go to the legs, rate-limited, only while the lease is fresh and the
        battery is above the floor. In dry run nothing moves; the would-be targets are reported."""
        if cmd is None or lease_age > LEASE_S or not cmd.get("servos"):
            return
        if self.battery_v is not None and self.battery_v < BATTERY_FLOOR_V:
            return
        targets = {}
        for k, v in cmd["servos"].items():
            sid = int(k)
            if sid not in LEG_IDS: continue
            cur = self.leg_targets.get(sid, self.servos.get(sid, int(v)))
            step = max(-MAX_PULSE_STEP, min(MAX_PULSE_STEP, int(v) - cur))
            targets[sid] = int(clamp(cur + step, 0, 1000))
        self.leg_targets.update(targets)
        self.stats["would_servos"] = targets
        if DRY_RUN or not targets:
            return
        m = ServosPosition(); m.duration = 0.1; m.position_unit = "pulse"
        m.position = [ServoPosition(id=sid, position=float(p)) for sid, p in targets.items()]
        self.pub_servo.publish(m); self.moving = True

    def _drive(self):
        now = time.time()
        with self.lock:
            cmd, lease_ts = self.cmd, self.lease_ts
        if PHASE2:
            self._drive_legs(cmd, now - lease_ts if cmd else 1e9); return
        lin = yaw = 0.0
        if cmd is None or now - lease_ts > LEASE_S:
            if cmd is not None and self.moving: self.stats["lease_stops"] += 1
        elif not cmd.get("stop") and (self.battery_v is None or self.battery_v >= BATTERY_FLOOR_V):
            lin = clamp(float(cmd.get("linear_mps", 0.0)), -MAX_LINEAR, MAX_LINEAR)
            yaw = clamp(float(cmd.get("yaw_rps", 0.0)), -MAX_YAW, MAX_YAW)
            scan_fresh = (now - self.scan_ts) < SCAN_FRESH_S
            if lin > 0 and (not scan_fresh or self.scan_front is None or self.scan_front < OBSTACLE_STOP_M):
                lin = 0.0; self.stats["obstacle_blocks"] += 1
            self.stats["would"] = {"linear": round(lin, 3), "yaw": round(yaw, 3)}
        want = (not DRY_RUN) and (abs(lin) > 0.005 or abs(yaw) > 0.02)
        if want:
            t = Twist(); t.linear.x = lin; t.angular.z = yaw
            self.pub_vel.publish(t); self.moving = True
        elif self.moving:
            self._halt()


def main():
    rclpy.init()
    node = Body()
    try:
        rclpy.spin(node)
    finally:
        node._halt(); node.destroy_node(); rclpy.shutdown()


if __name__ == "__main__":
    main()
