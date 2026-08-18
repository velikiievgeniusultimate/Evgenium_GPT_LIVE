from __future__ import annotations

import json
import math
import subprocess
import sys
import time
from array import array

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .config import load_config, save_config
from .control import send_command
from .integration import install_integrations
from .state import debug_screenshot_path, read_debug_events, read_state


class DebugWindow(QDialog):
    """Live view of the otherwise invisible EGL browser and event pipeline."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("EGL — отладка Voice")
        self.resize(920, 820)
        self._last_snapshot_request = 0.0

        layout = QVBoxLayout(self)

        self.state_label = QLabel()
        self.hotword_label = QLabel("Vosk: —")
        self.stop_label = QLabel("STOP: —")
        self.hotword_label.setWordWrap(True)
        self.stop_label.setWordWrap(True)
        layout.addWidget(self.state_label)
        layout.addWidget(self.hotword_label)
        layout.addWidget(self.stop_label)

        controls = QHBoxLayout()
        wake = QPushButton("Wake")
        wake.clicked.connect(lambda: self._command("wake"))
        stop = QPushButton("STOP")
        stop.clicked.connect(lambda: self._command("stop"))
        snapshot = QPushButton("Снимок сейчас")
        snapshot.clicked.connect(lambda: self._request_snapshot(quiet=False))
        reload_page = QPushButton("Reload ChatGPT")
        reload_page.clicked.connect(lambda: self._command("browser_reload"))
        self.live_preview = QCheckBox("Живое превью")
        self.live_preview.setChecked(True)
        for widget in (wake, stop, snapshot, reload_page, self.live_preview):
            controls.addWidget(widget)
        controls.addStretch(1)
        layout.addLayout(controls)

        preview_group = QGroupBox("Скрытая вкладка ChatGPT (Xvfb)")
        preview_layout = QVBoxLayout(preview_group)
        self.preview = QLabel("Жду первый снимок…")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(640, 360)
        self.preview.setStyleSheet("QLabel { background: #111; color: #aaa; border: 1px solid #444; }")
        preview_layout.addWidget(self.preview)
        layout.addWidget(preview_group, 2)

        log_group = QGroupBox("События EGL")
        log_layout = QVBoxLayout(log_group)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        log_layout.addWidget(self.log)
        layout.addWidget(log_group, 1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh)
        self.timer.start(700)
        self._request_snapshot(quiet=True)
        self._refresh()

    def _command(self, command: str) -> None:
        try:
            send_command(command)
        except OSError as exc:
            QMessageBox.warning(self, "EGL debug", f"Daemon не отвечает:\n{exc}")

    def _request_snapshot(self, *, quiet: bool) -> None:
        self._last_snapshot_request = time.monotonic()
        self._command("debug_snapshot_quiet" if quiet else "debug_snapshot")

    @staticmethod
    def _format_event(item: dict) -> str:
        ts = item.get("ts", 0)
        try:
            stamp = time.strftime("%H:%M:%S", time.localtime(float(ts)))
        except Exception:
            stamp = "??:??:??"
        event = str(item.get("event", "?"))
        detail = str(item.get("detail", ""))
        extra = {k: v for k, v in item.items() if k not in {"ts", "event", "detail"}}
        suffix = f"  {json.dumps(extra, ensure_ascii=False)}" if extra else ""
        return f"[{stamp}] {event}: {detail}{suffix}"

    def _refresh(self) -> None:
        state = read_state()
        self.state_label.setText(
            f"Состояние: <b>{state.mode}</b> — {state.detail or 'без деталей'}"
        )

        events = read_debug_events(140)
        hotwords = [e for e in events if e.get("event") == "hotword_heard"]
        if hotwords:
            last = hotwords[-1]
            self.hotword_label.setText(
                "Vosk услышал: <b>{}</b> | voice_active={} | wake_match={} | stop_match={}".format(
                    last.get("detail", ""),
                    last.get("voice_active"),
                    last.get("wake_match"),
                    last.get("stop_match"),
                )
            )

        stops = [e for e in events if e.get("event") == "voice_stopped"]
        if stops:
            last = stops[-1]
            verified = last.get("verified")
            ui_after = last.get("ui_active_after")
            self.stop_label.setText(
                f"Последний STOP: <b>verified={verified}</b> | Voice UI после остановки: <b>{ui_after}</b>"
            )

        text = "\n".join(self._format_event(e) for e in events)
        if self.log.toPlainText() != text:
            scroll = self.log.verticalScrollBar()
            at_bottom = scroll.value() >= max(0, scroll.maximum() - 5)
            self.log.setPlainText(text)
            if at_bottom:
                scroll.setValue(scroll.maximum())

        path = debug_screenshot_path()
        if path.exists():
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                self.preview.setPixmap(
                    pixmap.scaled(
                        self.preview.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )

        if self.live_preview.isChecked() and time.monotonic() - self._last_snapshot_request >= 1.2:
            self._request_snapshot(quiet=True)


class SettingsWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Evgenium GPT LIVE — EGL")
        self.resize(700, 600)
        self.cfg = load_config()
        self._mic_stream = None
        self._mic_level = 0.0
        self._debug_window: DebugWindow | None = None

        root = QWidget(self)
        layout = QVBoxLayout(root)
        self.setCentralWidget(root)

        title = QLabel("<h2>Evgenium GPT LIVE</h2>")
        layout.addWidget(title)

        status_group = QGroupBox("Состояние")
        status_layout = QVBoxLayout(status_group)
        self.service_label = QLabel()
        self.state_label = QLabel()
        self.browser_policy = QLabel(
            "Служебный Chromium: <b>всегда запущен</b> на приватном виртуальном дисплее Xvfb. "
            "Plasma его не видит; вкладка ChatGPT прогревается в фоне."
        )
        self.browser_policy.setWordWrap(True)
        status_layout.addWidget(self.service_label)
        status_layout.addWidget(self.state_label)
        status_layout.addWidget(self.browser_policy)

        controls = QHBoxLayout()
        wake = QPushButton("Запустить Voice")
        wake.clicked.connect(lambda: self._command("wake"))
        stop = QPushButton("Стоп")
        stop.clicked.connect(lambda: self._command("stop"))
        reload_browser = QPushButton("Перезагрузить скрытую вкладку")
        reload_browser.clicked.connect(lambda: self._command("browser_reload"))
        debug = QPushButton("Открыть отладчик")
        debug.clicked.connect(self._open_debug)
        for button in (wake, stop, reload_browser, debug):
            controls.addWidget(button)
        status_layout.addLayout(controls)
        layout.addWidget(status_group)

        audio_group = QGroupBox("Микрофон")
        audio_layout = QVBoxLayout(audio_group)
        audio_form = QFormLayout()
        self.microphone = QComboBox()
        audio_form.addRow("Устройство:", self.microphone)
        audio_layout.addLayout(audio_form)

        test_row = QHBoxLayout()
        self.test_button = QPushButton("Проверить микрофон")
        self.test_button.clicked.connect(self._toggle_mic_test)
        self.level = QProgressBar()
        self.level.setRange(0, 100)
        self.level.setValue(0)
        test_row.addWidget(self.test_button)
        test_row.addWidget(self.level, 1)
        audio_layout.addLayout(test_row)
        layout.addWidget(audio_group)

        behavior_group = QGroupBox("Поведение")
        behavior_form = QFormLayout(behavior_group)
        self.indicator_enabled = QCheckBox("Показывать живой круг во время Voice")
        self.indicator_enabled.setChecked(self.cfg.indicator_enabled)
        self.indicator_size = QSpinBox()
        self.indicator_size.setRange(44, 180)
        self.indicator_size.setSuffix(" px")
        self.indicator_size.setValue(self.cfg.indicator_size)
        behavior_form.addRow(self.indicator_enabled)
        behavior_form.addRow("Размер круга:", self.indicator_size)
        layout.addWidget(behavior_group)

        chat_group = QGroupBox("ChatGPT")
        chat_form = QFormLayout(chat_group)
        chat_label = QLabel(self.cfg.chat_url or "Не настроен")
        chat_label.setWordWrap(True)
        chat_form.addRow("Закреплённый чат:", chat_label)
        layout.addWidget(chat_group)

        bottom = QHBoxLayout()
        restart = QPushButton("Перезапустить EGL")
        restart.clicked.connect(self._restart_service)
        save = QPushButton("Сохранить и применить")
        save.clicked.connect(self._save)
        bottom.addStretch(1)
        bottom.addWidget(restart)
        bottom.addWidget(save)
        layout.addLayout(bottom)

        self._load_microphones()
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start(1200)
        self._meter_timer = QTimer(self)
        self._meter_timer.timeout.connect(self._refresh_meter)
        self._meter_timer.start(60)
        self._refresh_status()

    def _open_debug(self) -> None:
        if self._debug_window is None:
            self._debug_window = DebugWindow(self)
        self._debug_window.show()
        self._debug_window.raise_()
        self._debug_window.activateWindow()

    def _load_microphones(self) -> None:
        self.microphone.clear()
        self.microphone.addItem("Системный по умолчанию", None)
        try:
            import sounddevice as sd

            for index, device in enumerate(sd.query_devices()):
                if int(device.get("max_input_channels", 0)) <= 0:
                    continue
                name = str(device.get("name", f"Device {index}"))
                self.microphone.addItem(f"{index}: {name}", index)
        except Exception as exc:
            self.microphone.addItem(f"Ошибка чтения устройств: {exc}", "error")

        wanted = self.cfg.microphone_device
        for i in range(self.microphone.count()):
            if self.microphone.itemData(i) == wanted:
                self.microphone.setCurrentIndex(i)
                break

    def _selected_device(self):
        value = self.microphone.currentData()
        return value if isinstance(value, int) else None

    def _toggle_mic_test(self) -> None:
        if self._mic_stream is not None:
            self._stop_mic_test()
            return
        try:
            import sounddevice as sd

            self._mic_stream = sd.RawInputStream(
                samplerate=16000,
                blocksize=1600,
                dtype="int16",
                channels=1,
                device=self._selected_device(),
                callback=self._mic_callback,
            )
            self._mic_stream.start()
            self.test_button.setText("Остановить тест")
        except Exception as exc:
            self._mic_stream = None
            QMessageBox.warning(self, "EGL", f"Не удалось открыть микрофон:\n{exc}")

    def _mic_callback(self, indata, frames, time_info, status) -> None:  # type: ignore[no-untyped-def]
        try:
            samples = array("h")
            samples.frombytes(bytes(indata))
            if not samples:
                self._mic_level = 0.0
                return
            mean_square = sum(float(v) * float(v) for v in samples) / len(samples)
            rms = math.sqrt(mean_square) / 32768.0
            self._mic_level = min(1.0, rms * 8.0)
        except Exception:
            self._mic_level = 0.0

    def _refresh_meter(self) -> None:
        self.level.setValue(int(self._mic_level * 100))

    def _stop_mic_test(self) -> None:
        stream = self._mic_stream
        self._mic_stream = None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        self._mic_level = 0.0
        self.level.setValue(0)
        self.test_button.setText("Проверить микрофон")

    def _command(self, command: str) -> None:
        try:
            send_command(command)
        except OSError as exc:
            QMessageBox.warning(self, "EGL", f"EGL daemon не отвечает:\n{exc}")

    def _service_active(self) -> str:
        try:
            proc = subprocess.run(
                ["systemctl", "--user", "is-active", "egl.service"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                check=False,
            )
            return proc.stdout.strip() or "unknown"
        except Exception:
            return "unknown"

    def _refresh_status(self) -> None:
        self.service_label.setText(f"systemd: <b>{self._service_active()}</b>")
        state = read_state()
        detail = f" — {state.detail}" if state.detail else ""
        self.state_label.setText(f"EGL: <b>{state.mode}</b>{detail}")

    def _restart_service(self) -> None:
        self._stop_mic_test()
        subprocess.run(["systemctl", "--user", "restart", "egl.service"], check=False)
        QTimer.singleShot(700, self._refresh_status)

    def _save(self) -> None:
        self._stop_mic_test()
        self.cfg.microphone_device = self._selected_device()
        self.cfg.browser_headless = True
        self.cfg.browser_keep_alive = True
        self.cfg.indicator_enabled = self.indicator_enabled.isChecked()
        self.cfg.indicator_size = self.indicator_size.value()
        save_config(self.cfg)
        install_integrations()
        self._restart_service()
        QMessageBox.information(self, "EGL", "Настройки сохранены и EGL перезапущен.")

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._stop_mic_test()
        super().closeEvent(event)


def run_gui() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Evgenium GPT LIVE")
    app.setOrganizationName("EGL")
    window = SettingsWindow()
    window.show()
    return app.exec()
