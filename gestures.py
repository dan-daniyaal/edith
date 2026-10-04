"""
EDITH — gesture control (proof of concept).

Webcam hand tracking -> mouse control, Stark-style.
  - Point with your INDEX finger to move the cursor.
  - PINCH (index + thumb together) to click; hold the pinch and move to DRAG
    (grab a window's title bar and fling it around).
  - Press Q or ESC in the camera window to quit.

Run:  python gestures.py

100% local (MediaPipe runs on your laptop, nothing uploaded). The webcam is only
on while this runs. Coarse gestures work great; pixel-precision is naturally a bit
wobbly — that's webcam tracking, not a bug.
"""
import os
import time

import cv2
import pyautogui
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

pyautogui.FAILSAFE = False   # don't crash if the cursor hits a screen corner
pyautogui.PAUSE = 0          # no artificial delay between mouse calls (smoothness)
SCREEN_W, SCREEN_H = pyautogui.size()

MODEL_PATH = os.path.join(os.path.dirname(__file__), "hand_landmarker.task")

CYAN = (255, 227, 58)        # BGR for OpenCV
GOLD = (106, 207, 255)

# 21-point hand skeleton topology (we draw it ourselves now)
CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17),
]

MARGIN = 0.15        # active fraction of the frame (smaller area covers full screen)
SMOOTH = 0.45        # cursor smoothing (higher = snappier, lower = steadier)
PINCH_ON = 0.05      # normalized index-thumb distance to start a pinch
PINCH_OFF = 0.07     # distance to release (hysteresis stops flicker)
SCROLL_GAIN = 600    # two-finger scroll speed (raise for faster scrolling)


def _dist(a, b):
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5


def _make_landmarker():
    options = vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=1,
        min_hand_detection_confidence=0.7,
        min_tracking_confidence=0.6,
    )
    return vision.HandLandmarker.create_from_options(options)


def main():
    if not os.path.exists(MODEL_PATH):
        print("Missing hand_landmarker.task in this folder. See README.")
        return

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 540)
    if not cap.isOpened():
        print("Could not open the webcam. Is another app using it?")
        return

    landmarker = _make_landmarker()
    cur_x, cur_y = SCREEN_W / 2, SCREEN_H / 2
    pinching = False
    prev_scroll_y = None
    print("EDITH gesture control online. Point to move, pinch to click/drag.")
    print("Press Q or ESC in the camera window to quit.")

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.flip(frame, 1)               # mirror so it feels natural
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = landmarker.detect_for_video(mp_image, int(time.perf_counter() * 1000))
        status = "no hand detected"

        if result.hand_landmarks:
            pts = result.hand_landmarks[0]       # 21 landmarks (x,y,z normalized)

            for a, b in CONNECTIONS:
                pa = (int(pts[a].x * w), int(pts[a].y * h))
                pb = (int(pts[b].x * w), int(pts[b].y * h))
                cv2.line(frame, pa, pb, CYAN, 2)
            for p in pts:
                cv2.circle(frame, (int(p.x * w), int(p.y * h)), 3, GOLD, -1)

            def _up(tip, pip):
                return pts[tip].y < pts[pip].y - 0.02
            index_up, middle_up = _up(8, 6), _up(12, 10)
            ring_up, pinky_up = _up(16, 14), _up(20, 18)

            if index_up and middle_up and not ring_up and not pinky_up:
                # SCROLL: index + middle up; move the hand up/down to scroll
                if pinching:
                    pyautogui.mouseUp()
                    pinching = False
                cy = (pts[8].y + pts[12].y) / 2
                if prev_scroll_y is not None:
                    pyautogui.scroll(int((prev_scroll_y - cy) * SCROLL_GAIN))
                prev_scroll_y = cy
                status = "SCROLL - move hand up / down"
                cv2.putText(frame, "scroll", (int(pts[8].x * w) + 14, int(pts[8].y * h)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, GOLD, 2, cv2.LINE_AA)
            else:
                # POINT to move, PINCH to click / drag
                prev_scroll_y = None
                idx, thumb = pts[8], pts[4]
                nx = min(max((idx.x - MARGIN) / (1 - 2 * MARGIN), 0), 1)
                ny = min(max((idx.y - MARGIN) / (1 - 2 * MARGIN), 0), 1)
                cur_x += (nx * SCREEN_W - cur_x) * SMOOTH
                cur_y += (ny * SCREEN_H - cur_y) * SMOOTH
                pyautogui.moveTo(int(cur_x), int(cur_y))

                d = _dist(idx, thumb)
                if not pinching and d < PINCH_ON:
                    pyautogui.mouseDown()
                    pinching = True
                elif pinching and d > PINCH_OFF:
                    pyautogui.mouseUp()
                    pinching = False
                status = "PINCH - grab / drag" if pinching else "tracking - point to move"

                ix, iy = int(idx.x * w), int(idx.y * h)
                cv2.circle(frame, (ix, iy), 13, CYAN, 2)
                if pinching:
                    cv2.circle(frame, (ix, iy), 6, GOLD, -1)
        else:
            prev_scroll_y = None
            if pinching:               # hand left the frame mid-drag — let go
                pyautogui.mouseUp()
                pinching = False

        cv2.rectangle(frame, (0, 0), (w, 40), (24, 16, 12), -1)
        cv2.putText(frame, f"EDITH GESTURE  |  {status}  |  Q = quit",
                    (14, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.6, CYAN, 1, cv2.LINE_AA)
        cv2.imshow("EDITH Gesture Control", frame)
        if cv2.waitKey(1) & 0xFF in (27, ord("q")):
            break

    if pinching:
        pyautogui.mouseUp()
    cap.release()
    cv2.destroyAllWindows()
    landmarker.close()
    print("Gesture control off.")


if __name__ == "__main__":
    main()
