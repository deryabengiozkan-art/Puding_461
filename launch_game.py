"""Create this computer's own environment, install dependencies, and play.

Run: python launch_game.py
Mouse only: python launch_game.py --mouse
Validate the current Python without installing: python launch_game.py --check
"""
import argparse
import json
import platform
import struct
import subprocess
import sys
import sysconfig
import venv
from pathlib import Path


FOLDER = Path(__file__).resolve().parent
MODEL_NAMES = ("pose_landmarker_lite.task", "hand_landmarker.task")
CHECK_PACKAGES = """
import json, sys
from importlib.metadata import PackageNotFoundError, version
issues = []
for name, expected in json.loads(sys.argv[1]).items():
    try:
        actual = version(name)
        if actual != expected:
            issues.append(name + ': expected ' + expected + ', found ' + actual)
    except PackageNotFoundError:
        issues.append(name + ': not installed')
if issues:
    print('\\n'.join(issues))
    sys.exit(1)
"""


def requirement_pins(path):
    """Read our small pinned requirement files, including their local includes."""
    pins = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line.startswith("-r "):
            pins.update(requirement_pins(path.parent / line[3:].strip()))
        elif line:
            name, value = line.split("==", 1)
            pins[name.strip()] = value.strip()
    return pins


def check_packages(python, pins):
    # Metadata checks never import SDL or the vision libraries in this launcher.
    return subprocess.run([str(python), "-c", CHECK_PACKAGES, json.dumps(pins)],
                          cwd=str(FOLDER), text=True, capture_output=True)


def camera_platform_error():
    """Explain known missing binary wheels before starting a long install."""
    machine = platform.machine().lower()
    if sys.platform == "darwin":
        if machine != "arm64":
            return "Camera tracking needs Apple Silicon Python; this MediaPipe version has no Intel macOS wheel."
        system_version = platform.mac_ver()[0]
        if system_version and int(system_version.split(".", 1)[0]) < 11:
            return "Camera tracking needs macOS 11 or newer."
    elif sys.platform == "win32":
        if sysconfig.get_platform() != "win-amd64":
            return "These pinned packages need x64 Python on Windows, including Windows ARM devices."
    elif sys.platform.startswith("linux"):
        if machine not in ("x86_64", "amd64"):
            return "The pinned MediaPipe version has no Linux ARM camera-tracking wheel."
        library, version = platform.libc_ver()
        if library and (library != "glibc" or tuple(map(int, version.split(".")[:2])) < (2, 28)):
            return "Camera tracking needs Linux with glibc 2.28 or newer."
    else:
        return "Camera tracking is packaged for Windows x64, Apple Silicon macOS, and Linux x86_64."
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--setup-only", action="store_true", help="Install dependencies, then exit")
    parser.add_argument("--check", action="store_true", help="Check this Python and local files; do not install")
    args, game_args = parser.parse_known_args()
    if not (3, 9) <= sys.version_info[:2] <= (3, 12) or struct.calcsize("P") != 8:
        print("Use 64-bit Python 3.9-3.12. Python 3.11 is recommended for this game.")
        print("Download Python at https://www.python.org/downloads/ and run this launcher again.")
        return 1

    mouse_only = any(flag in game_args for flag in ("--mouse", "--duel-keyboard", "--duel-demo"))
    issue = None if mouse_only else camera_platform_error()
    if issue:
        print(issue)
        print("Use launch_game.py --mouse for practice; see README.md for platform details.")
        return 1
    requirements = FOLDER / ("requirements-mouse.txt" if mouse_only else "requirements.txt")
    needed = [FOLDER / "main.py", requirements, FOLDER / "assets" / "pixelMakinaG.jpeg"]
    if not mouse_only:
        needed.extend(FOLDER / name for name in MODEL_NAMES)
    missing = [str(path.relative_to(FOLDER)) for path in needed if not path.is_file()]
    if missing:
        print("Game files are missing: " + ", ".join(missing))
        print("Extract the entire shared ZIP before running the launcher.")
        return 1
    pins = requirement_pins(requirements)

    if args.check:
        result = check_packages(sys.executable, pins)
        if result.returncode:
            print(result.stdout or result.stderr)
            print("Run launch_game.py without --check to create the game's local environment.")
        else:
            print("Local game files and selected dependencies are ready.")
        return result.returncode

    environment = FOLDER / ".venv"
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not environment.exists():
        print("Creating a Python environment for this computer...", flush=True)
        venv.EnvBuilder(with_pip=True).create(str(environment))
    if not python.is_file():
        print("The local .venv folder is incomplete or was copied from another computer.")
        print("Remove that .venv folder and run the launcher again; it will create a new one.")
        return 1

    result = check_packages(python, pins)
    if result.returncode:
        print("Installing game dependencies. First setup needs an internet connection...", flush=True)
        subprocess.check_call([str(python), "-m", "pip", "install", "--upgrade", "pip"], cwd=str(FOLDER))
        subprocess.check_call([str(python), "-m", "pip", "install", "--only-binary=:all:",
                               "-r", str(requirements)], cwd=str(FOLDER))
        result = check_packages(python, pins)
        if result.returncode:
            print(result.stdout or result.stderr)
            return 1
    if args.setup_only:
        print("Setup complete. Run the launcher again to play.")
        return 0
    return subprocess.call([str(python), str(FOLDER / "main.py"), *game_args], cwd=str(FOLDER))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nSetup or game stopped.")
        raise SystemExit(130)
    except (OSError, subprocess.CalledProcessError) as exc:
        print("Could not start the game: " + str(exc))
        print("For installation errors, check the internet connection and the supported platforms in README.md.")
        raise SystemExit(1)
