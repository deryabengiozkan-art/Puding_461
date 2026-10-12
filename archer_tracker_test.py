# Combined arm/hand tracking with custom open/closed classification.
import cv2 as cv
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import time
import numpy as np
from pathlib import Path


def model_path(filename):
    """Find the shared models regardless of the terminal's working directory."""
    folder = Path(__file__).resolve().parent
    for candidate in (folder / filename, folder.parent / filename):
        if candidate.is_file():
            return str(candidate)
    raise FileNotFoundError(f"Missing {filename}; place it beside the tracker or in {folder.parent}")


class PoseTracker:
    # __init__ runs when PoseTracker() creates an object.
    def __init__(self):
        
        self.joint_positions = None
        self.pose_sample = (None, 0)  # Coordinates and the frame's timestamp together.

        #setting up the pose tracker with the pose_landmarker_lite model for media pipe
        pose_base_options = python.BaseOptions(
            model_asset_path=model_path("pose_landmarker_lite.task")
        )
        pose_options = vision.PoseLandmarkerOptions(
            base_options=pose_base_options,
            running_mode=vision.RunningMode.LIVE_STREAM,
            # Give MediaPipe this object's method to call when results arrive.
            result_callback=self.on_pose_result
        )
        self.detector = vision.PoseLandmarker.create_from_options(pose_options) #a detector object is created from the pose_landmarker_lite model and the options specified above

    # MediaPipe calls this method to update this object's joint positions.
    def on_pose_result(self, result, output_image, timestamp_ms):
        if result.pose_landmarks:
            person = result.pose_landmarks[0]  # Get the first detected person
            positions = []

            for joint in person:
                positions.append([joint.x, joint.y])

            # Shape (33, 2): one x/y pair for each body landmark.
            self.joint_positions = np.array(positions)
        else:
            self.joint_positions = None
        self.pose_sample = (self.joint_positions, timestamp_ms)


class HandTracker:
    def __init__(self):
        # Each HandTracker object owns its labels and stabilization history.
        self.hand_labels = []
        self.hand_history = {}

        # Position history is separate from the Open/Closed gesture history.
        self.wrist_history = {}
        self.wrist_sample = (0, {}, False)
        self.max_wrist_jump = 0.12  # Maximum step in normalized image coordinates.
        self.hold_ms = 200         # Briefly display the last accepted position.
        self.reacquire_ms = 150    # A new position must settle before we accept it.


        #setting up the hand tracker with the hand_landmarker model for media pipe
        hand_base_options = python.BaseOptions(
            model_asset_path=model_path("hand_landmarker.task")
        )
        hand_options = vision.HandLandmarkerOptions(
            base_options=hand_base_options,
            running_mode=vision.RunningMode.LIVE_STREAM,
            num_hands=2,
            result_callback=self.on_hand_result
        )
        self.hand_detector = vision.HandLandmarker.create_from_options(hand_options) #a hand-detector object is created from the hand_landmarker model and the options specified above

    # Measure a finger joint angle using 3D points.
    def finger_angle(self, base, joint, tip):
        """Return the 3D angle at joint, or None for unusable points."""
        first = base - joint
        second = tip - joint
        first_length = np.linalg.norm(first)
        second_length = np.linalg.norm(second)
        if first_length < 1e-9 or second_length < 1e-9:
            return None

        cosine = np.dot(first, second) / (first_length * second_length)
        return np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0)))

    # Use four finger angles to classify the hand as Open, Closed, or Unknown.
    def hand_state(self, landmarks):
        """Estimate open/closed from four fingers; the thumb is not counted."""
        points = np.array([[p.x, p.y, p.z] for p in landmarks])
        if points.shape != (21, 3) or not np.isfinite(points).all():
            return "Unknown"

        fingers = [
            [5, 6, 8],      # Index: base, middle joint, tip
            [9, 10, 12],    # Middle
            [13, 14, 16],   # Ring
            [17, 18, 20],   # Pinky
        ]

        straight = 0
        curled = 0

        for indices in fingers:
            base, joint, tip = points[indices]
            angle = self.finger_angle(base, joint, tip)
            if angle is None:
                continue

            # Same straight/curled thresholds as the bird game's trigger hand.
            if angle > 140:
                straight += 1
            elif angle < 125:
                curled += 1

        if straight >= 3:
            return "Open"
        if curled >= 3 and straight == 0:
            return "Closed"
        return "Unknown"

    # Keep a separate timer for each hand to reduce flickering labels.
    def stabilize_hand(self, side, prediction, timestamp_ms):
        """Accept Open/Closed after 100 ms, or Unknown after 250 ms."""
        history = self.hand_history.get(side)
        if history is None or timestamp_ms - history["last_seen"] > 300:
            history = {
                "stable_state": "Unknown",
                "candidate_state": None,
                "candidate_since": timestamp_ms,
                "last_seen": timestamp_ms,
            }
            self.hand_history[side] = history

        if prediction != history["candidate_state"]:
            history["candidate_state"] = prediction
            history["candidate_since"] = timestamp_ms

        required_duration = 250 if prediction == "Unknown" else 100
        if timestamp_ms - history["candidate_since"] >= required_duration:
            history["stable_state"] = prediction

        history["last_seen"] = timestamp_ms
        return history["stable_state"]

    def update_wrists(self, positions, timestamp_ms):
        """Check labelled wrists against their previous positions before using them."""
        previous = self.wrist_history.copy()
        accepted = set()

        for side in ("Left", "Right"):
            position = positions.get(side)
            history = self.wrist_history.get(side)

            if position is None:
                if history is not None:
                    history["candidate"] = None
                continue

            trustworthy = history is None
            if history is not None:
                step = np.linalg.norm(position - history["position"]) #calculate the distance between the current wrist position and the last known position
                age = timestamp_ms - history["last_seen"] #calculate the time since the last known position was seen
                trustworthy = step <= self.max_wrist_jump and age <= self.hold_ms #determine if the current position is trustworthy by checking if the step is less than the maximum allowed jump and if the age is less than the hold time

                # A label switch can put this wrist near the other hand's old position.
                other_side = "Right" if side == "Left" else "Left"
                other = previous.get(other_side)
                if other is not None and timestamp_ms - other["last_seen"] <= self.hold_ms:
                    other_step = np.linalg.norm(position - other["position"])
                    if step > self.max_wrist_jump / 2 and other_step < step / 2:
                        trustworthy = False

                if not trustworthy:
                    candidate = history["candidate"]
                    if candidate is None or np.linalg.norm(position - candidate) > self.max_wrist_jump / 2:
                        history["candidate"] = position
                        history["candidate_since"] = timestamp_ms

                    # Recover after a real fast movement without staying frozen forever.
                    settled = timestamp_ms - history["candidate_since"] >= self.reacquire_ms
                    trustworthy = age > self.hold_ms and settled

            if trustworthy:
                self.wrist_history[side] = {
                    "position": position,
                    "last_seen": timestamp_ms,
                    "candidate": None,
                    "candidate_since": timestamp_ms,
                }
                accepted.add(side)

        # Old positions may be displayed briefly, but cannot start a new pull.
        wrists = {}
        for side, history in self.wrist_history.items():
            if timestamp_ms - history["last_seen"] <= self.hold_ms:
                wrists[side] = history["position"]

        both_fresh = "Left" in accepted and "Right" in accepted
        self.wrist_sample = (timestamp_ms, wrists, both_fresh)

    # MediaPipe calls this method; store labels for the display loop to read.
    def on_hand_result(self, result, output_image, timestamp_ms):

        labels = []
        wrist_positions = {}
        sides = [hand[0].category_name if hand else None
                 for hand in result.handedness]
        seen_sides = set()

        for i in range(len(result.hand_landmarks)):
            # The same index selects the same hand in each result list.
            landmarks = result.hand_landmarks[i]
            handedness = result.handedness[i]

            label = "Unknown hand"
            if handedness:
                label = handedness[0].category_name + " hand"

            state = "Unknown"
            if i < len(result.hand_world_landmarks):
                state = self.hand_state(result.hand_world_landmarks[i])

            side = sides[i]
            # Ambiguous/duplicate labels must not mix two hands' histories.
            if side in ("Left", "Right") and sides.count(side) == 1:
                state = self.stabilize_hand(side, state, timestamp_ms)
                seen_sides.add(side)
                # Hand landmark 0 is the wrist; landmark 9 remains the text anchor.
                wrist = landmarks[0]
                position = np.array([wrist.x, wrist.y])
                if np.isfinite(position).all():
                    wrist_positions[side] = position
            else:
                state = "Unknown"

            # Landmark 9 is the base of the middle finger.
            anchor = landmarks[9]
            labels.append({
                "x": anchor.x,
                "y": anchor.y,
                "label": label,
                "state": state
            })

        for side in list(self.hand_history):
            if side not in seen_sides:
                # A missing observation breaks the candidate's continuous run.
                self.hand_history[side]["candidate_state"] = None
                if timestamp_ms - self.hand_history[side]["last_seen"] > 300:
                    del self.hand_history[side]

        # Publish the completed list; an empty list clears old labels.
        self.hand_labels = labels
        self.update_wrists(wrist_positions, timestamp_ms)


class ArcherTracker:
    def __init__(self):
        # OpenCV colors use BGR: blue, green, red.
        self.colors = {
            "red": (0, 0, 255),
            "orange": (0, 127, 255),
            "yellow": (0, 255, 255),
            "green": (0, 255, 0),
            "blue": (255, 0, 0),
            "indigo": (130, 0, 75),
            "violet": (211, 0, 148),
        }

        # Composition: this application contains two tracker objects.
        self.pose_tracker = PoseTracker()
        self.hand_tracker = HandTracker()
        self.camera = cv.VideoCapture(0)
        self.close_gap = 0.5  # Half a shoulder width: hands need not touch.
        self.ready_to_pull = False
        self.last_wrist_pair = None

    # Convert normalized x/y coordinates into integer screen coordinates.
    def to_pixels(self, positions, width, height):
        pixels = positions * [width, height]
        return pixels.astype(int)

    # Draw one filled circle at each supplied pixel position.
    def draw_points(self, frame, points, color, radius=8):
        for point in points:
            cv.circle(frame, tuple(point), radius, color, -1)

    # Connect consecutive points: first to second, second to third, and so on.
    def connect_points(self, frame, points, color):
        for i in range(len(points) - 1):
            start = tuple(points[i])
            end = tuple(points[i + 1])

            cv.line(frame, start, end, color, 2)

    # Keep the existing wrist angle calculation and sign convention.
    def wrist_angle(self, start, end):
        dx = start[0] - end[0]
        dy = start[1] - end[1]

        return -1 * np.degrees(np.arctan2(dy, dx))
    def wrist_distance(self, start, end):
        dx = start[0] - end[0]
        dy = start[1] - end[1]

        return np.sqrt(dx**2 + dy**2)
    # This method contains our existing camera and drawing loop.
    def run(self):
        while True:
            success, frame = self.camera.read()  # success tells us whether a frame was read.
            if not success:
                print("Could not read the camera.")
                break

            rgb_frame = cv.cvtColor(frame, cv.COLOR_BGR2RGB)  # MediaPipe expects RGB.
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

            timestamp = int(time.monotonic() * 1000)  # Time in milliseconds for MediaPipe.
            # Send the same frame to both trackers; callbacks store their results.
            self.pose_tracker.detector.detect_async(image, timestamp)
            self.hand_tracker.hand_detector.detect_async(image, timestamp)

            archery_angle = None
            wrist_dist = None
            shoulder_width = None
            self.ready_to_pull = False
            tracking_status = "Tracking paused"
            # Read the latest coordinates stored by the PoseTracker object.
            positions, pose_timestamp = self.pose_tracker.pose_sample
            height, width, _ = frame.shape
            if positions is not None and timestamp - pose_timestamp <= self.hand_tracker.hold_ms:
                pixel_positions = self.to_pixels(positions, width, height)

                # Pose supplies shoulders and elbows; HandTracker supplies wrists.
                self.draw_points(frame, pixel_positions[[11, 12, 13, 14]], self.colors["blue"], radius=12)
                self.connect_points(frame, pixel_positions[[11, 13]], self.colors["green"])
                self.connect_points(frame, pixel_positions[[12, 14]], self.colors["green"])
                shoulder_width = self.wrist_distance(pixel_positions[11], pixel_positions[12])

            sample_time, wrists, both_fresh = self.hand_tracker.wrist_sample
            if timestamp - sample_time <= self.hand_tracker.hold_ms:
                if "Left" in wrists and "Right" in wrists:
                    if both_fresh:
                        # Store both wrists together so an uncertain hand cannot change the distance.
                        self.last_wrist_pair = (np.array([wrists["Left"], wrists["Right"]]), sample_time)
                    tracking_status = "Tracking" if both_fresh else "Holding last position"

            if self.last_wrist_pair is not None:
                pair, pair_time = self.last_wrist_pair
                if timestamp - pair_time <= self.hand_tracker.hold_ms:
                    if not both_fresh or sample_time != pair_time:
                        tracking_status = "Holding last position"
                    wrist_pixels = self.to_pixels(pair, width, height)
                    self.draw_points(frame, wrist_pixels, self.colors["blue"], radius=12)
                    self.connect_points(frame, wrist_pixels, self.colors["red"])
                    archery_angle = round(self.wrist_angle(wrist_pixels[0], wrist_pixels[1]), 2)
                    wrist_dist = round(self.wrist_distance(wrist_pixels[0], wrist_pixels[1]), 2)

                    if shoulder_width is not None and shoulder_width > 1:
                        self.connect_points(frame, [pixel_positions[13], wrist_pixels[0]], self.colors["green"])
                        self.connect_points(frame, [pixel_positions[14], wrist_pixels[1]], self.colors["green"])
                        # Only a fresh pair can signal that the hands are close enough.
                        if both_fresh and sample_time == pair_time:
                            self.ready_to_pull = wrist_dist / shoulder_width <= self.close_gap
                            if self.ready_to_pull:
                                tracking_status = "Ready to pull"
                else:
                    self.last_wrist_pair = None
                    tracking_status = "Tracking paused"

            mirrored_frame = cv.flip(frame, 1)  # Mirror the display horizontally.
            height, width = mirrored_frame.shape[:2]
            # Read the latest labels stored by the HandTracker object.
            labels = self.hand_tracker.hand_labels

            for hand in labels:
                # Match the original landmark coordinates to the mirrored display.
                x = width - 1 - int(hand["x"] * width)
                y = int(hand["y"] * height)

                #express which hand is right and which hand is left, 
                cv.putText(
                    mirrored_frame,
                    hand["label"],
                    (x, y),
                    cv.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    self.colors["green"],
                    2
                )

                #express whether the hand is open or closed
                cv.putText(
                    mirrored_frame,
                    hand["state"],
                    (x, y + 25),
                    cv.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    self.colors["yellow"],
                    2
                )

            # Display the archery angle and wrist distance on the mirrored frame if they are available.
            if archery_angle is not None:
                cv.putText(
                    mirrored_frame,
                    f"Archery Angle: {archery_angle}",
                    (30, 30),
                    cv.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    self.colors["red"],
                    2
                )

            if wrist_dist is not None:
                cv.putText(
                    mirrored_frame,
                    f"Wrist Distance: {wrist_dist}",
                    (30, 60),
                    cv.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    self.colors["orange"],
                    2
                )

            cv.putText(
                mirrored_frame, tracking_status, (30, 90),
                cv.FONT_HERSHEY_SIMPLEX, 0.8, self.colors["yellow"], 2
            )

            cv.imshow("Live camera", mirrored_frame)

            if cv.waitKey(1) & 0xFF == ord("q"):  # Press q to quit.
                break

        # Release both detectors and the camera when the loop ends.
        self.pose_tracker.detector.close()
        self.hand_tracker.hand_detector.close()
        self.camera.release()
        cv.destroyAllWindows()


# Start only when this file is run directly.
if __name__ == "__main__":
    tracker = ArcherTracker()  # Create the application and its tracker objects.
    tracker.run()              # Call the method that starts the camera loop.
