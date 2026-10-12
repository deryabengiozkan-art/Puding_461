"""Full ±90° camera aiming and matching duel prediction/release checks."""
import unittest

from controls import Calibration
from duel import DuelMatch
from duel_aim import DuelCalibration, DuelInputController
from physics import GRAVITY


class DuelAimTests(unittest.TestCase):
    def calibration(self, neutral):
        calibration = DuelCalibration()
        calibration.step = 3
        calibration.rest_gap, calibration.full_gap = .4, 1.4
        calibration.neutral_angle = neutral
        return calibration

    def test_nonlevel_neutral_preserves_both_vertical_endpoints(self):
        for neutral in (-35, 0, 28):
            calibration = self.calibration(neutral)
            for angle, expected in ((-90, -1), (neutral, 0), (90, 1)):
                with self.subTest(neutral=neutral, angle=angle):
                    strength, direction = calibration.normalize({'gap': .9, 'angle': angle})
                    self.assertAlmostEqual(strength, .5)
                    self.assertEqual(direction, expected)
            directions = [calibration.normalize({'gap': 1.4, 'angle': angle})[1]
                          for angle in range(-90, 91)]
            self.assertTrue(all(a < b for a, b in zip(directions, directions[1:])))

    def test_recalibration_and_rematch_keep_duel_mapping(self):
        controller = DuelInputController(lambda *_: True)
        controller.calibration = self.calibration(20)
        controller.reset()
        self.assertEqual(controller.calibration.neutral_angle, 20)
        controller.reset(recalibrate=True)
        self.assertIsInstance(controller.calibration, DuelCalibration)
        self.assertFalse(controller.calibration.ready())
        match = DuelMatch()
        match.reset(recalibrate=True)
        self.assertTrue(all(isinstance(c.calibration, DuelCalibration) for c in match.controllers))

    def test_camera_controller_reaches_full_aim_from_nonlevel_calibration(self):
        for angle in (-90, 90):
            controller = DuelInputController(lambda *_: True)
            controller.calibration = self.calibration(25)
            controller.update_controls({'stamp': 1000, 'gap': 1.4, 'angle': angle,
                                        'state': 'Closed'}, 1000)
            self.assertEqual(controller.aim_degrees, angle)
            self.assertEqual(controller.last_draw, (1., angle))

    def test_solo_calibration_remains_unchanged(self):
        calibration = Calibration()
        calibration.rest_gap, calibration.full_gap = .4, 1.4
        calibration.neutral_angle = 30
        self.assertAlmostEqual(calibration.normalize({'gap': 1.4, 'angle': 90})[1], 2 / 3)

    def test_vertical_and_clamped_preview_matches_release_for_both_players(self):
        for player_id in (0, 1):
            for angle in (-120, -90, -45, 0, 45, 90, 120):
                with self.subTest(player=player_id, angle=angle):
                    match = DuelMatch(keyboard=True)
                    player = match.players[player_id]
                    player.angle, player.strength = angle, 1.
                    points = match.prediction(player_id, duration=.1, spacing=.02)
                    self.assertTrue(match.shoot(player_id, player.strength, player.angle))
                    arrow = match.arrows[0]
                    launch_y = arrow.y
                    if abs(angle) >= 90:
                        self.assertEqual(arrow.vx, 0)
                    for index, point in enumerate(points):
                        seconds = index * .02
                        self.assertAlmostEqual(point[0], arrow.x + arrow.vx * seconds)
                        self.assertAlmostEqual(point[1], launch_y + arrow.vy * seconds
                                               - .5 * GRAVITY * seconds * seconds)


if __name__ == '__main__':
    unittest.main()
