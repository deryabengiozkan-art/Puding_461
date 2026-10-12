"""Spawned, synchronized two-pose/four-hand vision worker; never imports Pygame.

VIDEO inference in this dedicated process yields pose and hand results from the
same source frame. The UI remains responsive, and crossing-hand associations
cannot accidentally combine observations captured at different moments.
"""
from pathlib import Path
import queue
import cv2 as cv
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from duel_tracking import (HAND_CROP_SIZE, HandStateHold, IdentityTracker, crop_affine,
                           hand_crop_box, measure_hands, pick_crop_hand)
from tracking_clock import monotonic_seconds


def model_path(*filenames):
    """First model found beside the game; earlier names are preferred."""
    folder = Path(__file__).resolve().parent
    for filename in filenames:
        for path in (folder / filename, folder.parent / filename):
            if path.is_file():
                return str(path)
    raise FileNotFoundError(f'Missing {filenames[-1]}; put the tracking model beside the game.')


# The full pose model keeps wrists steadier for small, distant bodies. It is
# optional: drop pose_landmarker_full.task beside the game to use it.
POSE_MODELS = ('pose_landmarker_full.task', 'pose_landmarker_lite.task')
# Overlapping left and right halves of the unmirrored frame, searched when the
# full-frame pass has not found both players.
TILES = ((0., .5625), (.4375, 1.))
CAPTURE_WIDTH, CAPTURE_HEIGHT = 640, 480
# Below this body size (shoulder width, px) a fist is too small to read
# reliably; testing misread one as Open, which would fire an arrow.
MIN_HAND_BODY_PX = 34


BODY_LINKS = ((11, 12), (11, 23), (12, 24), (23, 24), (11, 13), (13, 15), (12, 14), (14, 16),
              (23, 25), (25, 27), (27, 29), (29, 31), (27, 31), (24, 26), (26, 28), (28, 30), (30, 32), (28, 32),
              (0, 2), (2, 7), (0, 5), (5, 8), (9, 10))
POSE_HAND_LINKS = {'Left': ((15, 17), (17, 19), (19, 15), (15, 21)),
                   'Right': ((16, 18), (18, 20), (20, 16), (16, 22))}
HAND_LINKS = ((0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11),
              (11, 12), (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (0, 17), (17, 18), (18, 19), (19, 20))


def draw_player(frame, observation, colour, player_id):
    """Skeleton, hands and label for one tracked player on the mirrored BGR frame."""
    height, width = frame.shape[:2]
    pose = np.asarray(observation['pose'], dtype=float)
    visible = np.asarray(observation.get('visible', np.ones(len(pose))))
    pixel = lambda p: tuple(np.int32(np.asarray(p[:2]) * [width, height]))
    usable = lambda i: np.isfinite(pose[i]).all() and visible[i] >= .5
    # Thin strokes for distant (small) players so the skeleton stays readable.
    body_px = observation.get('size', observation['scale']) * width
    thick, dot = (2, 3) if body_px >= 70 else (1, 2)

    def links(pairs, colour, thickness):
        for a, b in pairs:
            if usable(a) and usable(b):
                cv.line(frame, pixel(pose[a]), pixel(pose[b]), colour, thickness, cv.LINE_AA)

    links(BODY_LINKS, colour, thick)
    for i in range(33):
        if usable(i):
            cv.circle(frame, pixel(pose[i]), dot, colour, -1, cv.LINE_AA)
    # The drawing hand comes from the hand model (21 joints, white); the bow
    # hand, or a right hand the model missed, from the pose's hand points.
    hand = observation.get('hand_points')
    links(POSE_HAND_LINKS['Left'], colour, thick)
    if hand is None:
        links(POSE_HAND_LINKS['Right'], colour, thick)
    else:
        for a, b in HAND_LINKS:
            cv.line(frame, pixel(hand[a]), pixel(hand[b]), (255, 255, 255), 1, cv.LINE_AA)
        for point in hand:
            cv.circle(frame, pixel(point), 1, colour, -1, cv.LINE_AA)
    for wrist in observation.get('wrists', {}).values():
        cv.circle(frame, pixel(wrist), dot + 1, colour, -1, cv.LINE_AA)
    box = observation.get('hand_box')
    if box is not None:
        cx, cy, side = box
        cv.rectangle(frame, (int(cx - side / 2), int(cy - side / 2)),
                     (int(cx + side / 2), int(cy + side / 2)), colour, 1)
    center = pixel(observation['center'])
    cv.putText(frame, f'P{player_id + 1} {observation.get("state", "Unknown")}', (center[0] - 40, center[1] - 25),
               cv.FONT_HERSHEY_SIMPLEX, .5, colour, 2, cv.LINE_AA)


def publish(output, packet):
    try:
        output.put_nowait(packet)
    except queue.Full:
        try:
            output.get_nowait()
        except queue.Empty:
            pass
        try:
            output.put_nowait(packet)
        except queue.Full:
            pass


class DuelCapture:
    def __init__(self, camera_index=0):
        self.camera = self.pose_detector = None
        self.hand_detectors = [None, None]
        self.tile_detectors = []
        self.hand_misses = [0, 0]
        self.identities = IdentityTracker()
        self.hand_states = HandStateHold()
        self.last_stamp = 0
        try:
            self.pose_detector = self.new_pose_detector(2)
            self.hand_detectors = [self.new_hand_detector(), self.new_hand_detector()]
            self.tile_detectors = [self.new_pose_detector(1) for _ in TILES]
            self.camera = cv.VideoCapture(camera_index)
            if not self.camera.isOpened():
                raise RuntimeError('Could not open the webcam. Check permission, or choose keyboard duel.')
            self.camera.set(cv.CAP_PROP_FRAME_WIDTH, CAPTURE_WIDTH)
            self.camera.set(cv.CAP_PROP_FRAME_HEIGHT, CAPTURE_HEIGHT)
            self.camera.set(cv.CAP_PROP_FPS, 30)
            self.camera.set(cv.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            self.close()
            raise

    def read(self):
        ok, frame = self.camera.read()
        if not ok:
            raise RuntimeError('Webcam stopped delivering frames. Reconnect it, or choose keyboard duel.')
        stamp = max(int(monotonic_seconds() * 1000), self.last_stamp + 1)
        self.last_stamp = stamp
        height, width = frame.shape[:2]
        factor = min(CAPTURE_WIDTH / width, CAPTURE_HEIGHT / height, 1.)
        if factor < 1:
            frame = cv.resize(frame, None, fx=factor, fy=factor, interpolation=cv.INTER_AREA)
        rgb = cv.cvtColor(frame, cv.COLOR_BGR2RGB)
        height, width = rgb.shape[:2]
        aspect = width / height
        raw = np.ascontiguousarray(rgb)
        poses = self.pose_detector.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=raw), stamp)
        # Infer the original image to preserve anatomical Left/Right, then
        # reflect all coordinates and the preview for intuitive movement.
        frame = cv.flip(frame, 1)
        rgb = np.ascontiguousarray(rgb[:, ::-1])
        candidates = self.candidates(poses.pose_landmarks, 0., 1., rgb, aspect)
        if len(candidates) < 2:
            # The person detector sees the whole frame at 224 px, so distant
            # players vanish from it first. Look again at each zoomed half.
            for detector, (x0, x1) in zip(self.tile_detectors, TILES):
                left, right = int(x0 * width), int(x1 * width)
                tile = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(raw[:, left:right]))
                found = detector.detect_for_video(tile, stamp).pose_landmarks
                for extra in self.candidates(found, left / width, (right - left) / width, rgb, aspect):
                    if all(np.linalg.norm((extra['center'] - c['center']) * [1, 1 / aspect])
                           > max(c['scale'], extra['scale']) for c in candidates):
                        candidates.append(extra)
        observations = self.identities.update(candidates, stamp)
        draw_states = [None, None]
        for player_id, observation in enumerate(observations):
            if observation is None:
                continue
            draw_states[player_id] = self.hand_states.update(
                player_id, observation['generation'], self.draw_hand(rgb, observation, stamp), stamp)
        observations = measure_hands(observations, draw_states, aspect)
        colors = ((60, 220, 245), (210, 140, 255))
        for player_id, observation in enumerate(observations):
            if observation is not None:
                draw_player(frame, observation, colors[player_id], player_id)
        found = sum(o is not None for o in observations)
        complete = sum(o is not None and o.get('hands_clear', False) for o in observations)
        status = ('Both players tracked — move, pull and release.' if complete == 2 else
                  'Keep both wrists visible. Close your right hand to draw.' if found == 2 else
                  'Keep both players visible. P1 starts on the preview left, P2 on the right.')
        preview = cv.cvtColor(cv.resize(frame, (320, round(320 / aspect)), interpolation=cv.INTER_AREA), cv.COLOR_BGR2RGB)
        return preview, observations, status, stamp

    @staticmethod
    def new_pose_detector(num_poses):
        return vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=model_path(*POSE_MODELS)),
            running_mode=vision.RunningMode.VIDEO, num_poses=num_poses,
            min_pose_detection_confidence=.5, min_pose_presence_confidence=.5,
            min_tracking_confidence=.5))

    @staticmethod
    def new_hand_detector():
        # One tracker per player. The crop follows that player's right wrist,
        # so the hand stays near the crop centre and VIDEO-mode tracking can
        # skip the palm detector on most frames (about half the cost).
        return vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=model_path('hand_landmarker.task')),
            running_mode=vision.RunningMode.VIDEO, num_hands=1,
            min_hand_detection_confidence=.35, min_hand_presence_confidence=.35,
            min_tracking_confidence=.35))

    @staticmethod
    def candidates(pose_landmarks, x0, span, rgb, aspect):
        """Body observations from poses found in a vertical strip of the frame.

        x0 and span place the strip in the unmirrored frame (0..1); returned
        coordinates are frame-normalized and mirrored like the preview.
        """
        height, width = rgb.shape[:2]
        found = []
        for landmarks in pose_landmarks:
            local = np.array([[p.x, p.y] for p in landmarks], dtype=float)
            if len(local) < 33 or not np.isfinite(local).all():
                continue
            if any(min(getattr(landmarks[i], 'visibility', 1.), getattr(landmarks[i], 'presence', 1.)) < .5
                   for i in (11, 12)):
                continue
            # A body cut by the strip's edge is only partly seen there.
            if np.any(local[[11, 12], 0] < .025) or np.any(local[[11, 12], 0] > .975):
                continue
            points = local.copy()
            points[:, 0] = 1 - (x0 + local[:, 0] * span)
            shoulders = points[[11, 12]]
            if np.any(shoulders < .025) or np.any(shoulders > .975):
                continue
            center = shoulders.mean(axis=0)
            scale = float(np.linalg.norm((shoulders[0] - shoulders[1]) * [1, 1 / aspect]))
            # Median shirt colour aids identity when the two people cross; never
            # rely on left/right order after their initial assignment.
            y = center[1] + scale * aspect * .35
            half = max(2, int(scale * width * .20))
            cx, cy = int(center[0] * width), int(y * height)
            crop = rgb[max(0, cy-half):min(height, cy+half), max(0, cx-half):min(width, cx+half)]
            colour = np.median(crop.reshape(-1, 3), axis=0) / 255 if crop.size else np.zeros(3)
            # Arms and hand points far away report lower visibility; the hand
            # crop verifies the drawing hand, so accept them a little earlier.
            for i in range(13, 23):
                if getattr(landmarks[i], 'visibility', 1.) < .3:
                    points[i] = np.nan
            # Shoulder width collapses when a player turns side-on; neck and
            # torso lengths do not, so the hand crop uses the largest estimate.
            size = scale
            if min(getattr(landmarks[0], 'visibility', 1.), getattr(landmarks[0], 'presence', 1.)) >= .5:
                neck = float(np.linalg.norm((points[0] - center) * [1, 1 / aspect]))
                size = max(size, 1.6 * neck)
            hips = local[[23, 24]]
            if all(min(getattr(landmarks[i], 'visibility', 1.), getattr(landmarks[i], 'presence', 1.)) >= .5
                   for i in (23, 24)):
                hip_mid = 1 - (x0 + hips[:, 0].mean() * span), hips[:, 1].mean()
                torso = float(np.linalg.norm((np.array(hip_mid) - center) * [1, 1 / aspect]))
                size = max(scale, .8 * torso)
            visible = np.array([min(getattr(p, 'visibility', 1.), getattr(p, 'presence', 1.)) for p in landmarks])
            found.append({'pose': points, 'center': center, 'scale': scale, 'size': size, 'colour': colour,
                          'visible': visible})
        return found

    def draw_hand(self, rgb, observation, stamp):
        """Run the hand model on an upscaled crop around the right wrist."""
        height, width = rgb.shape[:2]
        size = observation.get('size', observation['scale'])
        box = hand_crop_box(observation['pose'], size, width, height)
        observation['hand_box'] = box
        observation['hand_points'] = None
        if box is None or size * width < MIN_HAND_BODY_PX:
            return 'Unknown'
        crop = cv.warpAffine(rgb, crop_affine(box), (HAND_CROP_SIZE, HAND_CROP_SIZE),
                             flags=cv.INTER_LINEAR, borderMode=cv.BORDER_CONSTANT)
        player_id = observation['player_id']
        result = self.hand_detectors[player_id].detect_for_video(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(crop)), stamp)
        candidates = [[[p.x, p.y, p.z] for p in landmarks] for landmarks in result.hand_landmarks]
        hand = pick_crop_hand(candidates, box, observation['pose'][16], size, width, height)
        # A tracker can latch onto the bow hand while both hands are together.
        # If it keeps following a hand that is not at the right wrist, restart it.
        self.hand_misses[player_id] = self.hand_misses[player_id] + 1 if candidates and hand is None else 0
        if self.hand_misses[player_id] >= 3:
            self.hand_detectors[player_id].close()
            self.hand_detectors[player_id] = self.new_hand_detector()
            self.hand_misses[player_id] = 0
        if hand is None:
            return 'Unknown'
        observation['hand_points'] = hand['points']
        return hand['state']

    def close(self):
        for detector in [*getattr(self, 'hand_detectors', ()), *getattr(self, 'tile_detectors', ())]:
            if detector is not None:
                try:
                    detector.close()
                except Exception:
                    pass
        self.hand_detectors = [None, None]
        self.tile_detectors = []
        for name in ('camera', 'pose_detector'):
            item = getattr(self, name, None)
            if item is not None:
                try:
                    item.release() if name == 'camera' else item.close()
                except Exception:
                    pass
                setattr(self, name, None)


def run_camera(output, stop, camera_index):
    capture = None
    try:
        capture = DuelCapture(camera_index)
        while not stop.is_set():
            rgb, observations, status, stamp = capture.read()
            publish(output, {'type': 'frame', 'rgb': rgb, 'observations': observations,
                             'status': status, 'stamp': stamp})
    except Exception as exc:
        while not stop.is_set():
            publish(output, {'type': 'error', 'message': str(exc)})
            stop.wait(.1)
    finally:
        if capture is not None:
            capture.close()
        output.cancel_join_thread()
