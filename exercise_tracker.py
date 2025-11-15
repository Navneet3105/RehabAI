# exercise_tracker.py
import cv2
import mediapipe as mp
import numpy as np
import time
import json
import os
from datetime import datetime

mp_drawing = mp.solutions.drawing_utils
mp_pose = mp.solutions.pose

# Default optimal ranges (degrees)
OPTIMAL_RANGES = {
    "squat": (60, 180),
    "pushup": (80, 160),
    "curl": (20, 170),
    "raise": (15, 95)
}

EXERCISES_FILE = "exercises.json"
DB_FILE = "database.json"

# ---------- utilities for file persistence ----------
def ensure_exercises_file():
    if not os.path.exists(EXERCISES_FILE):
        with open(EXERCISES_FILE, "w") as f:
            json.dump({"custom_exercises": {}}, f, indent=4)

def load_custom_exercises():
    ensure_exercises_file()
    with open(EXERCISES_FILE, "r") as f:
        return json.load(f).get("custom_exercises", {})

def save_custom_exercise(name, joint_limits):
    ensure_exercises_file()
    with open(EXERCISES_FILE, "r") as f:
        data = json.load(f)
    data.setdefault("custom_exercises", {})
    # preserve any existing metadata if present (therapist code may add default_sets/optimal_range later)
    data["custom_exercises"][name] = data["custom_exercises"].get(name, {})
    data["custom_exercises"][name].setdefault("joints", joint_limits)
    data["custom_exercises"][name]["joints"] = joint_limits
    data["custom_exercises"][name]["created"] = datetime.utcnow().isoformat()
    with open(EXERCISES_FILE, "w") as f:
        json.dump(data, f, indent=4)

    # update DB snapshot
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            db = json.load(f)
    else:
        db = {}
    db.setdefault("exercises", {})
    # copy joint_limits (therapist UI populates default_sets/optimal_range afterwards)
    db["exercises"][name] = db["exercises"].get(name, {})
    db["exercises"][name]["joints"] = joint_limits
    db["exercises"][name]["created"] = datetime.utcnow().isoformat()
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=4)

# ---------- joint definitions ----------
JOINT_TRIPLES = {
    "LEFT_ELBOW": ("LEFT_SHOULDER", "LEFT_ELBOW", "LEFT_WRIST"),
    "RIGHT_ELBOW": ("RIGHT_SHOULDER", "RIGHT_ELBOW", "RIGHT_WRIST"),
    "LEFT_SHOULDER": ("LEFT_HIP", "LEFT_SHOULDER", "LEFT_ELBOW"),
    "RIGHT_SHOULDER": ("RIGHT_HIP", "RIGHT_SHOULDER", "RIGHT_ELBOW"),
    "LEFT_KNEE": ("LEFT_HIP", "LEFT_KNEE", "LEFT_ANKLE"),
    "RIGHT_KNEE": ("RIGHT_HIP", "RIGHT_KNEE", "RIGHT_ANKLE"),
    "LEFT_HIP": ("LEFT_SHOULDER", "LEFT_HIP", "LEFT_KNEE"),
    "RIGHT_HIP": ("RIGHT_SHOULDER", "RIGHT_HIP", "RIGHT_KNEE")
}

# ---------- math helpers ----------
def _angle(a, b, c):
    a = np.array(a); b = np.array(b); c = np.array(c)
    radians = np.arctan2(c[1]-b[1], c[0]-b[0]) - np.arctan2(a[1]-b[1], a[0]-b[0])
    angle = np.abs(radians * 180.0 / np.pi)
    if angle > 180:
        angle = 360 - angle
    return angle

def _land(landmarks, lm_name):
    p = landmarks[mp_pose.PoseLandmark[lm_name].value]
    return (p.x, p.y, p.z, p.visibility)

def _range_average_low_high(samples, low_pct=0.3):
    n = len(samples)
    if n == 0:
        return 0.0, 0.0
    k = max(1, int(np.ceil(n * low_pct)))
    s_sorted = sorted(samples)
    low_group = s_sorted[:k]
    high_group = s_sorted[-k:]
    avg_low = float(np.mean(low_group)) if low_group else float(np.min(samples))
    avg_high = float(np.mean(high_group)) if high_group else float(np.max(samples))
    return avg_low, avg_high

def _iqr(values):
    if not values:
        return 0.0
    a = np.percentile(values, [25, 75])
    return float(a[1] - a[0])

def _compute_deviation_repwise(rep_averages, opt_min, opt_max, cap_percent=200.0):
    if not rep_averages:
        return 0.0

    reps = [max(0.0, min(float(x), 180.0)) for x in rep_averages]
    n = len(reps)
    rep_min = min(reps)
    rep_max = max(reps)
    rep_range = rep_max - rep_min

    try:
        opt_min_f = float(opt_min)
        opt_max_f = float(opt_max)
    except Exception:
        opt_min_f, opt_max_f = 0.0, 180.0

    opt_min_f = max(0.0, min(opt_min_f, 180.0))
    opt_max_f = max(0.0, min(opt_max_f, 180.0))
    opt_width = opt_max_f - opt_min_f
    if opt_width <= 0.0:
        opt_width = 1.0

    inliers = sum(1 for r in reps if (opt_min_f <= r <= opt_max_f))
    inlier_frac = inliers / n

    distance_to_band = 0.0
    if rep_max < opt_min_f:
        distance_to_band = opt_min_f - rep_max
    elif rep_min > opt_max_f:
        distance_to_band = rep_min - opt_max_f
    else:
        distance_to_band = 0.0

    if distance_to_band > 0.0:
        deviation = (distance_to_band / opt_width) * 100.0
        deviation = min(max(deviation, 0.0), float(cap_percent))
        return float(round(deviation, 2))

    spread = 0.0
    if n >= 4:
        spread = _iqr(reps)
        if spread <= 0.0:
            spread = min(0.01, rep_range)
    else:
        if n == 1:
            spread = 0.0
        elif n == 2:
            spread = rep_range
        else:
            reps_sorted = sorted(reps)
            if len(reps_sorted) >= 2:
                spread = reps_sorted[-2] - reps_sorted[1]
            else:
                spread = rep_range
            if spread <= 0:
                spread = rep_range

    base_dev = (spread / opt_width) * 100.0
    multiplier = 1.0 + (1.0 - inlier_frac)
    deviation = base_dev * multiplier

    if rep_range > opt_width:
        extra = ((rep_range - opt_width) / opt_width) * 100.0
        deviation = max(deviation, extra)

    deviation = min(max(deviation, 0.0), float(cap_percent))
    return float(round(deviation, 2))

# ---------- main exercise recording for therapist (custom exercise) ----------
def record_custom_exercise(session_name, camera_index=0, countdown_seconds=3):
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print("Error: cannot open camera")
        return {}

    joint_samples = {j: [] for j in JOINT_TRIPLES.keys()}

    with mp_pose.Pose(min_detection_confidence=0.6, min_tracking_confidence=0.6) as pose:
        start_t = time.time()
        collecting = False
        countdown_start = None

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]
            img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img.flags.writeable = False
            res = pose.process(img)
            img.flags.writeable = True
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

            if countdown_start is None:
                countdown_start = time.time()

            elapsed = time.time() - countdown_start
            remaining = countdown_seconds - int(elapsed)
            if remaining > 0:
                cv2.putText(img, f"Starting in {remaining}", (w//2 - 140, h//2),
                            cv2.FONT_HERSHEY_SIMPLEX, 3.0, (0, 255, 255), 6)
                cv2.putText(img, "Get ready", (w//2 - 100, h//2 + 80),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (200, 200, 200), 2)
            else:
                collecting = True
                cv2.putText(img, f"Recording '{session_name}'", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

            if collecting and res.pose_landmarks:
                lm = res.pose_landmarks.landmark

                def px(name):
                    p = _land(lm, name)
                    return (p[0]*w, p[1]*h)

                for j, triple in JOINT_TRIPLES.items():
                    try:
                        a = px(triple[0]); b = px(triple[1]); c = px(triple[2])
                        ang = _angle(a, b, c)
                        ang = float(ang % 180.0)
                        ang = max(0.0, min(ang, 180.0))
                        joint_samples[j].append(ang)
                    except Exception:
                        pass

                mp_drawing.draw_landmarks(img, res.pose_landmarks, mp_pose.POSE_CONNECTIONS)
            else:
                if not collecting:
                    pass
                else:
                    cv2.putText(img, "No person detected - get visible", (10, 60),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            cv2.imshow("Record Custom Exercise - RehabAI", img)

            key = cv2.waitKey(5) & 0xFF
            if key == 27:
                break
            if time.time() - start_t > (countdown_seconds + 30):
                break

    cap.release()
    cv2.destroyAllWindows()

    joint_limits = {}
    for j, samples in joint_samples.items():
        if samples:
            mn = float(round(min(samples), 2))
            mx = float(round(max(samples), 2))
            if mn == mx:
                mn = max(0.0, mn - 1.0)
                mx = min(180.0, mx + 1.0)
            joint_limits[j] = [mn, mx]

    if joint_limits:
        save_custom_exercise(session_name, joint_limits)
    return joint_limits

# ---------- helper to pick primary joint (largest range) ----------
def pick_primary_joint_from_limits(joint_limits):
    if not joint_limits:
        return None
    best = None
    best_range = -1.0
    for j, (mn, mx) in joint_limits.items():
        rng = mx - mn
        if rng > best_range:
            best = j
            best_range = rng
    return best

# ---------- start exercise (supports custom exercises by name) ----------
def start_exercise(ex_name, target_reps=None, camera_index=0, opt_range=None):
    ex = ex_name.lower()

    custom_exs = load_custom_exercises()
    custom_def = None
    if ex_name in custom_exs:
        custom_def = custom_exs[ex_name]
    else:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "r") as f:
                db = json.load(f)
            if "exercises" in db and ex_name in db["exercises"]:
                custom_def = db["exercises"][ex_name]

    joint_limits = {}
    primary_joint = None
    exercise_opt_range = None

    if custom_def and isinstance(custom_def, dict):
        joint_limits = custom_def.get("joints", {})
        primary_joint = pick_primary_joint_from_limits(joint_limits)
        # If the custom exercise defines an optimal_range, use it as opt_range fallback
        # optimal_range format (therapist UI stores): {"joint": "LEFT_ELBOW", "min": 20, "max": 150}
        ex_opt = custom_def.get("optimal_range")
        if isinstance(ex_opt, dict) and "min" in ex_opt and "max" in ex_opt:
            try:
                exercise_opt_range = (float(ex_opt.get("min")), float(ex_opt.get("max")))
            except Exception:
                exercise_opt_range = None

    if opt_range is None:
        if exercise_opt_range is not None:
            opt_range = exercise_opt_range
        elif ex in OPTIMAL_RANGES:
            opt_range = OPTIMAL_RANGES.get(ex, (0, 0))
        else:
            opt_range = (None, None)

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print("Error: cannot open camera")
        return {
            'reps': 0,
            'rep_averages': [],
            'overall_avg': 0.0,
            'angle_min': 0.0,
            'angle_max': 0.0,
            'range_avg_low': 0.0,
            'range_avg_high': 0.0,
            'rep_min': 0.0,
            'rep_max': 0.0,
            'rep_range': 0.0,
            'opt_range': opt_range,
            'deviation_percent': 0.0,
            'timestamp': datetime.utcnow().isoformat()
        }

    counter = 0
    stage = None
    last_time = time.time()
    cooldown = 0.4

    rep_angles = []
    rep_averages = []
    all_angles = []

    with mp_pose.Pose(min_detection_confidence=0.6, min_tracking_confidence=0.6) as pose:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]
            img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img.flags.writeable = False
            res = pose.process(img)
            img.flags.writeable = True
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

            angle_value = None
            feedback = ""
            info = ""

            if res.pose_landmarks:
                lm = res.pose_landmarks.landmark

                def px(name):
                    p = _land(lm, name)
                    return (p[0]*w, p[1]*h)

                try:
                    if primary_joint:
                        triple = JOINT_TRIPLES.get(primary_joint)
                        if triple:
                            a = px(triple[0]); b = px(triple[1]); c = px(triple[2])
                            angle_value = _angle(a, b, c)
                            info = f"{primary_joint} angle: {int(angle_value)}"

                            jlim = joint_limits.get(primary_joint)
                            if jlim and isinstance(jlim, list) and len(jlim) == 2:
                                lim_min, lim_max = jlim
                            else:
                                lim_min, lim_max = None, None

                            if lim_min is not None and lim_max is not None:
                                if angle_value > (lim_max - 5):
                                    if stage == "down":
                                        stage = "up"
                                if angle_value < (lim_min + 5):
                                    if stage == "up":
                                        if (time.time() - last_time) > cooldown:
                                            counter += 1
                                            last_time = time.time()
                                            if rep_angles:
                                                rep_avg = float(np.mean(rep_angles))
                                                rep_averages.append(rep_avg)
                                                rep_angles = []
                                        stage = "down"
                                if stage is None:
                                    mid = (lim_min + lim_max) / 2.0
                                    stage = "up" if angle_value > mid else "down"

                                try:
                                    if lim_min < lim_max:
                                        if angle_value < lim_min:
                                            feedback = "Go higher!"
                                        elif angle_value > lim_max:
                                            feedback = "Go lower!"
                                        else:
                                            feedback = "Good form!"
                                except Exception:
                                    feedback = ""
                            else:
                                omn, omx = opt_range if opt_range else (None, None)
                                try:
                                    if omn is not None and omx is not None:
                                        if angle_value < omn:
                                            feedback = "Go higher!"
                                        elif angle_value > omx:
                                            feedback = "Go lower!"
                                        else:
                                            feedback = "Good form!"
                                except Exception:
                                    feedback = ""
                    else:
                        # built-in fallback logic (unchanged)
                        if ex == "squat":
                            hip = px("LEFT_HIP"); knee = px("LEFT_KNEE"); ankle = px("LEFT_ANKLE")
                            angle_value = _angle(hip, knee, ankle)
                            if angle_value > 160:
                                stage = "up"
                            if angle_value < 95 and stage == "up":
                                stage = "down"
                            if angle_value > 140 and stage == "down" and (time.time()-last_time) > cooldown:
                                counter += 1
                                last_time = time.time()
                                if rep_angles:
                                    rep_avg = float(np.mean(rep_angles))
                                    rep_averages.append(rep_avg)
                                    rep_angles = []
                                stage = "up"
                            info = f"Knee angle: {int(angle_value)}"

                        elif ex == "pushup":
                            shoulder = px("LEFT_SHOULDER"); elbow = px("LEFT_ELBOW"); wrist = px("LEFT_WRIST")
                            angle_value = _angle(shoulder, elbow, wrist)
                            if angle_value > 150:
                                stage = "up"
                            if angle_value < 90 and stage == "up":
                                stage = "down"
                            if angle_value > 140 and stage == "down" and (time.time()-last_time) > cooldown:
                                counter += 1
                                last_time = time.time()
                                if rep_angles:
                                    rep_avg = float(np.mean(rep_angles))
                                    rep_averages.append(rep_avg)
                                    rep_angles = []
                                stage = "up"
                            info = f"Elbow angle: {int(angle_value)}"

                        elif ex == "curl":
                            shoulder = px("LEFT_SHOULDER"); elbow = px("LEFT_ELBOW"); wrist = px("LEFT_WRIST")
                            angle_value = _angle(shoulder, elbow, wrist)
                            if angle_value > 150:
                                stage = "down"
                            if angle_value < 60 and stage == "down" and (time.time()-last_time) > cooldown:
                                counter += 1
                                last_time = time.time()
                                if rep_angles:
                                    rep_avg = float(np.mean(rep_angles))
                                    rep_averages.append(rep_avg)
                                    rep_angles = []
                                stage = "up"
                            info = f"Elbow angle: {int(angle_value)}"

                        elif ex == "raise" or ex == "lateral raise":
                            hip = px("LEFT_HIP"); shoulder = px("LEFT_SHOULDER"); elbow = px("LEFT_ELBOW")
                            angle_value = _angle(hip, shoulder, elbow)
                            if angle_value < 30:
                                stage = "down"
                            if angle_value > 75 and stage == "down" and (time.time()-last_time) > cooldown:
                                counter += 1
                                last_time = time.time()
                                if rep_angles:
                                    rep_avg = float(np.mean(rep_angles))
                                    rep_averages.append(rep_avg)
                                    rep_angles = []
                                stage = "up"
                            info = f"Shoulder raise angle: {int(angle_value)}"

                        else:
                            info = "Unknown exercise"
                except Exception:
                    info = "Landmarks not fully visible"

                if angle_value is not None:
                    angle_value = float(angle_value % 180.0)
                    angle_value = max(0.0, min(angle_value, 180.0))

                    all_angles.append(angle_value)
                    rep_angles.append(angle_value)

                    opt_min, opt_max = opt_range
                    try:
                        if opt_min is not None and opt_max is not None:
                            opt_min_f = float(opt_min)
                            opt_max_f = float(opt_max)
                            opt_min_f = max(0.0, min(opt_min_f, 180.0))
                            opt_max_f = max(0.0, min(opt_max_f, 180.0))
                            if opt_min_f < opt_max_f:
                                if angle_value < opt_min_f:
                                    feedback = "Go higher!"
                                elif angle_value > opt_max_f:
                                    feedback = "Go lower!"
                                else:
                                    feedback = "Good form!"
                    except Exception:
                        pass

                mp_drawing.draw_landmarks(img, res.pose_landmarks, mp_pose.POSE_CONNECTIONS)
                cv2.putText(img, f"{ex_name.upper()}  Reps: {counter}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
                if angle_value is not None:
                    cv2.putText(img, info, (10, 60),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
                    if feedback:
                        cv2.putText(img, feedback, (10, 100),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)
            else:
                cv2.putText(img, "No person detected", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            cv2.imshow("RehabAI Exercise Tracker", img)

            if target_reps is not None and counter >= target_reps:
                break

            key = cv2.waitKey(5) & 0xFF
            if key == 27:
                break

    cap.release()
    cv2.destroyAllWindows()

    if rep_angles:
        rep_averages.append(float(np.mean(rep_angles)))

    norm_angles = [float(a % 180.0) for a in all_angles] if all_angles else []
    norm_angles = [max(0.0, min(a, 180.0)) for a in norm_angles]
    overall_avg = float(round(np.mean(norm_angles), 2)) if norm_angles else 0.0
    angle_min = float(round(min(norm_angles), 2)) if norm_angles else 0.0
    angle_max = float(round(max(norm_angles), 2)) if norm_angles else 0.0

    range_avg_low, range_avg_high = _range_average_low_high(norm_angles, low_pct=0.3)
    range_avg_low = float(round(range_avg_low, 2))
    range_avg_high = float(round(range_avg_high, 2))

    rep_min = float(round(min(rep_averages), 2)) if rep_averages else 0.0
    rep_max = float(round(max(rep_averages), 2)) if rep_averages else 0.0
    rep_range = float(round((rep_max - rep_min), 2)) if rep_averages else 0.0

    opt_min, opt_max = opt_range
    deviation = _compute_deviation_repwise(rep_averages, opt_min, opt_max, cap_percent=200.0)

    return {
        'reps': int(counter),
        'rep_averages': [float(round(a, 2)) for a in rep_averages],
        'overall_avg': overall_avg,
        'angle_min': angle_min,
        'angle_max': angle_max,
        'range_avg_low': range_avg_low,
        'range_avg_high': range_avg_high,
        'rep_min': rep_min,
        'rep_max': rep_max,
        'rep_range': rep_range,
        'opt_range': opt_range,
        'deviation_percent': float(round(deviation, 2)),
        'timestamp': datetime.utcnow().isoformat()
    }
