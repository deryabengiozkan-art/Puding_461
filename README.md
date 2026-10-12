# Archidon — two-player camera duel

Choose **Two player camera duel** from the main menu. Both players share one
webcam and play at the same time: each can move, aim, draw and release while
the other player moves or has arrows in flight. Arrows hit the opposing archer;
the first player to lose all health loses. A simultaneous knockout is a draw.

Each player chooses one of six original pixel-art archers: **Fern** (forest
ranger), **Flint** (storm viking), **Prof. Torque** (mad engineer with a
compound bow), **Bolt-9** (scrap robot), **Akıncı** (steppe archer with a
recurve bow) and **Gourd** (pumpkin-head scarecrow). The big-head style is
inspired by the supplied references; the designs themselves are original.
All characters have the same gameplay stats. Players can choose the same one.

### Pixel art

Everything on screen is pixel art drawn by code in `pixelart/` (no image files,
no Pillow): art is generated at native resolution and scaled 3x with
nearest-neighbour, so pixels stay crisp. `pixelart/sprites.py` draws the
characters from separate parts; their arms, bow, string and arrow are redrawn
for every aim angle and pull, so aiming never blurs. `pixelart/font.py` is an
original 5x7 bitmap font (bold + regular, Turkish letters). `pixelart/ui.py`
holds the buttons (normal / hover / pressed / disabled), icon buttons, panels,
ribbons, logo, VS badge, cards, health and pull bars. `pixelart/scenery.py`
builds the endless campus: seven layers (clouds, hills, trees, campus buildings
including MAKİNE G, the stone wall, the path and foreground grass), each a
seamless loop with a different width and parallax speed, so the background
never visibly repeats. The menu's moon/sun button switches between day and
night (`--scenery night` starts at night).

Selection supports both the mouse and independent keyboard controls: Player 1
uses **A / D** to choose and **F** to confirm; Player 2 uses **Left / Right**
and **Enter**. When both are ready, press **Space**. The shared confirmation
button also starts the match. Use **Characters / Tab** during a duel or after
the result to choose again.

Start with Player 1 on the **left of the mirrored camera preview**, Player 2
on its right. Stand far enough from the camera for both pairs of shoulders and
both pairs of wrists to remain visible. Record the setup positions together with
**Space / Record position**, following the on-screen instructions. Each step
uses distinct, fresh observations of both players. Close your **right hand**
to start drawing, separate your hands to increase pull, tilt their line to
aim (raise the hand nearer your opponent to aim up: the bow hand for the
player on the right, the drawing hand for the player on the left), then open your right hand to release. Both players can fire simultaneously.
Aim stays within **−90° to +90°**, including straight up and straight down.
Calibrating a slightly tilted neutral position preserves both vertical limits.

**Hits match the drawing.** Arrows hit a character's drawn head, body and
legs (not the bow), using each character's pixel silhouette in `hitbox.py`, and
they launch from the arrow tip drawn on the bow. An opponent closer than the
bow tip is hit immediately.

**Far-player hand tracking.** The camera runs at 640×480. Both wrists come from
each player's body pose, which still works when players stand well back. Only
the right (drawing) hand needs a gesture, so the hand model runs on an upscaled
square crop around each player's right wrist (the boxes in the camera preview)
instead of the whole frame, where a distant hand is only a few pixels wide. A
body that is too small to read a fist reliably reports Unknown instead of
guessing. The preview draws each player's full skeleton, the drawing hand's 21
hand-model joints (white) and the bow hand from the pose. A missed hand reading is bridged for up to 250 ms with the last confident state,
so one dropped frame no longer cancels a draw. For even more range, download
`pose_landmarker_full.task` from the MediaPipe pose landmarker page and put it
beside the game; it is used automatically instead of the lite model.

Lateral movement and changes in apparent shoulder size move the archers and
change their separation in real time. Shoulder size estimates relative depth;
the distance shown in the arena is a gameplay distance, not a measurement of
physical metres. Player identities follow tracked body positions rather than
being reassigned left-to-right on every frame. Occlusion, ambiguous identity
or lost hands pauses that player's controls and cancels their draw; reacquire
tracking and close the hand again before firing.

Movement and separation have no fixed arena boundary. Each player's calibrated
position anchors their character; lateral movement is normalized by shoulder
width, and movement toward or away from the camera adds a relative depth
adjustment. The starting 22 m separation is a gameplay reference, not a measured
physical distance. Both people must remain visible for camera movement to work.
The characters walk when their positions change,
with alternating steps and body motion, and settle into idle when they stop.

The endless pixel campus scrolls in layers as a shared view keeps both
archers and their bows visible while they move and arrows fly. The camera also
zooms with the distance between the archers: `camera_zoom(separation)` in
`duel_renderer.py` gives 1.0 at the 22 m start, zooms in (up to 1.35x) as they
close in and out (down to 0.6x) as they separate. The zoom eases toward that
target with a 0.8 s time constant (`ZOOM_TIME`), so it moves slowly and
smoothly; it only jumps wider when needed to keep both archers on screen.
**R** restarts
with the existing calibration, **C** recalibrates, **Esc** returns to the menu,
**Tab** reopens character selection, and **Q** quits.

For two-player testing without vision dependencies:

```sh
python launch_game.py --duel-keyboard
```

| Player | Move | Aim | Draw and release |
| --- | --- | --- | --- |
| Player 1 | A / D | W / S | Hold F, then release |
| Player 2 | Left / Right | Up / Down | Hold Enter, then release |

Direct development launch from the parent folder:

```sh
.venv/bin/python "Official Game/main.py" --duel
```

The original single-player camera and mouse practice modes remain in the menu.
Their distant-target instructions follow below.

### Duel implementation and checks

`duel.py` owns independent inputs, health, moving-target collisions, multiple
projectiles and match outcomes. `duel_tracking.py` owns persistent player
identities and unique pose-to-hand assignments. `duel_camera_worker.py` runs
synchronized inference in a separate spawned process; `duel_camera.py` keeps
the game loop responsive. `characters.py` draws both original characters, and
`duel_renderer.py` renders calibration and the shared arena with campus
parallax, camera framing and distance-driven walking. `character_selection.py`
provides independent selection and confirmation. `duel_aim.py` preserves the
full aiming range around a calibrated neutral position.

The worker uses `num_poses=2` and `num_hands=4`, with both models processing the
same captured frame. It runs inference on the original camera image, preserving
anatomical left/right, then mirrors coordinates and the preview for movement.
See the official [Pose Landmarker documentation](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker/python)
and [Hand Landmarker documentation](https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker/python).

Synthetic tests cover simultaneous releases, independent inputs, identity
crossings, ambiguous hands, tracking loss/recovery, calibration, changing
distance, swept collisions, dodging, double knockouts, keyboard events and
menu/restart/camera cleanup. The intended two-person webcam setup still needs
a live play session; lighting, occlusion and camera placement affect tracking.
The current suite passes **160 tests** (including 34 campaign and admin tests), including movement beyond the old arena,
nonlevel neutral calibration, independent selection, walking/idle rendering,
and simultaneous crossing and release. Headless previews also verify the
restored scenery, shared camera framing, and unclipped endpoint poses.
An isolated spawned worker also ran both
actual models on a two-person image fixture: two body poses were detected,
identities were assigned correctly, the preview arrived with fresh timestamps,
and the process closed cleanly. The fixture did not show all four hands, so
gesture validation uses synthetic observations rather than that image.

```sh
.venv/bin/python -m unittest discover -s "Official Game" -p "test_*.py"
.venv/bin/python "Official Game/main.py" --duel-demo --headless --frames 3 --screenshot "Official Game/preview_duel.png"
```

## Single-player campaign (10 levels)

Choose **Campaign · Camera** or **Campaign · Mouse** in the main menu. Each
level gives a fixed number of arrows and a score you must reach; clearing it
unlocks the next level and awards 1–3 stars. Progress (unlocked level, best
score, stars) is saved in `campaign_progress.json` beside the game.

* **Random target position** – every attempt places the board at a random
  distance (and on some levels a random height) inside the level's range.
  From Level 7 the board also jumps to a new spot after every arrow, once the
  view has returned to the archer.
* **Different target sizes** – the board shrinks from 0.9 m to 0.65 m radius;
  rings are 40 / 80 / 100 % of the radius (50 / 25 / 15 points).
* **Hits match what you see** – the board counts as the disc that is drawn:
  any arrow path that passes over the disc is a hit, even a steep arrow that
  enters its near edge. The arrow sticks at its closest approach to the
  centre, and that distance decides the ring. The outer ring has a 6 cm margin
  for the arrow head.
* **Arrow budget and required score** – listed per level below. The level ends
  early once the required score can no longer be reached.
* **Hills and obstacles** – hills, a hedge, castle walls, trees, a rock and
  floating crates (some bobbing) stop arrows. Low, flat shots no longer work.
* **Wind** – a random tail- or headwind each attempt on Levels 5, 8, 9, 10.
* **Moving board** – Levels 8 and 10 bob up and down; time your release.
* **Stronger bows** – full pull grows from 26 m/s (training bow) to 38 m/s
  (war bow) instead of the practice bow's 24 m/s. The minimum speed also
  rises on longer levels, so each percent of pull changes the shot less and
  long shots are easier to control.
* **Shorter preview** – the dotted aim preview shows less of the flight on
  later levels (100 % → 50 %). The minimap at the top shows the whole level,
  your previous paths and the same partial preview.

| # | Level | Target | Board radius | Arrows | Score to clear / max | Bow speed | Preview | Hazards |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Training Field | 24–32 m | 0.9 m | 6 | 60 / 300 | 12–26 m/s | 100% | — |
| 2 | The Hedge | 30–40 m | 0.85 m | 6 | 70 / 300 | 13–28 m/s | 95% | hedge |
| 3 | Rolling Hills | 40–50 m | 0.8 m | 6 | 75 / 300 | 14–30 m/s | 85% | hills |
| 4 | Castle Wall | 42–54 m | 0.8 m | 6 | 80 / 300 | 15–31 m/s | 80% | wall |
| 5 | Crosswind Meadow | 48–60 m | 0.75 m | 7 | 90 / 350 | 16–32 m/s | 75% | tree, wind 0.4–0.9 |
| 6 | Crate Canyon | 55–66 m | 0.75 m | 7 | 95 / 350 | 17–33 m/s | 70% | crates, rock |
| 7 | Hilltop | 60–74 m | 0.7 m | 7 | 100 / 350 | 18–34 m/s | 65% | hills, board relocates |
| 8 | Swinging Target | 64–76 m | 0.75 m | 7 | 100 / 350 | 19–35 m/s | 60% | tree, wind 0.3–0.7, moving board |
| 9 | The Gauntlet | 74–86 m | 0.7 m | 8 | 110 / 400 | 20–36 m/s | 55% | hills, crate, wall, moving crate, wind 0.4–1.0, board relocates |
| 10 | Champion's Range | 86–98 m | 0.65 m | 8 | 120 / 400 | 21–38 m/s | 50% | hills, crate, wall, moving crate, wind 0.5–1.1, moving board, board relocates |

Stars: 1 = cleared, 2 = 35 % of the way from the required score to a perfect
round, 3 = 65 % of the way. A test checks that every level has a gold shot
on many random layouts (`campaign_solver.py`), so no layout is impossible.

**Controls.** Camera play uses the same calibration and gestures as solo
practice; calibration is kept between levels. Away from the keyboard, close
and open the drawing hand to start a level from its briefing, and on the
result screen to go to the next level (or retry). Mouse play: drag as before;
**Up/Down** change the angle by 0.1°, **Left/Right** the pull by 0.2 %
(hold **Shift** for 1° / 2 %), **Space** fires. Keys: **Space** start / retry,
**N** next level, **R** retry, **L** level select, **Esc** menu, **1–9, 0**
start a level from the level select.

```sh
python launch_game.py --mouse                      # then Campaign in the menu
.venv/bin/python "Official Game/main.py" --campaign --level 3 --unlock-all
.venv/bin/python "Official Game/main.py" --campaign-camera
```

`--unlock-all` opens every level for that run only; it is never saved.
Delete `campaign_progress.json` to reset progress.

### Admin mode

Click the **gear** (top right of the main menu, or start with `--admin`) and
enter the password. The default password is **`archidon461`**; change it in
the admin panel. Only a salted PBKDF2 hash is stored, in `admin_config.json`
beside the game (delete that file to restore the default). Five wrong
attempts lock the screen for 30 seconds.

The admin panel can: unlock all levels, give unlimited arrows, show the full
aim preview, turn wind off, stop moving / relocating boards, enlarge boards
(x1, x1.5, x2), show hitboxes (exact board hit circle and obstacle boxes),
open the level select with mouse or camera, reset saved progress (press
twice), change the password, and lock admin mode again. In a level, **F**
ends the level immediately. Results played in admin mode are never saved.

**Tuning.** Every number above lives in `levels.py` (one `Level(...)` per
level). `campaign.py` holds the flight with wind, terrain and obstacles, the
round rules and the saved progress; `campaign_renderer.py` draws the hills,
obstacles, minimap, level select, briefing and result. `test_campaign.py`
(34 tests) covers flight, scoring, wind, hills, walls, moving boards,
relocation, arrow budget, early failure, stars, saved progress and the full
menu → level → result flow.

## Solo distant-target archery

The human archer stands on the **right**, shooting left toward a target **35 m
away**. The board is outside the starting view. After release, the game camera
follows the arrow and scrolls the campus scenery, briefly shows the landing,
then returns to the archer. You can shoot again when the view settles.

Completed paths stay visible in different colors. A small diagram also preserves
the full range of every previous shot, even when the distant end is offscreen.
It records pull, elevation and points, so you can adjust the next attempt.
The white dotted path remains the current prediction; colored paths are actual
completed flights. Three arrows make a round, with a maximum score of 150.

## Run

On another computer, extract **the entire ZIP**, install 64-bit Python 3.11,
and run the launcher inside `Official Game`:

```sh
python launch_game.py
```

On macOS/Linux, the command may be `python3.11 launch_game.py`. The launcher
accepts Python 3.9–3.12, creates this computer's own `.venv`, and installs the
pinned dependencies. First setup needs internet. Allow camera access when the
operating system asks. Later launches reuse the installed environment.

You can also double-click `Play Windows.bat` or `Play macOS.command`, or run
`./play_linux.sh` on Linux. Choose **Play with camera** in the menu.

For mouse practice with only NumPy/Pygame installed:

```sh
python launch_game.py --mouse
```

Run the full launcher to install tracking dependencies before switching to
camera play. `--setup-only` installs without opening the game. `--check` checks
the current interpreter, dependency versions and local files without installing.

On the development Mac, the existing parent environment still works:
`.venv/bin/python "Official Game/main.py"` from `Archery Game`.
Models and assets resolve relative to their source files, so the terminal's
working directory does not affect the game.

`--camera 1` selects another webcam. `--scenery night` starts with the night
campus (the menu button toggles it). `--background` is kept for compatibility;
the pixel-art scenery has replaced the photo backgrounds.

## Sharing and compatibility

Send **`Archidon_Portable.zip`**. It contains the complete `Official Game`
folder: source, backgrounds, local requirements, launchers and both required
tracking models. To rebuild it after changes, run `python build_share.py` inside
`Official Game`; the ZIP is written to its parent folder. The ZIP excludes
virtual environments, caches, legacy backups and generated gameplay previews.

Previously, sending only this folder omitted `pose_landmarker_lite.task` and
`hand_landmarker.task`. Its requirements file also referred to the parent's
requirements, and the launch instructions used the parent's Mac environment.
Those dependencies are now inside this folder. Each recipient still needs
Python and their own installed packages. A copied virtual environment is not
portable between computers; recreate it on the destination as the launcher does.
See the [Python virtual environment documentation](https://docs.python.org/3/library/venv.html).

The current pinned package set targets **Windows x86-64, Apple Silicon macOS
11+, and Linux x86-64 with glibc 2.28+**. MediaPipe 0.10.35 does not publish an
Intel Mac or Linux ARM wheel. Although it has a Windows ARM64 wheel, our NumPy
and Pygame versions do not. The launcher explains these known installation
limits; `--mouse` avoids vision dependencies on platforms where NumPy/Pygame
are available. Package files:
[MediaPipe](https://pypi.org/project/mediapipe/0.10.35/),
[NumPy](https://pypi.org/project/numpy/2.0.2/),
[Pygame](https://pypi.org/project/pygame/2.6.1/).

The packaged game has been checked on this Apple Silicon Mac. Windows/Linux
launchers and supported-platform installation instructions are included;
those operating systems have not been tested here.

## Controls and calibration

Camera mode starts with three recorded positions. Face the camera with your
shoulders visible. Press **Space** or **Record position** for each step:

1. **Camera position:** hold a comfortable position with both shoulders visible.
2. **Relaxed gap:** bring the hands close without covering one with the other.
3. **Full pull:** separate the hands comfortably and hold your normal level aim.

Each capture needs at least four distinct results spanning one second. Slower
tracking can take a few seconds; repeated display frames do not count. Position
setup uses only shoulders. The screen names the reason if tracking is missing.

The **right hand draws**, and the **left holds the bow**. Close the drawing hand
at any comfortable spacing, adjust pull and elevation, then open it to release.
You do not need to bring your hands together before another shot or after
tracking resumes. The relaxed-gap position is measured only during calibration,
to establish zero power. The shot uses the last closed-hand aim and pull, so
finger opening does not alter it. The camera preview is mirrored. Press **H**
to swap drawing hands and recalibrate if the label does not match your hand.

Distances are divided by shoulder width. Full-pull calibration defines neutral
level aim; elevations span **−90° to +90°**, including exactly vertical shots.
The original tracker classification
and wrist filtering remain intact. Stale, duplicate or unknown observations
cannot fire a shot. A draw is canceled after a tracking gap longer than 500 ms;
a fresh closed-hand result immediately starts a new draw at the current spacing.
Returning with an open hand does not release the canceled shot. Fresh wrist
measurements also allow a manual Space release.

While the arrow flies and the scenery returns, additional releases are ignored.
A fresh closed-hand observation is required after returning. The last impact is
held for 0.8 s, followed by a 0.9 s camera return. Restart keeps calibration;
recalibrating or swapping hands begins a new setup and round.

In mouse mode, hold left mouse in the field, drag horizontally up to 240 pixels
for full pull, move vertically to aim, then release. Space releases the current
prediction. The starting example is 75% power and +24°; small adjustments matter
at the longer range.

| Key | Action |
| --- | --- |
| Space | Record position / manually release with fresh tracking / shoot in mouse mode |
| R | Restart the round, keeping calibration; clear paths and reset game camera |
| C | Restart calibration and the round |
| H | Swap drawing hand and recalibrate |
| Esc | Menu; close the webcam and restore the initial view |
| Q | Quit |

## Code structure

| File | Responsibility |
| --- | --- |
| `main.py` | Menu/calibration/play/finish; one loop and one shared release gate |
| `archer_tracker_test.py` | Existing MediaPipe pose/hand tracking and gesture/wrist stabilization |
| `controls.py` | Calibrated measurements, smoothing, drawing state and confirmed release |
| `camera.py` | Webcam worker connection, fresh snapshots, timeouts and cleanup |
| `camera_worker.py` | Model inference, camera capture and annotated preview |
| `tracking_clock.py` | Shared OS clock for UI and worker, including macOS Python 3.9 |
| `physics.py` | Projectile equations, elevation bounds, target dimensions and scoring |
| `game_mechanics.py` | Flight, three-arrow round, impacts and immutable completed-shot history |
| `viewport.py` | Game camera: aim → follow → impact → return |
| `renderer.py` | Practice screens: parallax pixel campus, board, arrows, dotted paths and panels |
| `levels.py` | The ten campaign levels as data: range, board size, arrows, score, bow, wind, hills, obstacles |
| `campaign.py` | Campaign flight (wind, terrain, obstacles, moving board), arrow-budget round, saved progress |
| `campaign_renderer.py` | Campaign HUD, minimap, hills/obstacles, level select, briefing and result screens |
| `admin.py` | Admin password (salted hash), lockout and admin options applied to levels |
| `campaign_solver.py` | Finds gold shots for a layout; used by tests to prove every level is solvable |
| `pixelart/` | Pixel-art kit: canvas, font, character sprites, UI widgets, parallax scenery |
| `archer.py` | Previous vector archer (no longer drawn; kept for reference) |
| `test_game.py` | Physics, history, controls, worker lifecycle, viewport and SDL event regressions |
| `test_tracking_clock.py` | Real spawned-process regression after waiting in the menu |
| `launch_game.py` | Recipient's environment, dependency checks, setup and startup |
| `build_share.py` | Complete sharing ZIP; excludes environments, caches and previews |
| `pose_landmarker_lite.task`, `hand_landmarker.task` | Local tracking models included in the ZIP |
| `legacy/` | Backups of the original official main, mechanics and physics |

Tracker callbacks publish pose/hand snapshots with timestamps. The controller
converts shoulder-scaled wrist gap and tilt into pull and elevation. Every
mouse, Space and gesture release reaches `Archidon.shoot`, which checks both the
round and game-camera readiness. The round creates a `Flight`; exact elapsed
time advances it. At its target-plane crossing or ground landing, it creates an
`Impact` and an immutable `CompletedShot` containing the shot and complete path.

The renderer evaluates world coordinates with `WorldCamera.pan_x/pan_y`. World
x increases toward the target; rendering subtracts it from screen x so arrows
fly left. The camera pans when the arrow reaches the middle of the field and
tracks high arcs vertically. Terrain, ruler, board and all saved paths share the
same transform. The HUD stays fixed on screen. The webcam inset is hidden while
following/returning so that it cannot cover a steep arrow; tracking continues.
Camera motion
never changes hand measurements or physics. A new round clears history; a new
arrow retains every previous path.

## Physics

Launch height is 1.4 m, target center is 1 m high, range is 35 m, and gravity is
9.81 m/s². Calibrated pull maps to **12–24 m/s**, allowing long shots while
making elevation and pull errors more noticeable.

```text
x(t) = speed * cos(angle) * t
y(t) = 1.4 + speed * sin(angle) * t - 0.5 * 9.81 * t²
```

Scoring retains the original ring boundaries: within 0.2 m of center earns 50,
within 0.4 m earns 25, and within 0.5 m earns 15; edges are inclusive. A miss or
short landing earns zero. The third impact is shown before the final score.

Prediction, animation and stored history use the same equations and stop at the
same impact. Large display steps cannot skip the target or change its score.
`Trajectory` and `Score_Calculator` remain available for course code. Tune target,
speed and scoring in `physics.py`, round length in `game_mechanics.py`, camera
behavior in `viewport.py`, and appearance in `renderer.py`/`archer.py`.

At exactly ±90°, horizontal speed is zero. Time-based flight, dotted prediction
and camera tracking remain valid; the arrow lands beneath its launch and scores
zero. The legacy `Trajectory` function returns coefficients for `y(x)` and
therefore explicitly rejects an exactly vertical path. It is not used to
animate the game. The renderer handles zero velocity at a vertical apex.

## Debugging and optimization

The refactored tracker/physics APIs now support the existing course and game
calls. Incomplete calibration, invalid physics inputs, stale manual releases,
duplicate gestures and queued draws during flight/return are guarded. Camera
startup and frozen-frame timeouts show the actual failure; partial startup,
blocked capture and normal shutdown release worker resources.

Both processes use the shared OS `CLOCK_MONOTONIC`. On macOS Python 3.9, process
local `time.monotonic()` values have different origins; using them across the
camera boundary previously turned menu time into a false tracking delay.
OpenCV and Pygame remain in separate spawned processes to keep their bundled
macOS SDL libraries separate and camera reads away from the game loop.

Each actual flight path is sampled once and reused for its trail/history.
Predictions and the antialiased character surface are cached until their pose
changes. The webcam inset reuses its converted surface between new frames.
Preview IPC uses 320×240 instead of 640×480 (75% fewer RGB bytes); model inputs
stay at 640×480, and the unchanged aspect ratio preserves angle/pull measurements.

## Validation

```sh
.venv/bin/python -m unittest discover -s "Official Game" -p "test_*.py" -v
.venv/bin/python "Official Game/main.py" --mouse --headless --frames 3 --screenshot "Official Game/preview.png"
```

60 tests cover scoring, exact paths, frame-rate independence, offscreen target,
arrow containment, camera follow/hold/return, persistent histories, input gates,
calibration, wide-gap draws, recovery without a gap reset, exact ±90° flight,
vertical-apex rendering, stale timestamps, long-frame landing timing,
worker timeouts/cleanup and a real spawned clock check.
A complete three-shot rendered playthrough also checks a short miss, a
red-ring hit and a bullseye, with scenery motion and final score. On this Mac,
that render benchmark measured about 0.7 ms per frame median; it excludes webcam
capture/model inference and is not a promise of total gameplay frame rate.

A separate check ran the production camera worker with the actual MediaPipe
models on a supplied person image after waiting in the menu. First-step
calibration completed, 40 distinct pose results arrived with ages of 43–91 ms,
and the worker shut down cleanly. The native Pygame window also passed a
90-frame mouse-mode launch and exit check.

`preview.png` shows the initial view; `preview_flight.png`, `preview_impact.png`
and `preview_history.png` show flight, landing and the next aiming view.
`playthrough.gif` demonstrates the entire round. Live human webcam gestures and
calibration still need a play session with the intended player.
Generated preview files are kept in the development folder and excluded from
the sharing ZIP to keep it small.
