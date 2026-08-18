from __future__ import annotations

from typing import Any


COMMON_INPUT_SAMPLE_RATES = (48_000, 44_100, 32_000, 24_000, 22_050, 16_000)


def resolve_input_sample_rate(sd: Any, device: int | None) -> int:
    """Return a mono/int16 sample rate the selected PortAudio device accepts.

    EGL used to force every microphone to 16 kHz. Many USB interfaces (including
    common pro-audio devices) expose only 44.1/48 kHz through PortAudio, which
    caused PaErrorCode -9997. Prefer the device's native/default rate and verify
    it before falling back through a small set of common rates.
    """
    info = sd.query_devices(device, "input")
    if int(info.get("max_input_channels", 0)) < 1:
        raise RuntimeError("Selected audio device has no input channels")

    candidates: list[int] = []
    try:
        native = int(round(float(info.get("default_samplerate", 0))))
        if native > 0:
            candidates.append(native)
    except (TypeError, ValueError):
        pass

    for rate in COMMON_INPUT_SAMPLE_RATES:
        if rate not in candidates:
            candidates.append(rate)

    errors: list[str] = []
    for rate in candidates:
        try:
            sd.check_input_settings(
                device=device,
                channels=1,
                dtype="int16",
                samplerate=rate,
            )
            return rate
        except Exception as exc:
            errors.append(f"{rate} Hz: {exc}")

    name = str(info.get("name", device if device is not None else "default"))
    raise RuntimeError(
        f"No supported mono/int16 sample rate found for {name}. "
        + "; ".join(errors[:6])
    )


def input_device_label(device: dict[str, Any], index: int) -> str:
    name = str(device.get("name", f"Device {index}"))
    try:
        rate = int(round(float(device.get("default_samplerate", 0))))
    except (TypeError, ValueError):
        rate = 0
    suffix = f" — {rate} Hz" if rate > 0 else ""
    return f"{index}: {name}{suffix}"
