from __future__ import annotations

import argparse
import json
import math
import os
import sys
import threading
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=74)
    parser.add_argument("--margin", type=int, default=18)
    args = parser.parse_args()

    # On KDE Wayland, XWayland gives this tiny overlay deterministic global placement.
    if "QT_QPA_PLATFORM" not in os.environ and os.environ.get("DISPLAY"):
        os.environ["QT_QPA_PLATFORM"] = "xcb"

    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QColor, QPainter, QPen
    from PySide6.QtWidgets import QApplication, QWidget

    class Orb(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.mode = "starting"
            self.level = 0.0
            self._born = time.monotonic()
            flags = Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
            flags |= Qt.WindowTransparentForInput
            self.setWindowFlags(flags)
            self.setAttribute(Qt.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WA_ShowWithoutActivating, True)
            self.resize(args.size, args.size)
            self._place()
            self.show()

            timer = QTimer(self)
            timer.timeout.connect(self._tick)
            timer.start(33)
            self._timer = timer

        def _place(self) -> None:
            screen = QApplication.primaryScreen()
            if not screen:
                return
            geo = screen.availableGeometry()
            self.move(geo.left() + args.margin, geo.bottom() - self.height() - args.margin + 1)

        def _tick(self) -> None:
            self.level *= 0.90
            self.update()

        def apply(self, payload: dict) -> None:
            if "mode" in payload:
                self.mode = str(payload["mode"])
            if "level" in payload:
                try:
                    self.level = max(self.level, min(1.0, float(payload["level"])))
                except (TypeError, ValueError):
                    pass
            if payload.get("quit"):
                QApplication.quit()

        def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            t = time.monotonic() - self._born
            breath = (math.sin(t * 3.1) + 1.0) / 2.0
            activity = max(self.level, 0.10 + breath * 0.08)
            if self.mode == "error":
                base = QColor(235, 82, 82)
            elif self.mode == "starting":
                base = QColor(246, 190, 70)
            else:
                base = QColor(93, 214, 255)

            center = self.rect().center()
            outer_r = (min(self.width(), self.height()) / 2.0 - 3.0) * (0.86 + activity * 0.14)
            glow = QColor(base)
            glow.setAlpha(int(55 + activity * 90))
            p.setPen(QPen(glow, 5.0 + activity * 4.0))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(center, int(outer_r - 2), int(outer_r - 2))

            inner = QColor(base)
            inner.setAlpha(225)
            p.setPen(Qt.NoPen)
            p.setBrush(inner)
            inner_r = outer_r * (0.48 + activity * 0.20)
            p.drawEllipse(center, int(inner_r), int(inner_r))

    app = QApplication(sys.argv)
    orb = Orb()

    def reader() -> None:
        for line in sys.stdin:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            QTimer.singleShot(0, orb, lambda p=payload: orb.apply(p))
        QTimer.singleShot(0, app.quit)

    threading.Thread(target=reader, name="egl-indicator-input", daemon=True).start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
