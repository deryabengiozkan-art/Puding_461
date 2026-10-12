"""Build a portable source ZIP with local assets/models and no virtualenv.

Run: python build_share.py
Optional: python build_share.py --output /path/to/Archidon_Portable.zip
"""
import argparse
from pathlib import Path
import zipfile


FOLDER = Path(__file__).resolve().parent
FILES = (
    "README.md", "main.py", "renderer.py", "archer.py", "viewport.py",
    "physics.py", "game_mechanics.py", "controls.py", "camera.py",
    "camera_worker.py", "tracking_clock.py", "archer_tracker_test.py",
    "test_game.py", "test_tracking_clock.py", "requirements.txt",
    "requirements-mouse.txt", "launch_game.py", "build_share.py",
    "Play Windows.bat", "Play macOS.command", "play_linux.sh",
    "pose_landmarker_lite.task", "hand_landmarker.task",
    "characters.py", "duel.py", "duel_renderer.py", "duel_tracking.py", "hitbox.py",
    "duel_camera.py", "duel_camera_worker.py", "test_characters.py",
    "test_duel.py", "test_duel_ui.py",
    "character_selection.py", "duel_aim.py", "test_selection_flow.py",
    "test_duel_aim.py", "test_duel_movement.py",
    "levels.py", "admin.py", "campaign.py", "campaign_renderer.py", "campaign_solver.py", "test_campaign.py",
    "pixelart/__init__.py", "pixelart/kit.py", "pixelart/font.py", "pixelart/sprites.py",
    "pixelart/ui.py", "pixelart/scenery.py", "pixelart/painter.py",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=FOLDER.parent / "Archidon_Portable.zip")
    args = parser.parse_args()
    files = [FOLDER / name for name in FILES]
    # Optional, more accurate pose model for players standing far back.
    if (FOLDER / "pose_landmarker_full.task").is_file():
        files.append(FOLDER / "pose_landmarker_full.task")
    # Design previews in assets/pixel_art are not needed to play: all art is drawn by pixelart/.
    files.extend(sorted(path for path in (FOLDER / "assets").rglob("*")
                        if path.is_file() and "pixel_art" not in path.parts))
    missing = [str(path.relative_to(FOLDER)) for path in files if not path.is_file()]
    if missing:
        parser.error("Cannot share an incomplete game: " + ", ".join(missing))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, "Official Game/" + path.relative_to(FOLDER).as_posix())
    print(str(args.output.resolve()))
    print(f"{len(files)} files, {args.output.stat().st_size / 1024 / 1024:.1f} MiB; no virtualenv or cache included.")


if __name__ == "__main__":
    main()
