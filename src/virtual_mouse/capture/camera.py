"""Threaded webcam capture that always exposes the newest frame (low latency, bounded memory)."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Protocol

from ..config import CameraConfig
from ..types import CapturedFrame

log = logging.getLogger(__name__)


class CameraError(RuntimeError):
    """Raised when the camera cannot be opened or stops delivering frames."""


class CaptureLike(Protocol):
    def isOpened(self) -> bool: ...
    def read(self) -> tuple[bool, Any]: ...
    def release(self) -> None: ...


CaptureFactory = Callable[[CameraConfig], CaptureLike]


def default_capture_factory(cfg: CameraConfig) -> CaptureLike:
    """Open a cv2.VideoCapture (imported lazily so tests need no camera/cv2 GUI)."""
    import cv2

    backends = {"auto": cv2.CAP_ANY, "dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF}
    cap = cv2.VideoCapture(cfg.device_index, backends[cfg.backend])
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.height)
    cap.set(cv2.CAP_PROP_FPS, cfg.fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # ignored by some backends; harmless
    return cap


class Camera:
    """Background grabber. `read()` returns each frame at most once; stale frames are dropped."""

    def __init__(self, config: CameraConfig, capture_factory: CaptureFactory = default_capture_factory) -> None:
        self._config = config
        self._factory = capture_factory
        self._cap: CaptureLike | None = None
        self._thread: threading.Thread | None = None
        self._cond = threading.Condition()
        self._stop = threading.Event()
        self._latest: CapturedFrame | None = None
        self._index = 0
        self._last_read = 0
        self._last_ts = -1
        self._error: CameraError | None = None

    # -- lifecycle -------------------------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None:
            raise CameraError("camera already started")
        cap = self._factory(self._config)
        if not cap.isOpened():
            cap.release()
            raise CameraError(f"could not open camera device {self._config.device_index}")
        self._cap = cap
        self._stop.clear()
        self._error = None
        self._thread = threading.Thread(target=self._run, name="camera-grabber", daemon=True)
        self._thread.start()
        log.info("camera started (device %d)", self._config.device_index)

    def stop(self) -> None:
        """Stop the thread and always release the device. Idempotent."""
        self._stop.set()
        with self._cond:
            self._cond.notify_all()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=2.0)
        cap, self._cap = self._cap, None
        if cap is not None:
            cap.release()
            log.info("camera released")

    def __enter__(self) -> "Camera":
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    # -- consumption -----------------------------------------------------------------------
    def read(self, timeout: float = 0.5) -> CapturedFrame | None:
        """Return the newest unseen frame, or None on timeout. Raises CameraError if the grabber failed."""
        with self._cond:
            self._cond.wait_for(
                lambda: self._index > self._last_read or self._error is not None or self._stop.is_set(),
                timeout=timeout,
            )
            if self._error is not None:
                raise self._error
            if self._index > self._last_read and self._latest is not None:
                self._last_read = self._index
                return self._latest
            return None

    # -- internals -------------------------------------------------------------------------
    def _run(self) -> None:
        failures = 0
        assert self._cap is not None
        while not self._stop.is_set():
            try:
                ok, image = self._cap.read()
            except Exception as exc:  # noqa: BLE001 - device drivers can raise anything
                self._fail(CameraError(f"camera read raised: {exc!r}"))
                return
            if not ok or image is None:
                failures += 1
                if failures >= self._config.max_read_failures:
                    self._fail(CameraError(f"camera failed {failures} consecutive reads"))
                    return
                time.sleep(0.005)
                continue
            failures = 0
            ts = max(time.monotonic_ns() // 1_000_000, self._last_ts + 1)
            self._last_ts = ts
            with self._cond:
                self._index += 1
                self._latest = CapturedFrame(image=image, timestamp_ms=ts, index=self._index)
                self._cond.notify_all()

    def _fail(self, error: CameraError) -> None:
        log.error("%s", error)
        with self._cond:
            self._error = error
            self._cond.notify_all()
