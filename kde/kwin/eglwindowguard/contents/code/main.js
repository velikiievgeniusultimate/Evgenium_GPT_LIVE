const EGL_CLASS_TOKEN = "evgeniumgpt";

function isEglWindow(window) {
    const windowClass = String(window.windowClass || "").toLowerCase();
    return windowClass.indexOf(EGL_CLASS_TOKEN) !== -1;
}

function guard(window) {
    if (!window || !isEglWindow(window)) {
        return;
    }

    // Keep the service browser usable by EGL while making it disappear from
    // normal Plasma surfaces. The GUI can unminimize it explicitly via CDP.
    window.skipTaskbar = true;
    window.skipPager = true;
    window.skipSwitcher = true;
    if (window.minimizable) {
        window.minimized = true;
    }
}

for (const window of workspace.stackingOrder) {
    guard(window);
}

workspace.windowAdded.connect(guard);
