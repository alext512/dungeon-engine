"""Window/display bootstrap helpers."""

from __future__ import annotations

import sys


def configure_process_dpi_awareness() -> None:
    """Opt into sharp per-monitor DPI handling on Windows before opening a window."""
    if sys.platform != "win32":
        return

    try:
        import ctypes

        user32 = ctypes.windll.user32
        per_monitor_v2 = ctypes.c_void_p(-4)
        if hasattr(user32, "SetProcessDpiAwarenessContext"):
            if user32.SetProcessDpiAwarenessContext(per_monitor_v2):
                return

        shcore = getattr(ctypes.windll, "shcore", None)
        if shcore is not None and hasattr(shcore, "SetProcessDpiAwareness"):
            try:
                # PROCESS_PER_MONITOR_DPI_AWARE
                shcore.SetProcessDpiAwareness(2)
                return
            except OSError:
                pass

        if hasattr(user32, "SetProcessDPIAware"):
            user32.SetProcessDPIAware()
    except Exception:
        # Rendering should still work even if DPI-awareness setup fails.
        return
