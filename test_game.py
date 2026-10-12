"""Run: ../.venv/bin/python -m unittest discover -s . -p 'test_game.py' -v

No webcam or model initialization. These check scoring, release safety and the
actual SDL event flow, including the final arrow and menu/restart actions.
"""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
from types import SimpleNamespace
from unittest.mock import Mock, patch
import math
import unittest
import queue
from dataclasses import FrozenInstanceError
import numpy as np
import pygame
from physics import (Shot, Score_Calculator, Trajectory, score_height, GRAVITY,
                     Target_Distance, Archer_Height, TARGET_HEIGHT, TARGET_RADIUS, strength_to_speed)
from game_mechanics import GameRound, STATE_MENU, STATE_PLAY, STATE_CALIBRATE, STATE_FINISH
from controls import Calibration, InputController
from camera import CameraSession
from main import Archidon, load_ui
from renderer import world_to_screen, FIELD, PIXELS_PER_METRE
from viewport import WorldCamera


def measurement(stamp=1000, gap=0.5, angle=0.0, state='Closed'):
    return {'stamp': stamp, 'gap': gap, 'angle': angle, 'scale': 0.3, 'state': state}


def bullseye_angle(strength=.75):
    """Low ballistic arc toward the centre, independent of field size."""
    speed = strength_to_speed(strength)
    distance = Target_Distance
    rise = TARGET_HEIGHT - Archer_Height
    discriminant = speed**4 - GRAVITY * (GRAVITY * distance**2 + 2 * rise * speed**2)
    return math.degrees(math.atan((speed**2 - math.sqrt(discriminant)) / (GRAVITY * distance)))


def tracker_pair(pose=None, stamp=1000, wrists=None, fresh=True, state='Closed'):
    return (SimpleNamespace(pose_sample=(pose, stamp)),
            SimpleNamespace(game_sample=(stamp, wrists or {}, fresh, {'Right': state})))


def calibrated():
    game = GameRound()
    controls = InputController(game.shoot)
    controls.calibration.step = 3
    controls.calibration.rest_gap = 0.5
    controls.calibration.full_gap = 1.5
    controls.calibration.neutral_angle = 0.0
    return controls, game


class PhysicsTests(unittest.TestCase):
    def test_original_score_ring_boundaries_are_inclusive(self):
        for delta, expected in ((0, 50), (.2, 50), (.20001, 25), (.4, 25),
                                (.40001, 15), (.5, 15), (.50001, 0)):
            for sign in (-1, 1):
                self.assertEqual(score_height(1 + sign * delta), expected)

    def test_polynomial_matches_flight_and_preview_for_up_level_down(self):
        for angle in (-30, 0, 35):
            shot = Shot(12, angle)
            a, b, c = Trajectory(12, angle)
            for seconds in (0, shot.end_time / 2, shot.end_time):
                x, y = shot.position(seconds)
                self.assertAlmostEqual(y, a*x*x + b*x + c)
            self.assertEqual(shot.preview()[-1], shot.position(shot.end_time))
            end_x, end_y = shot.preview()[-1]
            self.assertTrue(abs(end_x - Target_Distance) < 1e-8 or abs(end_y) < 1e-8)
            start = world_to_screen(shot.position(0))
            later = world_to_screen(shot.position(.01))
            self.assertLess(later.x, start.x)
            self.assertEqual(later.y < start.y, angle > 0)

    def test_invalid_or_vertical_shots_do_not_score(self):
        for speed, angle in ((0, 0), (12, 90), (12, -90), (12, 180), (float('nan'), 20), (12, float('nan'))):
            self.assertEqual(Score_Calculator(speed, angle), 0)

    def test_preview_cannot_continue_below_ground(self):
        shot = Shot(6, -30)
        self.assertFalse(shot.reaches_target)
        self.assertAlmostEqual(shot.preview()[-1][1], 0)
        self.assertTrue(all(y >= -1e-8 for x, y in shot.preview()))

    def test_actual_endpoint_scores_the_same_as_original_calculator(self):
        game = GameRound()
        self.assertTrue(game.shoot(.75, bullseye_angle()))
        game.update(5)
        self.assertEqual(game.score, Score_Calculator(strength_to_speed(.75), bullseye_angle()))
        self.assertEqual(game.score, 50)

    def test_large_and_small_frame_steps_have_identical_impacts(self):
        for strength, angle in ((.75, 20), (.15, -30), (1, 70), (1, 90), (1, -90)):
            small, large = GameRound(), GameRound()
            for game in (small, large):
                game.shoot(strength, angle)
            for _ in range(600):
                small.update(.01)
            large.update(6)
            self.assertEqual(small.impacts, large.impacts)
            self.assertEqual(small.score, large.score)
            self.assertEqual(small.history, large.history)

    def test_round_finishes_only_after_third_impact_and_cannot_score_twice(self):
        game = GameRound()
        for i in range(3):
            self.assertTrue(game.shoot(.75, bullseye_angle()))
            self.assertFalse(game.shoot(.75, bullseye_angle()))
            self.assertFalse(game.finished)
            game.update(3)
        self.assertTrue(game.finished)
        self.assertEqual(game.score, 150)
        game.update(3)
        self.assertEqual(game.score, 150)
        self.assertFalse(game.shoot(.75, bullseye_angle()))

    def test_invalid_pull_does_not_consume_an_arrow(self):
        game = GameRound()
        for strength, angle in ((0, 20), (float('nan'), 20), (.8, float('inf'))):
            self.assertFalse(game.shoot(strength, angle))
        self.assertEqual(game.shots, 0)


    def test_prediction_and_launch_clamp_the_same_extreme_aim(self):
        for strength, angle in ((2, 120), (.8, -120), (.8, 85), (.8, -85)):
            game = GameRound()
            prediction = game.prediction(strength, angle)
            self.assertTrue(game.shoot(strength, angle))
            self.assertEqual(game.arrow.shot, prediction)
            self.assertEqual(prediction.angle, max(-90, min(90, angle)))
            self.assertLessEqual(prediction.speed, strength_to_speed(1))

    def test_distance_requires_a_longer_flight_and_full_pull_has_usable_range(self):
        self.assertEqual(Target_Distance, 35.0)
        self.assertEqual(strength_to_speed(0), 12.0)
        self.assertEqual(strength_to_speed(1), 24.0)
        shot = Shot(strength_to_speed(.75), bullseye_angle())
        self.assertTrue(shot.reaches_target)
        self.assertGreater(shot.end_time, 1.5)
        self.assertAlmostEqual(shot.position(shot.end_time)[1], TARGET_HEIGHT)

    def test_finished_paths_remain_exact_after_the_next_arrow_launches(self):
        game = GameRound()
        self.assertTrue(game.shoot(.75, bullseye_angle()))
        first_path = tuple(game.arrow.path)
        game.update(5)
        self.assertEqual(len(game.history), 1)
        completed = game.last_shot
        self.assertEqual(completed.number, 1)
        self.assertEqual(completed.path, first_path)
        self.assertEqual(completed.path[0], (0, Archer_Height))
        self.assertEqual(completed.path[-1], completed.impact.position)
        self.assertEqual(completed.impact, game.impacts[0])
        with self.assertRaises(FrozenInstanceError):
            completed.number = 7
        self.assertTrue(game.shoot(.8, 35))
        self.assertIs(game.last_shot, completed)
        game.update(5)
        self.assertEqual([record.number for record in game.history], [1, 2])
        self.assertEqual(game.history[0].path, first_path)
        self.assertIs(game.last_shot, game.history[1])
        game.reset()
        self.assertEqual(game.history, [])
        self.assertIsNone(game.last_shot)

    def test_trail_never_includes_a_future_position_and_ends_at_live_arrow(self):
        game = GameRound()
        game.shoot(.75, bullseye_angle())
        game.update(.37)
        flight = game.arrow
        self.assertEqual(flight.trail[0], flight.shot.position(0))
        self.assertEqual(flight.trail[-1], flight.position)
        self.assertTrue(all(x <= flight.position[0] for x, y in flight.trail))
        self.assertLess(len(flight.trail), len(flight.path))

    def test_invalid_frame_time_cannot_poison_flight_or_award_points(self):
        game = GameRound()
        game.shoot(.75, bullseye_angle())
        for dt in (float('nan'), float('inf'), float('-inf'), -1):
            game.update(dt)
            self.assertIsNotNone(game.arrow)
            self.assertEqual(game.arrow.elapsed, 0)
            self.assertEqual(game.score, 0)
        game.update(5)
        self.assertEqual(game.score, 50)

    def test_exact_vertical_predictions_and_flights_land_without_horizontal_drift(self):
        for angle in (-90, 90):
            with self.subTest(angle=angle):
                game = GameRound()
                prediction = game.prediction(1, angle)
                self.assertEqual(prediction.vx, 0)
                self.assertTrue(math.isfinite(prediction.end_time))
                self.assertFalse(prediction.reaches_target)
                self.assertTrue(all(x == 0 and math.isfinite(y) for x, y in prediction.preview()))
                self.assertAlmostEqual(prediction.preview()[-1][1], 0)
                with self.assertRaisesRegex(ValueError, 'vertical'):
                    Trajectory(24, angle)
                self.assertTrue(game.shoot(1, angle))
                self.assertEqual(game.arrow.shot, prediction)
                game.update(6)
                self.assertIsNone(game.arrow)
                self.assertEqual(game.score, 0)
                self.assertEqual(game.last_shot.path[-1], game.last_shot.impact.position)
                self.assertEqual(game.last_shot.impact.position[0], 0)
                self.assertAlmostEqual(game.last_shot.impact.position[1], 0)
                self.assertFalse(game.last_shot.impact.on_target)

    def test_nonfinite_prediction_spacing_is_rejected(self):
        shot = Shot(24, 35)
        for spacing in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                shot.preview(spacing)


class ViewportTests(unittest.TestCase):
    def test_far_target_is_completely_hidden_from_the_initial_aim_view(self):
        camera = WorldCamera()
        self.assertTrue(camera.can_shoot)
        target = world_to_screen((Target_Distance, TARGET_HEIGHT))
        self.assertLess(target.x + TARGET_RADIUS * PIXELS_PER_METRE, FIELD.left)

    def test_scenery_follows_a_high_arrow_and_keeps_it_in_the_play_area(self):
        game, camera = GameRound(), WorldCamera()
        game.shoot(1, 35)
        for _ in range(240):
            game.update(1 / 60)
            camera.update(1 / 60, game.arrow, game.impacts[-1] if game.impacts else None)
            if game.arrow is None:
                break
            position = world_to_screen(game.arrow.position, camera.pan_x, camera.pan_y)
            self.assertTrue(FIELD.collidepoint(position), (game.arrow.position, position))
            self.assertFalse(camera.can_shoot)
        self.assertGreater(camera.pan_x, 20)
        self.assertGreater(camera.pan_y, 0)
        self.assertEqual(camera.phase, WorldCamera.IMPACT)

    def test_vertical_arrow_stays_visible_through_apex_and_camera_returns(self):
        game, camera = GameRound(), WorldCamera()
        game.shoot(1, 90)
        highest_pan = 0
        for _ in range(480):
            game.update(1 / 60)
            camera.update(1 / 60, game.arrow, game.impacts[-1] if game.impacts else None)
            highest_pan = max(highest_pan, camera.pan_y)
            if game.arrow is not None:
                location = world_to_screen(game.arrow.position, camera.pan_x, camera.pan_y)
                self.assertTrue(FIELD.collidepoint(location), location)
                self.assertEqual(camera.pan_x, 0)
            elif camera.can_shoot:
                break
        self.assertGreater(highest_pan, 20)
        self.assertTrue(camera.can_shoot)
        self.assertEqual((camera.pan_x, camera.pan_y), (0, 0))
        self.assertEqual(game.last_shot.impact.position[0], 0)
        self.assertEqual(game.score, 0)

    def test_impact_holds_then_returns_even_when_the_same_result_is_repeated(self):
        camera = WorldCamera()
        impact = SimpleNamespace(position=(Target_Distance, TARGET_HEIGHT))
        camera.update(0, None, impact)
        start_pan = camera.pan_x
        self.assertGreater(start_pan, 20)
        self.assertEqual(camera.phase, WorldCamera.IMPACT)
        self.assertFalse(camera.can_shoot)
        camera.update(.4, None, impact)
        self.assertEqual(camera.pan_x, start_pan)
        camera.update(.4, None, impact)
        self.assertEqual(camera.phase, WorldCamera.RETURN)
        camera.update(.45, None, impact)
        self.assertAlmostEqual(camera.pan_x, start_pan / 2)
        camera.update(.45, None, impact)
        self.assertTrue(camera.can_shoot)
        self.assertEqual((camera.pan_x, camera.pan_y), (0, 0))
        camera.update(2, None, impact)
        self.assertEqual(camera.phase, WorldCamera.AIM)

    def test_fixed_follow_focus_and_full_return_are_frame_rate_independent(self):
        small, large = WorldCamera(), WorldCamera()
        flight = SimpleNamespace(position=(20, 9))
        for _ in range(10):
            small.update(.1, flight)
        large.update(1, flight)
        self.assertAlmostEqual(small.pan_x, large.pan_x)
        self.assertAlmostEqual(small.pan_y, large.pan_y)
        impact = SimpleNamespace(position=(Target_Distance, TARGET_HEIGHT))
        for _ in range(17):
            small.update(.1, None, impact)
        large.update(1.7, None, impact)
        self.assertTrue(small.can_shoot)
        self.assertTrue(large.can_shoot)
        self.assertEqual((small.pan_x, small.pan_y), (large.pan_x, large.pan_y))

    def test_reset_restores_aim_and_invalid_frame_times_do_not_shift_scenery(self):
        camera = WorldCamera()
        flight = SimpleNamespace(position=(20, 9))
        camera.update(.5, flight)
        before = (camera.pan_x, camera.pan_y, camera.phase)
        for dt in (-1, float('nan'), float('inf')):
            camera.update(dt, flight)
            self.assertEqual((camera.pan_x, camera.pan_y, camera.phase), before)
        camera.reset()
        self.assertTrue(camera.can_shoot)
        self.assertEqual((camera.pan_x, camera.pan_y), (0, 0))


class CalibrationAndReleaseTests(unittest.TestCase):
    def test_three_calibration_stages_normalize_pull_and_neutral(self):
        calibration = Calibration()
        for gap, angle in ((1, 0), (.5, 0), (1.5, 10)):
            calibration.start_capture()
            for stamp in range(1000, 2400, 100):
                calibration.update(measurement(stamp, gap, angle))
        self.assertTrue(calibration.ready())
        self.assertEqual(calibration.normalize(measurement(gap=1, angle=55)), (.5, .5))

    def test_calibrated_aim_covers_both_exact_vertical_limits(self):
        controls, game = calibrated()
        for angle in (-90, -75, 75, 90):
            strength, direction = controls.calibration.normalize(measurement(gap=1.3, angle=angle))
            self.assertAlmostEqual(strength, .8)
            self.assertAlmostEqual(direction, angle / 90)
        self.assertEqual(controls.calibration.AIM_RANGE, 90)
        for angle in (-90, 90):
            controls, game = calibrated()
            controls.update_controls(measurement(1000, 1.3, angle))
            self.assertEqual(controls.aim_degrees, angle)
            self.assertTrue(controls.drawing)

    def test_a_first_closed_hand_can_draw_at_a_wide_gap_and_release_held_aim(self):
        controls, game = calibrated()
        controls.update_controls(measurement(1000, 1.3, 55))
        self.assertTrue(controls.drawing)
        self.assertAlmostEqual(controls.strength, .8)
        expected = controls.last_draw
        controls.update_controls(measurement(1100, .6, -25, 'Open'))
        self.assertEqual(game.shots, 0)
        controls.update_controls(measurement(1200, .6, -25, 'Open'))
        self.assertEqual(game.shots, 1)
        self.assertAlmostEqual(game.arrow.shot.speed, strength_to_speed(expected[0]))
        self.assertAlmostEqual(game.arrow.shot.angle, expected[1])

    def test_the_next_shot_starts_closed_at_a_wide_gap_without_recalibration(self):
        controls, game = calibrated()
        controls.update_controls(measurement(1000, 1.3, 25))
        controls.update_controls(measurement(1100, 1.3, state='Open'))
        controls.update_controls(measurement(1200, 1.3, state='Open'))
        self.assertEqual(game.shots, 1)
        game.update(6)
        controls.arrow = game.arrow
        controls.update_controls(measurement(2000, 1.2, 65))
        self.assertTrue(controls.drawing)
        expected = controls.last_draw
        self.assertGreater(expected[0], .69)
        self.assertGreater(expected[1], 64)
        controls.update_controls(measurement(2100, 1.2, state='Open'))
        controls.update_controls(measurement(2200, 1.2, state='Open'))
        self.assertEqual(game.shots, 2)
        self.assertAlmostEqual(game.arrow.shot.angle, expected[1])
        self.assertAlmostEqual(game.arrow.shot.speed, strength_to_speed(expected[0]))
        self.assertTrue(controls.calibration.ready())
        self.assertEqual((controls.calibration.rest_gap, controls.calibration.full_gap), (.5, 1.5))

    def test_closed_at_any_gap_can_resume_after_loss_but_open_cannot_release_old_draw(self):
        controls, game = calibrated()
        controls.update_controls(measurement(1000, 1.3, 15))
        self.assertTrue(controls.drawing)
        controls.update_controls(None, 2000)
        self.assertFalse(controls.drawing)
        for stamp, state in ((2100, 'Open'), (2200, 'Unknown'), (2300, 'Open'), (2400, 'Open')):
            controls.update_controls(measurement(stamp, 1.3, state=state))
        self.assertEqual(game.shots, 0)
        controls.update_controls(measurement(2500, 1.2, 70))
        self.assertTrue(controls.drawing)
        expected = controls.last_draw
        self.assertGreater(expected[1], 30)
        controls.update_controls(measurement(2600, 1.2, state='Open'))
        controls.update_controls(measurement(2700, 1.2, state='Open'))
        self.assertEqual(game.shots, 1)
        self.assertAlmostEqual(game.arrow.shot.angle, expected[1])

    def test_repeated_results_cannot_complete_calibration(self):
        calibration = Calibration()
        calibration.start_capture()
        for _ in range(100):
            calibration.update(measurement())
        self.assertEqual(calibration.step, 0)

    def test_first_calibration_finishes_with_slow_or_fast_pose_callbacks(self):
        # The old 1.6 s / 60-sample window could never finish at 2, 4 or 60 Hz.
        for fps in (1, 2, 4, 5, 15, 30, 60, 90):
            with self.subTest(fps=fps):
                calibration = Calibration()
                calibration.start_capture()
                for tick in range(301):
                    now = 1000 + round(tick * 1000 / 60)
                    result_index = int(tick * fps / 60)
                    sample_stamp = 1000 + round(result_index * 1000 / fps)
                    # The UI repeats a pose, and sometimes receives no fresh pose.
                    sample = measurement(sample_stamp) if now - sample_stamp <= 400 else None
                    calibration.update(sample, now)
                    if calibration.step:
                        break
                self.assertEqual(calibration.step, 1)
                self.assertAlmostEqual(calibration.camera_scale, .3)

    def test_capture_reports_missing_pose_reason_and_restarts_after_long_loss(self):
        calibration = Calibration()
        calibration.start_capture()
        calibration.update(measurement(1000))
        calibration.update(None, 1700, 'Move closer and face the camera.')
        self.assertEqual(len(calibration.samples), 1)
        self.assertEqual(calibration.message, 'Move closer and face the camera.')
        calibration.update(None, 2700)
        self.assertEqual(calibration.samples, [])

    def test_first_calibration_only_needs_visible_shoulders_and_accepts_setup_delay(self):
        controls, game = calibrated()
        controls.calibration = Calibration()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        controls.hand_tracker = SimpleNamespace(game_sample=(0, {}, False, {}))
        for shoulder_width in (.1, .3, .6):
            pose = np.full((33, 2), .5)
            pose[11], pose[12] = [.5 - shoulder_width / 2, .35], [.5 + shoulder_width / 2, .35]
            controls.pose_tracker = SimpleNamespace(pose_sample=(pose, 1000))
            sample, message = controls.read_measurement(frame, 1700, controls.pose_tracker, controls.hand_tracker)
            self.assertIsNotNone(sample)
            self.assertEqual(sample['stamp'], 1000)
        controls.calibration.step = 1
        sample, message = controls.read_measurement(frame, 1700, controls.pose_tracker, controls.hand_tracker)
        self.assertIsNone(sample)
        self.assertIn('No fresh shoulder result', message)

    def test_close_pull_open_fires_once_with_last_closed_aim(self):
        controls, game = calibrated()
        controls.update_controls(measurement(1000, .5))
        controls.update_controls(measurement(1100, 1.3, 20))
        expected = (controls.strength, controls.aim_degrees)
        controls.update_controls(measurement(1200, .7, -20, 'Open'))
        self.assertEqual(game.shots, 0)
        controls.update_controls(measurement(1300, .7, -20, 'Open'))
        self.assertEqual(game.shots, 1)
        self.assertAlmostEqual(game.arrow.shot.speed, strength_to_speed(expected[0]))
        self.assertAlmostEqual(game.arrow.shot.angle, expected[1])
        controls.arrow = game.arrow
        controls.update_controls(measurement(1400, .7, -20, 'Open'))
        self.assertEqual(game.shots, 1)

    def test_dropout_does_not_fire_and_long_dropout_cancels_draw(self):
        for return_stamp, expected in ((1300, 1), (2100, 0)):
            controls, game = calibrated()
            controls.update_controls(measurement(1000, .5))
            controls.update_controls(measurement(1100, 1.3))
            controls.update_controls(None, return_stamp - 50)
            self.assertEqual(game.shots, 0)
            controls.update_controls(measurement(return_stamp, 1.3, state='Open'))
            controls.update_controls(measurement(return_stamp + 100, 1.3, state='Open'))
            self.assertEqual(game.shots, expected)

    def test_one_false_open_and_unknown_gesture_cannot_release(self):
        controls, game = calibrated()
        controls.update_controls(measurement(1000, .5))
        controls.update_controls(measurement(1100, 1.3))
        controls.update_controls(measurement(1200, 1.3, state='Open'))
        controls.update_controls(measurement(1250, 1.3, state='Closed'))
        controls.update_controls(measurement(1900, 1.3, state='Unknown'))
        controls.update_controls(measurement(2000, 1.3, state='Open'))
        controls.update_controls(measurement(2100, 1.3, state='Open'))
        self.assertEqual(game.shots, 0)

    def test_measurements_use_only_fresh_pairs_and_raise_bow_to_aim_up(self):
        controls, game = calibrated()
        pose = np.full((33, 2), .5)
        pose[11], pose[12] = [.35, .35], [.65, .35]
        wrists = {'Left': np.array([.35, .4]), 'Right': np.array([.65, .6])}
        controls.pose_tracker = SimpleNamespace(pose_sample=(pose, 1000))
        controls.hand_tracker = SimpleNamespace(game_sample=(1000, wrists, True, {'Right': 'Closed'}))
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        sample, message = controls.read_measurement(frame, 1010, controls.pose_tracker, controls.hand_tracker)
        self.assertGreater(sample['angle'], 0)
        self.assertEqual(sample['state'], 'Closed')
        sample, _ = controls.read_measurement(frame, 1500, controls.pose_tracker, controls.hand_tracker)
        self.assertIsNone(sample)
        controls.hand_tracker.game_sample = (1000, wrists, False, {})
        sample, _ = controls.read_measurement(frame, 1010, controls.pose_tracker, controls.hand_tracker)
        self.assertIsNone(sample)

    def test_old_measurement_cannot_resume_or_release_a_draw(self):
        controls, game = calibrated()
        controls.update_controls(measurement(1000, .5), 1000)
        controls.update_controls(measurement(1100, 1.3), 1100)
        self.assertTrue(controls.drawing)
        for state in ('Open', 'Closed', 'Open'):
            controls.update_controls(measurement(1200, 1.3, state=state), 1800)
        self.assertEqual(game.shots, 0)
        self.assertFalse(controls.controls_clear)
        self.assertFalse(controls.drawing)
        self.assertIsNone(controls.last_draw)

    def test_future_worker_measurement_cannot_start_a_draw(self):
        controls, game = calibrated()
        controls.update_controls(measurement(1100, .5), 1000)
        self.assertFalse(controls.controls_clear)
        self.assertFalse(controls.drawing)
        self.assertEqual(game.shots, 0)

    def test_manual_and_gesture_release_are_blocked_during_flight(self):
        controls, game = calibrated()
        controls.update_controls(measurement(1000, .5))
        controls.update_controls(measurement(1100, 1.3))
        game.shoot(.75, bullseye_angle())
        controls.arrow = game.arrow
        self.assertFalse(controls.shoot(.75, bullseye_angle()))
        self.assertFalse(controls.drawing)
        controls.update_controls(measurement(1200, .5))
        controls.update_controls(measurement(1300, 1.3))
        self.assertFalse(controls.drawing)
        self.assertEqual(game.shots, 1)

    def test_uncalibrated_controls_wait_instead_of_normalizing_missing_range(self):
        controller = InputController(Mock())
        controller.update_controls(measurement())
        self.assertFalse(controller.drawing)
        self.assertFalse(controller.controls_clear)
        controller.on_shot.assert_not_called()

    def test_camera_bridge_reads_latest_snapshot_and_rejects_stale_results(self):
        controls, game = calibrated()
        controls.calibration.step = 0
        session = CameraSession.__new__(CameraSession)
        session.controller = controls
        session.pose_tracker = SimpleNamespace(pose_sample=(None, 0))
        session.hand_tracker = SimpleNamespace(game_sample=(0, {}, False, {}))
        session.rgb = np.zeros((480, 640, 3), dtype=np.uint8)
        session.received_frame = False
        session.process = Mock()
        session.process.is_alive.return_value = True
        session.output = queue.Queue()
        controls.pose_tracker = SimpleNamespace(pose_sample=(None, 0))
        controls.hand_tracker = SimpleNamespace(game_sample=(0, {}, False, {}))
        pose = np.full((33, 2), .5)
        pose[11], pose[12] = [.35, .35], [.65, .35]
        for stamp in (900, 1000):
            session.output.put({'type': 'frame', 'rgb': session.rgb,
                                'pose': (pose, stamp), 'hands': (stamp, {}, False, {})})
        with patch('camera.monotonic_seconds', return_value=1.01):
            rgb, sample, message, stamp = session.read()
        self.assertEqual(sample['stamp'], 1000)
        with patch('camera.monotonic_seconds', return_value=1.5):
            rgb, sample, message, stamp = session.read()
        self.assertIsNotNone(sample)  # Step 1 accepts a slower pose callback.
        with patch('camera.monotonic_seconds', return_value=2.1):
            rgb, sample, message, stamp = session.read()
        self.assertIsNone(sample)

    def test_camera_bridge_reports_startup_and_frame_watchdog_failures(self):
        def make_session():
            controls, game = calibrated()
            session = CameraSession.__new__(CameraSession)
            session.controller = controls
            session.rgb = np.zeros((240, 320, 3), dtype=np.uint8)
            session.pose_tracker, session.hand_tracker = tracker_pair()
            session.received_frame, session.closed = False, False
            session.started_at, session.last_frame_stamp = 1000, None
            session.process = Mock()
            session.process.is_alive.return_value = True
            session.output = queue.Queue()
            return session

        session = make_session()
        with patch('camera.monotonic_seconds', return_value=1.01):
            rgb, sample, message, stamp = session.read()
        self.assertIsNone(sample)
        self.assertIn('Starting', message)
        with patch('camera.monotonic_seconds', return_value=21.001):
            with self.assertRaisesRegex(RuntimeError, 'startup timed out'):
                session.read()
        session = make_session()
        session.output.put({'type': 'frame', 'stamp': 2000, 'rgb': session.rgb,
                            'pose': (None, 0), 'hands': (0, {}, False, {})})
        with patch('camera.monotonic_seconds', return_value=2.001):
            session.read()
        with patch('camera.monotonic_seconds', return_value=5.001):
            with self.assertRaisesRegex(RuntimeError, 'frames stopped'):
                session.read()

    def test_camera_start_failure_closes_queue_and_cannot_leak_a_worker(self):
        context = Mock()
        context.Process.return_value.start.side_effect = RuntimeError('cannot start')
        with patch('camera.multiprocessing.get_context', return_value=context):
            with self.assertRaisesRegex(RuntimeError, 'cannot start'):
                CameraSession(InputController(Mock()))
        context.Event.return_value.set.assert_called_once()
        context.Queue.return_value.cancel_join_thread.assert_called_once()
        context.Queue.return_value.close.assert_called_once()
        context.Process.return_value.join.assert_not_called()

    def test_camera_read_after_close_reports_restart_instruction(self):
        session = CameraSession.__new__(CameraSession)
        session.closed = True
        with self.assertRaisesRegex(RuntimeError, 'closed'):
            session.read()

    def test_camera_bridge_stops_a_blocked_worker_and_can_close_twice(self):
        controls, game = calibrated()
        session = CameraSession.__new__(CameraSession)
        session.controller, session.closed = controls, False
        session.process, session.stop, session.output = Mock(), Mock(), Mock()
        session.process.is_alive.return_value = True
        session.close()
        session.close()
        session.process.terminate.assert_called_once()
        session.output.close.assert_called_once()


class WindowFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        load_ui()
        pygame.display.init()
        pygame.font.init()
        cls.screen = pygame.display.set_mode((1280, 800))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        pygame.event.clear()
        self.app = Archidon(self.screen)

    def tearDown(self):
        self.app.close_camera()

    def event(self, kind, **attributes):
        pygame.event.post(pygame.event.Event(kind, **attributes))
        self.app.events()

    def advance_until_ready(self):
        for _ in range(480):
            self.app.update(1 / 60)
            if self.app.game.arrow is None and self.app.world_camera.can_shoot:
                return
        self.fail('Arrow flight and camera return did not finish within eight seconds.')

    def advance_to_impact(self):
        for _ in range(240):
            self.app.update(1 / 60)
            if self.app.game.arrow is None:
                return
        self.fail('Arrow did not land within four seconds.')

    def test_space_and_mouse_drag_wait_for_camera_return_after_impact(self):
        self.app.start_mouse()
        self.assertTrue(self.app.shoot(.75, bullseye_angle()))
        self.advance_to_impact()
        self.assertFalse(self.app.world_camera.can_shoot)
        self.app.update(.8)
        self.assertEqual(self.app.world_camera.phase, WorldCamera.RETURN)
        self.event(pygame.KEYDOWN, key=pygame.K_SPACE)
        self.event(pygame.MOUSEBUTTONDOWN, button=1, pos=(600, 400))
        self.event(pygame.MOUSEMOTION, pos=(780, 375))
        self.event(pygame.MOUSEBUTTONUP, button=1, pos=(780, 375))
        self.assertEqual(self.app.game.shots, 1)
        self.assertIsNone(self.app.drag_start)
        self.advance_until_ready()
        self.event(pygame.KEYDOWN, key=pygame.K_SPACE)
        self.assertEqual(self.app.game.shots, 2)

    def test_gesture_draw_during_camera_return_cannot_queue_the_next_shot(self):
        self.app.start_mouse()
        self.app.shoot(.75, bullseye_angle())
        self.advance_to_impact()
        controls, unused = calibrated()
        controls.on_shot = self.app.shoot
        self.app.mode, self.app.controller = 'camera', controls
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        camera = Mock()
        camera.preview.return_value = frame
        camera.read.side_effect = [
            (frame, measurement(stamp, gap, state=state), 'Tracking OK', stamp)
            for stamp, gap, state in ((1000, .5, 'Closed'), (1100, 1.3, 'Closed'),
                                      (1200, 1.3, 'Open'), (1300, 1.3, 'Open'))
        ]
        self.app.camera = camera
        for _ in range(4):
            self.app.update(.1)
            self.assertFalse(controls.drawing)
        self.assertEqual(self.app.game.shots, 1)
        self.assertIsNone(controls.last_draw)

    def test_long_frame_landing_spends_only_post_impact_time_on_camera_hold(self):
        self.app.start_mouse()
        self.assertTrue(self.app.shoot(.75, bullseye_angle()))
        duration = self.app.game.arrow.shot.end_time
        after_impact = .1
        self.app.update(duration + after_impact)
        self.assertIsNone(self.app.game.arrow)
        self.assertEqual(len(self.app.game.history), 1)
        self.assertEqual(self.app.world_camera.phase, WorldCamera.IMPACT)
        self.assertFalse(self.app.world_camera.can_shoot)
        # Only the .1 s after landing belongs to the camera's .8 s hold.
        self.app.update(WorldCamera.IMPACT_SECONDS - after_impact - .01)
        self.assertEqual(self.app.world_camera.phase, WorldCamera.IMPACT)
        # One later large frame may consume the final hold and complete return.
        self.app.update(WorldCamera.RETURN_SECONDS + .02)
        self.assertTrue(self.app.world_camera.can_shoot)
        self.assertEqual(self.app.world_camera.phase, WorldCamera.AIM)
        self.assertEqual((self.app.world_camera.pan_x, self.app.world_camera.pan_y), (0, 0))
        self.assertEqual(self.app.game.score, 50)
        self.assertEqual(len(self.app.game.history), 1)

    def test_finish_waits_for_the_last_landing_to_be_seen_and_camera_return(self):
        self.app.start_mouse()
        for _ in range(2):
            self.assertTrue(self.app.shoot(.75, bullseye_angle()))
            self.advance_until_ready()
        self.assertTrue(self.app.shoot(.75, bullseye_angle()))
        self.advance_to_impact()
        self.assertTrue(self.app.game.finished)
        self.assertFalse(self.app.world_camera.can_shoot)
        self.assertEqual(self.app.state, STATE_PLAY)
        self.advance_until_ready()
        self.assertEqual(self.app.state, STATE_FINISH)
        self.assertEqual(self.app.game.score, 150)

    def test_renderer_keeps_both_completed_paths_visible_for_the_next_aim(self):
        self.app.start_mouse()
        for strength, angle in ((.75, bullseye_angle()), (.8, 35)):
            self.app.shoot(strength, angle)
            self.advance_until_ready()
        with patch.object(self.app.renderer, 'draw_path', wraps=self.app.renderer.draw_path) as draw_path:
            self.app.draw()
        drawn_paths = [call.args[0] for call in draw_path.call_args_list]
        self.assertEqual(len(self.app.game.history), 2)
        for completed in self.app.game.history:
            self.assertIn(completed.path, drawn_paths)
        self.assertTrue(self.app.world_camera.can_shoot)

    def test_restart_and_menu_restore_initial_aim_view(self):
        self.app.start_mouse()
        self.app.shoot(.75, bullseye_angle())
        for _ in range(60):
            self.app.update(1 / 60)
        self.assertGreater(self.app.world_camera.pan_x, 0)
        self.event(pygame.KEYDOWN, key=pygame.K_r)
        self.assertTrue(self.app.world_camera.can_shoot)
        self.assertEqual(self.app.world_camera.pan_x, 0)
        self.assertEqual(self.app.game.history, [])
        self.app.shoot(.75, bullseye_angle())
        for _ in range(60):
            self.app.update(1 / 60)
        self.assertGreater(self.app.world_camera.pan_x, 0)
        self.event(pygame.KEYDOWN, key=pygame.K_ESCAPE)
        self.assertEqual(self.app.state, STATE_MENU)
        self.assertEqual(self.app.world_camera.pan_x, 0)

    def test_menu_mouse_button_three_shots_finish_and_restart(self):
        self.app.draw()
        self.event(pygame.MOUSEBUTTONDOWN, button=1, pos=self.app.renderer.buttons['mouse'].center)
        self.assertEqual(self.app.state, STATE_PLAY)
        self.app.angle = bullseye_angle(self.app.strength)
        for i in range(3):
            self.event(pygame.KEYDOWN, key=pygame.K_SPACE)
            self.advance_until_ready()
        self.assertEqual(self.app.state, STATE_FINISH)
        self.assertEqual(self.app.game.score, 150)
        self.app.draw()
        self.event(pygame.MOUSEBUTTONDOWN, button=1, pos=self.app.renderer.buttons['again'].center)
        self.assertEqual(self.app.state, STATE_PLAY)
        self.assertEqual(self.app.game.shots, 0)

    def test_mouse_drag_release_launches_the_displayed_prediction(self):
        self.app.start_mouse()
        self.app.draw()
        self.event(pygame.MOUSEBUTTONDOWN, button=1, pos=(600, 400))
        self.event(pygame.MOUSEMOTION, pos=(780, 375))
        expected = self.app.game.prediction(self.app.strength, self.app.angle)
        self.event(pygame.MOUSEBUTTONUP, button=1, pos=(780, 375))
        self.assertEqual(self.app.game.arrow.shot, expected)

    def test_mouse_can_aim_and_release_both_exact_vertical_directions(self):
        for angle, start, end in ((90, (650, 650), (890, 100)),
                                  (-90, (650, 150), (890, 750))):
            with self.subTest(angle=angle):
                self.app.start_mouse()
                self.app.angle = 0
                self.app.draw()
                self.event(pygame.MOUSEBUTTONDOWN, button=1, pos=start)
                self.event(pygame.MOUSEMOTION, pos=end)
                self.assertEqual(self.app.angle, angle)
                prediction = self.app.game.prediction(self.app.strength, self.app.angle)
                self.app.draw()
                self.event(pygame.MOUSEBUTTONUP, button=1, pos=end)
                self.assertEqual(self.app.game.arrow.shot, prediction)
                self.assertEqual(self.app.game.arrow.shot.vx, 0)
                self.advance_until_ready()
                self.app.draw()
                self.assertEqual(self.app.game.score, 0)
                self.assertEqual(self.app.game.last_shot.impact.position[0], 0)

    def test_webcam_inset_hides_during_vertical_flight_and_returns_when_ready(self):
        self.app.start_mouse()
        controls, unused = calibrated()
        controls.on_shot = self.app.shoot
        self.app.mode, self.app.controller = 'camera', controls
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        camera = Mock()
        camera.read.return_value = (frame, measurement(), 'Tracking OK', 1000)
        camera.preview.return_value = frame
        self.app.camera, self.app.camera_rgb = camera, frame
        with patch.object(self.app.renderer, 'camera', wraps=self.app.renderer.camera) as draw_camera:
            self.app.draw()
            self.assertEqual(draw_camera.call_count, 1)
            self.assertTrue(self.app.shoot(1, 90))
            apex_time = self.app.game.arrow.shot.vy / GRAVITY
            self.app.update(apex_time)
            self.app.draw()
            self.assertEqual(draw_camera.call_count, 1)
            self.advance_until_ready()
            self.app.draw()
            self.assertEqual(draw_camera.call_count, 2)

    def test_exact_vertical_apex_can_render_with_zero_instantaneous_velocity(self):
        self.app.start_mouse()
        self.assertTrue(self.app.shoot(1, 90))
        apex_time = self.app.game.arrow.shot.vy / GRAVITY
        self.app.update(apex_time)
        self.assertIsNotNone(self.app.game.arrow)
        self.assertEqual(self.app.game.arrow.velocity[0], 0)
        self.assertAlmostEqual(self.app.game.arrow.velocity[1], 0)
        self.app.draw()

    def test_menu_cancels_drag_without_firing(self):
        self.app.start_mouse()
        self.app.draw()
        self.event(pygame.MOUSEBUTTONDOWN, button=1, pos=(600, 400))
        self.event(pygame.KEYDOWN, key=pygame.K_ESCAPE)
        self.event(pygame.MOUSEBUTTONUP, button=1, pos=(800, 400))
        self.assertEqual(self.app.state, STATE_MENU)
        self.assertEqual(self.app.game.shots, 0)

    def test_camera_failure_returns_to_reviewable_menu(self):
        with patch('camera.CameraSession', side_effect=RuntimeError('no webcam')):
            self.app.start_camera()
        self.assertEqual(self.app.state, STATE_MENU)
        self.assertIsNone(self.app.controller)
        self.assertTrue(self.app.error)
        self.app.draw()
        self.assertIn('mouse', self.app.renderer.buttons)

    def test_keyboard_camera_release_requires_a_fresh_shared_clock_sample(self):
        self.app.start_mouse()
        controls, unused = calibrated()
        controls.on_shot = self.app.shoot
        controls.controls_clear = True
        controls.last_draw = (.75, bullseye_angle())
        self.app.mode, self.app.controller = 'camera', controls
        self.app.measurement = measurement(1000)
        for seconds in (1.5, .9):
            with patch('main.monotonic_seconds', return_value=seconds):
                self.event(pygame.KEYDOWN, key=pygame.K_SPACE)
            self.assertEqual(self.app.game.shots, 0)
        with patch('main.monotonic_seconds', return_value=1.1):
            self.event(pygame.KEYDOWN, key=pygame.K_SPACE)
        self.assertEqual(self.app.game.shots, 1)
        self.assertAlmostEqual(self.app.game.arrow.shot.angle, bullseye_angle())

    def test_window_focus_loss_cancels_mouse_release_without_consuming_an_arrow(self):
        self.app.start_mouse()
        self.event(pygame.MOUSEBUTTONDOWN, button=1, pos=(600, 400))
        self.event(pygame.MOUSEMOTION, pos=(780, 375))
        self.assertIsNotNone(self.app.drag_start)
        self.event(pygame.WINDOWFOCUSLOST)
        self.event(pygame.MOUSEBUTTONUP, button=1, pos=(780, 375))
        self.assertEqual(self.app.game.shots, 0)
        self.assertIsNone(self.app.drag_start)

    def test_space_records_first_camera_step_with_slow_shoulder_results(self):
        camera = Mock()
        camera.preview.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
        camera.read.side_effect = [
            (camera.preview.return_value, measurement(stamp), 'Camera distance looks good.', stamp)
            for stamp in (1000, 1600, 2200, 2800)
        ]
        with patch('camera.CameraSession', return_value=camera):
            self.app.start_camera()
        self.assertEqual(self.app.state, STATE_CALIBRATE)
        self.event(pygame.KEYDOWN, key=pygame.K_SPACE)
        for _ in range(4):
            self.app.update(.6)
        self.assertEqual(self.app.controller.calibration.step, 1)
        self.assertAlmostEqual(self.app.controller.calibration.camera_scale, .3)
        self.app.draw()


if __name__ == '__main__':
    unittest.main()
