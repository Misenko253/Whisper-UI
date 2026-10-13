"""Thin wrappers over the macOS APIs the app needs. Call them on the main thread."""

import subprocess

import AVFoundation
from AppKit import NSApplication, NSModalResponseOK, NSOpenPanel

MIC_SETTINGS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"


def mic_status() -> str:
    """'authorized', 'undetermined' or 'denied'. A denied mic doesn't error, it records silence."""
    status = AVFoundation.AVCaptureDevice.authorizationStatusForMediaType_(AVFoundation.AVMediaTypeAudio)
    if status == AVFoundation.AVAuthorizationStatusAuthorized:
        return "authorized"
    if status == AVFoundation.AVAuthorizationStatusNotDetermined:
        return "undetermined"
    return "denied"


def request_mic(callback) -> None:
    """Show the macOS mic prompt. callback(granted: bool) runs on a background thread."""
    AVFoundation.AVCaptureDevice.requestAccessForMediaType_completionHandler_(
        AVFoundation.AVMediaTypeAudio, callback
    )


def open_path(path_or_url: str) -> None:
    subprocess.Popen(["/usr/bin/open", path_or_url])


def open_mic_settings() -> None:
    open_path(MIC_SETTINGS_URL)


def choose_audio_file() -> str | None:
    app = NSApplication.sharedApplication()
    app.activateIgnoringOtherApps_(True)  # accessory apps must activate or the panel opens behind
    panel = NSOpenPanel.openPanel()
    panel.setTitle_("Transcribe file")
    panel.setCanChooseFiles_(True)
    panel.setCanChooseDirectories_(False)
    panel.setAllowsMultipleSelection_(False)
    panel.setAllowedFileTypes_(["public.audio", "public.movie"])
    if panel.runModal() != NSModalResponseOK:
        return None
    return panel.URLs()[0].path()

