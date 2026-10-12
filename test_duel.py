"""Camera-free checks of shared-camera ownership, release safety and duel physics."""
import math
import queue
import unittest
from unittest.mock import Mock, patch
import numpy as np
from duel import DuelMatch, DuelArrow
from duel_aim import launch_velocity
import hitbox
from duel_tracking import (IdentityTracker, HandStateHold, associate_hands, classify_hand,
                           crop_affine, hand_crop_box, measure_hands, pick_crop_hand)
from duel_camera import DuelSession
from physics import GRAVITY, strength_to_speed


def observation(stamp=1000, center=(.25, .4), scale=.16, state='Closed', gap=1.2, generation=1):
    return {'stamp': stamp, 'center': np.array(center), 'scale': scale,
            'gap': gap, 'angle': 0., 'state': state, 'generation': generation,
            'hands_clear': True, 'identity_clear': True}


def pair(stamp=1000, state='Closed', gap=1.2):
    return [observation(stamp, state=state, gap=gap),
            observation(stamp, center=(.75, .4), state=state, gap=gap)]


def camera_match():
    match = DuelMatch()
    match.calibration_step = 3
    match.body_baselines = [{'center': np.array([x, .4]), 'scale': .16} for x in (.25, .75)]
    for controller in match.controllers:
        controller.calibration.step = 3
        controller.calibration.rest_gap = .4
        controller.calibration.full_gap = 1.4
        controller.calibration.neutral_angle = 0
    return match


def candidate(x, colour=(1, 0, 0), scale=.16):
    return {'center': np.array([x, .4]), 'scale': scale, 'colour': np.array(colour)}


def aim_at_opponent(match, player_id, strength=1, height=1.6):
    """Low-arc angle whose arrow, launched from the drawn bow tip, crosses the opponent at height."""
    player, target = match.players[player_id], match.players[1 - player_id]

    def height_at_target(angle):
        x0, y0 = match.launch_point(player_id, angle)
        vx, vy = launch_velocity(strength, angle, player.facing)
        t = (target.x - x0) / vx
        return y0 + vy * t - .5 * GRAVITY * t * t

    low, high = -20., 45.
    for _ in range(60):
        mid = (low + high) / 2
        low, high = (mid, high) if height_at_target(mid) < height else (low, mid)
    return (low + high) / 2


class TrackingTests(unittest.TestCase):
    def test_initial_identity_requires_two_separated_people(self):
        tracker = IdentityTracker()
        self.assertEqual(tracker.update([candidate(.4)], 1000), [None, None])
        self.assertEqual(tracker.update([candidate(.4), candidate(.45)], 1100), [None, None])
        result = tracker.update([candidate(.8), candidate(.2)], 1200)
        self.assertAlmostEqual(result[0]['center'][0], .2)
        self.assertAlmostEqual(result[1]['center'][0], .8)

    def test_identity_survives_crossing_and_detector_order_changes(self):
        tracker = IdentityTracker()
        red, blue = (1, 0, 0), (0, 0, 1)
        tracker.update([candidate(.25, red), candidate(.75, blue)], 1000)
        for frame, (left, right) in enumerate(((.32, .68), (.39, .61), (.46, .54), (.53, .47), (.60, .40))):
            result = tracker.update([candidate(right, blue), candidate(left, red)], 1100 + frame * 100)
            self.assertIsNotNone(result[0])
            self.assertIsNotNone(result[1])
            self.assertAlmostEqual(result[0]['center'][0], left)
            self.assertAlmostEqual(result[1]['center'][0], right)

    def test_ambiguous_identity_is_withheld_and_does_not_swap(self):
        tracker = IdentityTracker()
        tracker.update([candidate(.35), candidate(.65)], 1000)
        for stamp, xs in ((1100, (.41, .59)), (1200, (.47, .53))):
            tracker.update([candidate(x) for x in xs], stamp)
        result = tracker.update([candidate(.5), candidate(.5)], 1300)
        self.assertEqual(result, [None, None])

    def test_missing_person_does_not_reassign_other_player(self):
        tracker = IdentityTracker()
        tracker.update([candidate(.25, (1, 0, 0)), candidate(.75, (0, 0, 1))], 1000)
        result = tracker.update([candidate(.72, (0, 0, 1))], 1100)
        self.assertIsNone(result[0])
        self.assertAlmostEqual(result[1]['center'][0], .72)
        result = tracker.update([candidate(.25, (1, 0, 0)), candidate(.72, (0, 0, 1))], 1600)
        self.assertEqual(result[0]['generation'], 2)

    def test_hands_have_global_unique_pose_ownership(self):
        observations = pair()
        for o, xs in zip(observations, ((.15, .35), (.65, .85))):
            o['pose'] = np.ones((33, 2)) * .5
            o['pose'][15], o['pose'][16] = [xs[0], .5], [xs[1], .5]
        hands = [{'wrist': [x, .5], 'state': state} for x, state in
                 ((.85, 'Open'), (.15, 'Open'), (.65, 'Closed'), (.35, 'Closed'))]
        result = associate_hands(observations, hands)
        self.assertTrue(all(o['hands_clear'] for o in result))
        self.assertEqual([o['state'] for o in result], ['Closed', 'Open'])
        self.assertEqual(len({tuple(w) for o in result for w in o['wrists'].values()}), 4)

    def test_overlapping_hands_cancel_uncertain_ownership(self):
        observations = pair()
        for o in observations:
            o['pose'] = np.ones((33, 2)) * .5
        result = associate_hands(observations, [{'wrist': [.5, .5], 'state': 'Open'}] * 4)
        self.assertFalse(any(o['hands_clear'] for o in result))
        self.assertTrue(all(not o['wrists'] for o in result))

    def test_bad_landmarks_do_not_classify_as_release(self):
        self.assertEqual(classify_hand(np.zeros((21, 3))), 'Unknown')
        self.assertEqual(classify_hand(np.ones((21, 3)) * np.nan), 'Unknown')



def open_hand(wrist=(.5, .8)):
    """Synthetic open hand in crop coordinates: straight fingers pointing up."""
    points = np.zeros((21, 3))
    points[0, :2] = wrist
    for finger, x in zip(range(4), (-.06, -.02, .02, .06)):
        for joint in range(4):
            points[5 + finger * 4 + joint, :2] = [wrist[0] + x, wrist[1] - .15 - .08 * joint]
    for joint in range(4):
        points[1 + joint, :2] = [wrist[0] - .1 - .03 * joint, wrist[1] - .05 * joint]
    return points


def far_pose(right_wrist=(.62, .55), left_wrist=(.45, .5)):
    pose = np.full((33, 2), np.nan)
    pose[11], pose[12] = [.48, .4], [.56, .4]
    pose[14], pose[16], pose[15] = [.6, .48], right_wrist, left_wrist
    return pose


class FarHandTests(unittest.TestCase):
    def test_crop_frames_right_hand_from_pose_and_round_trips(self):
        pose = far_pose()
        box = hand_crop_box(pose, .08, 1280, 720)
        cx, cy, side = box
        # Extrapolated past the wrist, away from the elbow, at least 64 px.
        self.assertGreater(cx, .62 * 1280)
        self.assertGreaterEqual(side, 64)
        wrist_px = np.array([.62 * 1280, .55 * 720, 1])
        u, v = crop_affine(box) @ wrist_px / 256
        hand = pick_crop_hand([open_hand((u, v))], box, pose[16], .08, 1280, 720)
        self.assertEqual(hand['state'], 'Open')
        np.testing.assert_allclose(hand['wrist'], [.62, .55], atol=1e-9)

    def test_crop_needs_a_visible_right_wrist(self):
        self.assertIsNone(hand_crop_box(far_pose(right_wrist=(np.nan, np.nan)), .08, 1280, 720))

    def test_crop_ignores_far_or_ambiguous_hands(self):
        pose = far_pose()
        box = hand_crop_box(pose, .08, 1280, 720)
        u, v = crop_affine(box) @ np.array([.62 * 1280, .55 * 720, 1]) / 256
        self.assertIsNone(pick_crop_hand([open_hand((.02, .02))], box, pose[16], .08, 1280, 720))
        twins = [open_hand((u, v)), open_hand((u + .01, v))]
        self.assertIsNone(pick_crop_hand(twins, box, pose[16], .08, 1280, 720))

    def test_hand_state_bridges_short_dropouts_only(self):
        hold = HandStateHold()
        self.assertEqual(hold.update(0, 1, 'Closed', 1000), 'Closed')
        self.assertEqual(hold.update(0, 1, 'Unknown', 1200), 'Closed')
        self.assertEqual(hold.update(0, 1, 'Unknown', 1300), 'Unknown')
        self.assertEqual(hold.update(1, 1, 'Unknown', 1300), 'Unknown')
        hold.update(0, 1, 'Closed', 2000)
        self.assertEqual(hold.update(0, 2, 'Unknown', 2050), 'Unknown')
        self.assertEqual(hold.update(0, 1, 'Open', 2100), 'Open')

    def test_raising_the_hand_nearer_the_opponent_aims_up_for_both_players(self):
        observations = pair()
        # P1 (left) draws with the hand nearer P2; P2 (right) holds the bow nearer P1.
        observations[0]['pose'] = far_pose(right_wrist=(.35, .40), left_wrist=(.15, .50))
        observations[1]['pose'] = far_pose(right_wrist=(.85, .50), left_wrist=(.65, .40))
        result = measure_hands(observations, ['Closed', 'Closed'], 4 / 3)
        self.assertGreater(result[0]['angle'], 15)
        self.assertGreater(result[1]['angle'], 15)
        self.assertAlmostEqual(result[0]['angle'], result[1]['angle'])
        # Lowering that same hand aims down, again identically for both.
        observations = pair()
        observations[0]['pose'] = far_pose(right_wrist=(.35, .60), left_wrist=(.15, .50))
        observations[1]['pose'] = far_pose(right_wrist=(.85, .50), left_wrist=(.65, .60))
        result = measure_hands(observations, ['Closed', 'Closed'], 4 / 3)
        self.assertLess(result[0]['angle'], -15)
        self.assertAlmostEqual(result[0]['angle'], result[1]['angle'])

    def test_aim_direction_follows_players_who_swap_sides(self):
        observations = pair()
        observations[0]['center'], observations[1]['center'] = np.array([.75, .4]), np.array([.25, .4])
        # P1 is now on the right: like P2 before, its bow hand faces the opponent.
        observations[0]['pose'] = far_pose(right_wrist=(.85, .50), left_wrist=(.65, .40))
        observations[1]['pose'] = far_pose(right_wrist=(.35, .40), left_wrist=(.15, .50))
        result = measure_hands(observations, ['Closed', 'Closed'], 4 / 3)
        self.assertGreater(result[0]['angle'], 15)
        self.assertGreater(result[1]['angle'], 15)

    def test_measure_hands_uses_each_players_own_pose_wrists(self):
        observations = pair()
        # Mirrored preview: each player's left (bow) hand is on the screen-left.
        observations[0]['pose'] = far_pose(right_wrist=(.35, .5), left_wrist=(.15, .5))
        observations[1]['pose'] = far_pose(right_wrist=(.85, .5), left_wrist=(.65, .5))
        result = measure_hands(observations, ['Closed', 'Open'], 4 / 3)
        self.assertTrue(all(o['hands_clear'] for o in result))
        self.assertEqual([o['state'] for o in result], ['Closed', 'Open'])
        self.assertAlmostEqual(result[0]['gap'], .2 / .16)
        self.assertAlmostEqual(result[0]['angle'], 0)
        observations = pair()
        for o in observations:
            o['pose'] = far_pose()
        result = measure_hands(observations, [None, 'Unknown'], 4 / 3)
        self.assertFalse(any(o['hands_clear'] for o in result))

class GestureTests(unittest.TestCase):
    def test_two_closed_then_open_hands_release_two_arrows_together(self):
        match = camera_match()
        for stamp, state in ((1000, 'Closed'), (1100, 'Closed'), (1200, 'Open'), (1310, 'Open')):
            match.apply_tracking(pair(stamp, state), stamp)
        self.assertEqual([p.shots for p in match.players], [1, 1])
        self.assertEqual({a.owner for a in match.arrows}, {0, 1})

    def test_duplicate_results_cannot_confirm_release(self):
        match = camera_match()
        match.apply_tracking(pair(1000), 1000)
        for now in (1100, 1200, 1300):
            match.apply_tracking(pair(1100, 'Open'), now)
        self.assertEqual(len(match.arrows), 0)

    def test_loss_and_open_reacquisition_cannot_shoot_previous_draw(self):
        for lost in (None, 'stale', 'ambiguous', 'unknown', 'hands'):
            with self.subTest(lost=lost):
                match = camera_match()
                match.apply_tracking(pair(1000), 1000)
                lost_pair = pair(1100)
                if lost is None:
                    lost_pair = [None, None]
                elif lost == 'stale':
                    lost_pair = pair(500)
                elif lost == 'ambiguous':
                    for o in lost_pair:
                        o['identity_clear'] = False
                else:
                    for o in lost_pair:
                        o['hands_clear'] = False
                        if lost == 'unknown':
                            o['state'] = 'Unknown'
                match.apply_tracking(lost_pair, 1100)
                match.apply_tracking(pair(1200, 'Open'), 1200)
                match.apply_tracking(pair(1320, 'Open'), 1320)
                self.assertEqual(len(match.arrows), 0)

    def test_generation_change_open_cannot_release_a_previous_draw(self):
        match = camera_match()
        match.apply_tracking(pair(1000), 1000)
        observations = pair(1100, 'Open')
        for o in observations:
            o['generation'] = 2
        match.apply_tracking(observations, 1100)
        match.apply_tracking(pair(1220, 'Open'), 1220)
        self.assertEqual(len(match.arrows), 0)

    def test_one_person_can_release_while_other_continues_drawing(self):
        match = camera_match()
        match.apply_tracking(pair(1000), 1000)
        for stamp in (1100, 1210):
            observations = pair(stamp)
            observations[0]['state'] = 'Open'
            match.apply_tracking(observations, stamp)
        self.assertEqual([p.shots for p in match.players], [1, 0])
        self.assertTrue(match.players[1].drawing)

    def test_lateral_and_relative_depth_change_player_distance(self):
        match = camera_match()
        match.apply_tracking(pair(1000), 1000)
        start = match.separation
        observations = pair(1200)
        observations[0]['center'][0] += .1
        observations[1]['center'][0] -= .1
        match.apply_tracking(observations, 1200)
        self.assertLess(match.separation, start)
        observations = pair(1400)
        for o in observations:
            o['scale'] = .10
        match.apply_tracking(observations, 1400)
        self.assertGreater(match.separation, start)

    def test_players_can_cross_and_face_each_other(self):
        match = camera_match()
        observations = pair(1000)
        observations[0]['center'][0] = .95
        observations[1]['center'][0] = .05
        match.apply_tracking(observations, 1000)
        self.assertGreater(match.players[0].x, match.players[1].x)
        self.assertEqual([p.facing for p in match.players], [-1, 1])

    def test_calibration_requires_both_fresh_unique_stable_samples(self):
        match = DuelMatch()
        match.request_capture()
        for now in range(1000, 2500, 100):
            match.apply_tracking(pair(1000), now)
        self.assertEqual(match.calibration_step, 0)
        for step in range(3):
            match.request_capture()
            gap = .4 if step == 1 else 1.2
            for sample in range(12):
                stamp = 3000 + step * 2000 + sample * 100
                match.apply_tracking(pair(stamp, gap=gap), stamp)
            self.assertEqual(match.calibration_step, step + 1)
        self.assertTrue(match.ready)
        self.assertAlmostEqual(match.controllers[0].calibration.full_gap, 1.2)


class PhysicsTests(unittest.TestCase):
    def test_simultaneous_projectiles_hit_both_opponents(self):
        match = DuelMatch(keyboard=True)
        for i in range(2):
            self.assertTrue(match.shoot(i, 1., aim_at_opponent(match, i)))
        match.update(2.)
        self.assertEqual([p.health for p in match.players], [60, 60])
        self.assertEqual([p.hits for p in match.players], [1, 1])

    def test_large_and_small_steps_produce_same_health(self):
        big, small = DuelMatch(keyboard=True), DuelMatch(keyboard=True)
        for match in (big, small):
            for i in range(2):
                match.shoot(i, 1., aim_at_opponent(match, i))
        big.update(2)
        for _ in range(200):
            small.update(.01)
        self.assertEqual([p.health for p in big.players], [p.health for p in small.players])
        self.assertEqual([p.hits for p in big.players], [p.hits for p in small.players])

    def test_collision_sweeps_opponent_motion(self):
        match = DuelMatch(keyboard=True)
        match.arrows.append(DuelArrow(0, 20., 1.5, 0., 0., 1.))
        match.players[1].x = 15
        match.update(.02)
        self.assertEqual(match.players[1].health, 60)
        self.assertFalse(match.arrows)

    def test_arrows_hit_the_drawn_head_not_just_a_thin_box(self):
        match = DuelMatch(keyboard=True)
        target = match.players[1]
        # Level arrow at head height (about 2.8 m): the old 2.4 m box missed it.
        match.arrows.append(DuelArrow(0, target.x - 6, 2.8, 30., 0., 1.))
        match.update(.4)
        self.assertLess(target.health, 100)

    def test_arrow_over_the_head_misses(self):
        match = DuelMatch(keyboard=True)
        target = match.players[1]
        match.arrows.append(DuelArrow(0, target.x - 6, 4.2, 30., 0., 1.))
        match.update(.4)
        self.assertEqual(target.health, 100)

    def test_the_held_bow_does_not_count_as_body(self):
        match = DuelMatch(keyboard=True)
        target = match.players[1]           # faces left, bow ~3 m in front
        match.arrows.append(DuelArrow(0, target.x - 3.2, 2.5, 0., -10., 1.))
        match.update(1.)
        self.assertEqual(target.health, 100)

    def test_point_blank_opponent_is_hit_at_once(self):
        match = DuelMatch(keyboard=True)
        match.players[1].x = match.players[0].x + 2
        self.assertTrue(match.shoot(0, 1., 0))
        self.assertLess(match.players[1].health, 100)
        self.assertFalse(match.arrows)

    def test_hit_area_and_launch_match_the_renderer(self):
        import duel_renderer
        from characters import CharacterArtist
        self.assertAlmostEqual(hitbox.PX_PER_M_X, duel_renderer.WIDTH / duel_renderer.BASE_VIEW)
        for angle in (-60, 0, 30, 90):
            radians = math.radians(angle)
            visible = math.degrees(math.atan2(65 * math.sin(radians), hitbox.PX_PER_M_X * math.cos(radians)))
            tip = CharacterArtist.arrow_tip((0, 0), 1, visible, 1)
            x, y = hitbox.tip_offset(angle)
            self.assertAlmostEqual(x, tip.x / hitbox.PX_PER_M_X, places=4)
            self.assertAlmostEqual(y, -tip.y / 65, places=4)

    def test_opponent_can_dodge_a_previously_aimed_arrow(self):
        match = DuelMatch(keyboard=True)
        match.shoot(0, 1., aim_at_opponent(match, 0))
        match.players[1].x = 45
        match.update(.25)
        match.update(2.75)
        self.assertEqual(match.players[1].health, 100)

    def test_double_knockout_draw_and_restarting_resets_match(self):
        match = DuelMatch(keyboard=True)
        for i in range(2):
            match.players[i].health = 40
            match.shoot(i, 1., aim_at_opponent(match, i))
        match.update(2)
        self.assertEqual(match.winner, 'draw')
        self.assertFalse(match.shoot(0, 1, 0))
        match.reset()
        self.assertFalse(match.finished)
        self.assertEqual([p.health for p in match.players], [100, 100])
        self.assertEqual(match.separation, 22)

    def test_already_flying_retaliation_can_still_draw_after_first_knockout(self):
        match = DuelMatch(keyboard=True)
        match.players[0].health = match.players[1].health = 20
        match.arrows = [DuelArrow(0, 30, 1.5, 15, 0, 1), DuelArrow(1, 12, 1.5, -15, 0, 1)]
        match.update(.05)
        self.assertEqual(match.players[1].health, 0)
        self.assertIsNone(match.winner)
        match.update(.3)
        self.assertEqual(match.winner, 'draw')

    def test_keyboard_draw_requires_hold_and_release_keys_independently(self):
        match = DuelMatch(keyboard=True)
        for i in range(2):
            match.keyboard(i, draw=True, dt=.8)
        match.keyboard(0, draw=False, dt=.02)
        self.assertTrue(match.players[0].drawing)
        self.assertTrue(match.keyboard(0, release=True))
        self.assertTrue(match.keyboard(1, release=True))
        self.assertEqual([p.shots for p in match.players], [1, 1])
        self.assertFalse(match.keyboard(0, release=True))

    def test_invalid_shots_frames_and_reload(self):
        match = DuelMatch(keyboard=True)
        self.assertFalse(match.shoot(0, float('nan'), 20))
        self.assertFalse(match.shoot(0, .05, 20))
        self.assertTrue(match.shoot(0, 1, 20))
        self.assertFalse(match.shoot(0, 1, 20))
        match.update(.7)
        self.assertTrue(match.shoot(0, 1, 20))
        for dt in (-1, float('inf'), float('nan')):
            with self.assertRaises(ValueError):
                match.update(dt)


class CameraBridgeTests(unittest.TestCase):
    def session(self):
        camera = DuelSession.__new__(DuelSession)
        camera.closed = False
        camera.rgb = np.zeros((240, 320, 3), dtype=np.uint8)
        camera.output = queue.Queue()
        camera.observations = pair(1400)
        camera.status = 'Tracking OK'
        camera.last_stamp = 1400
        camera.process = Mock()
        camera.process.is_alive.return_value = True
        camera.started_at = 1000
        return camera

    def test_bridge_cancels_old_samples_using_shared_clock(self):
        camera = self.session()
        with patch('duel_camera.monotonic_seconds', return_value=1.8):
            rgb, observations, status, timestamp = camera.read()
        self.assertEqual(observations, [None, None])
        self.assertEqual(timestamp, 1800)
        with patch('duel_camera.monotonic_seconds', return_value=4.5):
            with self.assertRaises(RuntimeError):
                camera.read()

    def test_bridge_drains_to_newest_packet_and_reports_worker_error(self):
        camera = self.session()
        for stamp in (1450, 1500):
            camera.output.put({'type': 'frame', 'rgb': camera.rgb, 'observations': pair(stamp),
                               'stamp': stamp, 'status': 'Tracking OK'})
        with patch('duel_camera.monotonic_seconds', return_value=1.6):
            result = camera.read()
        self.assertEqual(result[1][0]['stamp'], 1500)
        camera.output.put({'type': 'error', 'message': 'Permission denied'})
        with self.assertRaisesRegex(RuntimeError, 'Permission denied'):
            camera.read()


if __name__ == '__main__':
    unittest.main()
