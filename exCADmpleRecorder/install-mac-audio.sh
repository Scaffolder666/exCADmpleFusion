#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
xcode-select -p >/dev/null || {
    echo "Run xcode-select --install first. When the installation finishes, rerun this script."
    exit 1
}
app="exCADmple Microphone.app"
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT
bundle="$build/$app"
mkdir -p "$bundle/Contents/MacOS"
cat > "$bundle/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
    <key>CFBundleIdentifier</key><string>org.excadmple.recorder.microphone</string>
    <key>CFBundleExecutable</key><string>excadmple-microphone</string>
    <key>CFBundleName</key><string>exCADmple Microphone</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleVersion</key><string>1</string>
    <key>CFBundleShortVersionString</key><string>1.0</string>
    <key>LSUIElement</key><true/>
    <key>NSMicrophoneUsageDescription</key><string>Record voice messages for design steps in Autodesk Fusion.</string>
</dict></plist>
PLIST
xcrun swiftc -target "$(uname -m)-apple-macosx11.0" -swift-version 5 -O -framework AVFoundation mac_audio.swift -o "$bundle/Contents/MacOS/excadmple-microphone"
codesign --force --sign - "$bundle"
ditto "$bundle" "$app"
codesign --verify "$app"
echo "exCADmple Microphone is installed. Return to Fusion and run the recorder add-in."
