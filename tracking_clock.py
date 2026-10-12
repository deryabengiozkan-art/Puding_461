"""One monotonic clock origin for tracker timestamps in both processes.

On macOS Python 3.9, time.monotonic() starts at a different origin in each
process. CLOCK_MONOTONIC is the OS clock and is shared across processes.
Never subtract a camera-worker timestamp from a process-local UI clock.
"""
import time


def monotonic_seconds():
    if hasattr(time, 'clock_gettime') and hasattr(time, 'CLOCK_MONOTONIC'):
        return time.clock_gettime(time.CLOCK_MONOTONIC)
    # Platforms without clock_gettime (including Windows) share the origin
    # of Python's monotonic clock across processes in our supported versions.
    return time.monotonic()
