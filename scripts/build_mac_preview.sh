#!/bin/bash
# Build an actual LaunchServices application bundle for the Mac clip player.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUNDLE="$ROOT/native/ScenepackiePreview.app"
BIN="$BUNDLE/Contents/MacOS/ScenepackiePreview"
mkdir -p "$BUNDLE/Contents/MacOS" "$BUNDLE/Contents/Resources"

cat > "$BUNDLE/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleIdentifier</key>
    <string>app.scenepackie.preview</string>
    <key>CFBundleName</key>
    <string>Scenepackie Preview</string>
    <key>CFBundleDisplayName</key>
    <string>Scenepackie Preview</string>
    <key>CFBundleExecutable</key>
    <string>ScenepackiePreview</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>0.4</string>
    <key>CFBundleVersion</key>
    <string>4</string>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSPrincipalClass</key>
    <string>NSApplication</string>
</dict>
</plist>
PLIST

swiftc "$ROOT/native/mac_preview.swift" -o "$BIN"
chmod +x "$BIN"
plutil -lint "$BUNDLE/Contents/Info.plist"
codesign --force --sign - "$BUNDLE"
codesign --verify --verbose=2 "$BUNDLE"
test -x "$BIN"
echo "Native Mac Preview.app compiled and signed."
