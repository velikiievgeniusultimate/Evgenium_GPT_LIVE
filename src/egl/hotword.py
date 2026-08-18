from __future__ import annotations

import itertools
import json
import logging
import queue
import threading
import time
from pathlib import Path
from typing import Callable

from .microphone import resolve_input_sample_rate
from .phrases import normalize_phrase, phrase_matches

LOG = logging.getLogger(__name__)

DebugCallback = Callable[[dict[str, object]], None]
StatusCallback = Callable[[str, str, dict[str, object]], None]

# «Евгениум» is intentionally invented and is not expected to be in the stock
# Russian Vosk vocabulary. We keep it as the user-facing phrase, but map only
# the OOV token to a close, known acoustic surrogate for the decoder. The rest
# of the phrase stays exact and wake still requires a FINAL high-confidence
# result, so this is not fuzzy matching.
ACOUSTIC_WORD_FALLBACKS: dict[str, tuple[str, ...]] = {
    "евгениум": ("евгений",),
}


def _model_knows_word(model: object, word: str) -> bool:
    try:
        finder = getattr(model, "vosk_model_find_word")
        return int(finder(word)) >= 0
    except Exception:
        return False


def resolve_decoder_phrases(model: object, phrases: list[str]) -> list[str]:
    """Translate user-facing phrases into exact phrases representable by Vosk.

    Known words are preserved verbatim. Unknown words are replaced only through
    explicit acoustic fallbacks above. If a phrase cannot be represented at all,
    it is omitted instead of silently degrading to a one-word grammar.
    """
    resolved: list[str] = []
    for raw_phrase in phrases:
        phrase = normalize_phrase(raw_phrase)
        words = phrase.split()
        if not words:
            continue

        options: list[list[str]] = []
        representable = True
        for word in words:
            if _model_knows_word(model, word):
                options.append([word])
                continue

            replacements = [
                candidate
                for candidate in ACOUSTIC_WORD_FALLBACKS.get(word, ())
                if _model_knows_word(model, candidate)
            ]
            if not replacements:
                representable = False
                break
            options.append(replacements)

        if not representable:
            continue

        for combination in itertools.product(*options):
            candidate = " ".join(combination)
            if candidate and candidate not in resolved:
                resolved.append(candidate)
    return resolved


class HotwordListener:
    """Offline Russian wake/stop detector using Vosk.

    Wake and stop are intentionally asymmetric:
    - WAKE is conservative: exact decoder phrase, FINAL result only, and a
      strong per-word confidence floor.
    - STOP is aggressive: while Voice is active it may fire from a partial
      result as soon as the complete decoder stop phrase is present.
    """

    def __init__(
        self,
        model_path: Path,
        wake_aliases: list[str],
        stop_aliases: list[str],
        on_wake: Callable[[], None],
        on_stop: Callable[[], None],
        microphone_device: int | None = None,
        on_debug: DebugCallback | None = None,
        on_status: StatusCallback | None = None,
        wake_confidence_threshold: float = 0.86,
        stop_confidence_threshold: float = 0.35,
    ) -> None:
        self.model_path = model_path
        self.wake_aliases = wake_aliases
        self.stop_aliases = stop_aliases
        self.on_wake = on_wake
        self.on_stop = on_stop
        self.microphone_device = microphone_device
        self.on_debug = on_debug
        self.on_status = on_status
        self.wake_confidence_threshold = float(wake_confidence_threshold)
        self.stop_confidence_threshold = float(stop_confidence_threshold)
        self.decoder_wake_aliases = [normalize_phrase(x) for x in wake_aliases if normalize_phrase(x)]
        self.decoder_stop_aliases = [normalize_phrase(x) for x in stop_aliases if normalize_phrase(x)]
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._active = threading.Event()
        self._last_wake_trigger = 0.0
        self._stop_fired_for_session = False
        self._last_debug_key: tuple[object, ...] | None = None

    def _emit_status(self, event: str, detail: str = "", **data: object) -> None:
        if self.on_status is None:
            return
        try:
            self.on_status(event, detail, dict(data))
        except Exception:
            LOG.debug("Hotword status callback failed", exc_info=True)

    def set_voice_active(self, active: bool) -> None:
        if active:
            if not self._active.is_set():
                self._stop_fired_for_session = False
            self._active.set()
        else:
            self._active.clear()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="egl-hotword", daemon=True)
        self._thread.start()

    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def close(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    @staticmethod
    def _confidence(payload: dict[str, object], *, final: bool) -> float | None:
        key = "result" if final else "partial_result"
        raw_words = payload.get(key)
        if not isinstance(raw_words, list) or not raw_words:
            return None
        values: list[float] = []
        for item in raw_words:
            if not isinstance(item, dict):
                continue
            try:
                values.append(float(item["conf"]))
            except (KeyError, TypeError, ValueError):
                continue
        return min(values) if values else None

    def _emit_debug(
        self,
        *,
        text: str,
        final: bool,
        confidence: float | None,
        wake_match: bool,
        stop_match: bool,
        accepted: str | None,
        reason: str,
    ) -> None:
        if self.on_debug is None:
            return
        active = self._active.is_set()
        key = (
            text,
            final,
            None if confidence is None else round(confidence, 3),
            active,
            wake_match,
            stop_match,
            accepted,
            reason,
        )
        if key == self._last_debug_key:
            return
        self._last_debug_key = key
        try:
            self.on_debug(
                {
                    "text": text,
                    "voice_active": active,
                    "final": final,
                    "confidence": confidence,
                    "wake_match": wake_match,
                    "stop_match": stop_match,
                    "accepted": accepted,
                    "reason": reason,
                    "wake_threshold": self.wake_confidence_threshold,
                    "stop_threshold": self.stop_confidence_threshold,
                    "decoder_wake_aliases": self.decoder_wake_aliases,
                    "decoder_stop_aliases": self.decoder_stop_aliases,
                }
            )
        except Exception:
            LOG.debug("Hotword debug callback failed", exc_info=True)

    def _dispatch(
        self,
        text: str,
        *,
        final: bool = True,
        confidence: float | None = 1.0,
    ) -> None:
        normalized = normalize_phrase(text)
        active = self._active.is_set()

        wake_match = normalized in self.decoder_wake_aliases
        stop_match = phrase_matches(normalized, self.decoder_stop_aliases)

        accepted: str | None = None
        reason = "no_match"
        now = time.monotonic()

        if active:
            confidence_ok = confidence is None or confidence >= self.stop_confidence_threshold
            if stop_match and confidence_ok and not self._stop_fired_for_session:
                self._stop_fired_for_session = True
                accepted = "stop"
                reason = "partial_fast_stop" if not final else "final_stop"
                self.on_stop()
            elif stop_match and self._stop_fired_for_session:
                reason = "stop_already_fired"
            elif stop_match:
                reason = "stop_confidence_too_low"
        else:
            if not final and wake_match:
                reason = "wake_partial_rejected"
            elif final and wake_match:
                if confidence is None:
                    reason = "wake_missing_confidence"
                elif confidence < self.wake_confidence_threshold:
                    reason = "wake_confidence_too_low"
                elif now - self._last_wake_trigger < 1.5:
                    reason = "wake_debounce"
                else:
                    self._last_wake_trigger = now
                    accepted = "wake"
                    reason = "strict_final_wake"
                    self.on_wake()

        self._emit_debug(
            text=normalized,
            final=final,
            confidence=confidence,
            wake_match=wake_match,
            stop_match=stop_match,
            accepted=accepted,
            reason=reason,
        )

    def _run(self) -> None:
        try:
            import sounddevice as sd
            from vosk import KaldiRecognizer, Model, SetLogLevel

            SetLogLevel(-1)
            model = Model(str(self.model_path))
            self.decoder_wake_aliases = resolve_decoder_phrases(model, self.wake_aliases)
            self.decoder_stop_aliases = resolve_decoder_phrases(model, self.stop_aliases)
            if not self.decoder_wake_aliases:
                raise RuntimeError(
                    f"Wake phrase is not representable by the Vosk vocabulary: {self.wake_aliases!r}"
                )
            if not self.decoder_stop_aliases:
                raise RuntimeError(
                    f"STOP phrase is not representable by the Vosk vocabulary: {self.stop_aliases!r}"
                )

            grammar = sorted(
                set(self.decoder_wake_aliases + self.decoder_stop_aliases + ["[unk]"])
            )
            self._emit_status(
                "HOTWORD_GRAMMAR",
                "Vosk decoder grammar prepared",
                user_wake=self.wake_aliases,
                user_stop=self.stop_aliases,
                decoder_wake=self.decoder_wake_aliases,
                decoder_stop=self.decoder_stop_aliases,
            )
        except Exception as exc:
            LOG.exception("Hotword engine initialization failed")
            self._emit_status("HOTWORD_FATAL", str(exc))
            return

        retry_delay = 2.0
        while not self._stop.is_set():
            try:
                sample_rate = resolve_input_sample_rate(sd, self.microphone_device)
                blocksize = max(320, int(round(sample_rate * 0.10)))

                recognizer = KaldiRecognizer(
                    model,
                    sample_rate,
                    json.dumps(grammar, ensure_ascii=False),
                )
                recognizer.SetWords(True)
                try:
                    recognizer.SetPartialWords(True)
                except AttributeError:
                    LOG.warning("This Vosk build lacks SetPartialWords; STOP will still use exact partial text")

                audio_q: queue.Queue[bytes] = queue.Queue(maxsize=20)

                def callback(indata, frames, time_info, status):  # type: ignore[no-untyped-def]
                    if status:
                        LOG.debug("Microphone status: %s", status)
                    try:
                        audio_q.put_nowait(bytes(indata))
                    except queue.Full:
                        pass

                with sd.RawInputStream(
                    samplerate=sample_rate,
                    blocksize=blocksize,
                    dtype="int16",
                    channels=1,
                    device=self.microphone_device,
                    callback=callback,
                ):
                    LOG.info(
                        "Hotword listener ready (device=%s, sample_rate=%d Hz, wake=%s, stop=%s, wake>=%.2f final-only, stop>=%.2f partial-ok)",
                        self.microphone_device,
                        sample_rate,
                        self.decoder_wake_aliases,
                        self.decoder_stop_aliases,
                        self.wake_confidence_threshold,
                        self.stop_confidence_threshold,
                    )
                    self._emit_status(
                        "HOTWORD_READY",
                        "background microphone listener is active",
                        device=self.microphone_device,
                        sample_rate=sample_rate,
                        decoder_wake=self.decoder_wake_aliases,
                        decoder_stop=self.decoder_stop_aliases,
                    )
                    retry_delay = 2.0
                    while not self._stop.is_set():
                        try:
                            chunk = audio_q.get(timeout=0.20)
                        except queue.Empty:
                            continue

                        if recognizer.AcceptWaveform(chunk):
                            payload = json.loads(recognizer.Result())
                            text = str(payload.get("text", ""))
                            if text:
                                self._dispatch(
                                    text,
                                    final=True,
                                    confidence=self._confidence(payload, final=True),
                                )
                        else:
                            payload = json.loads(recognizer.PartialResult())
                            partial = str(payload.get("partial", ""))
                            if partial:
                                self._dispatch(
                                    partial,
                                    final=False,
                                    confidence=self._confidence(payload, final=False),
                                )
            except Exception as exc:
                LOG.exception(
                    "Hotword audio stream failed; retrying in %.0f seconds",
                    retry_delay,
                )
                self._emit_status(
                    "HOTWORD_ERROR",
                    str(exc),
                    retry_in_seconds=retry_delay,
                    device=self.microphone_device,
                )
                if self._stop.wait(retry_delay):
                    break
                retry_delay = min(retry_delay * 2.0, 30.0)
