#!/bin/bash
# Build Beebo.app for macOS (Apple Silicon or Intel).
#
#   desktop/mac/build_app.sh            full build -> build/mac/Beebo-macOS-<arch>.zip
#   SKIP_PLUGINS=1 desktop/mac/build_app.sh   reuse already-built plugins
#
# Needs Homebrew and the Xcode command line tools. Runs the same on a Mac
# at home or on GitHub's macOS build machines (.github/workflows/mac-app.yml).
#
# What goes into the app (Contents/Resources):
#   ui/        the Beebo screen (this repo), prepared for Qt 6
#   python/    a private Python 3.12 with PySide6 (Qt 6)
#   ingen/     Poly Effects' Ingen engine, with desktop/ingen/JsonWriter.*
#   jack/      the JACK audio server and its CoreAudio driver
#   lv2/       every module that builds (see build/mac/report/plugins-report.md)
#   factory/   start-up graph and the Empty preset
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BUILD="${BUILD:-$ROOT/build/mac}"
APP="$BUILD/Beebo.app"
RES="$APP/Contents/Resources"
DEPS="$BUILD/deps"
REPORT="$BUILD/report"
ARCH="$(uname -m)"
JOBS="$(sysctl -n hw.ncpu)"

INGEN_URL=https://github.com/polyeffects/ingen
INGEN_COMMIT=8dae740425f0f1468198e0cdf1e1c61b3fc6ec5e
RAUL_URL=https://github.com/drobilla/raul
RAUL_COMMIT=26143ba44a5ad9a42dc515ba3a6a192774dfd6ab
PYTHON_VERSION=3.12
PYSIDE_VERSION=6.8.1

step() { echo; echo "=== $*"; echo "=== $*" >> "$REPORT/steps.log"; }
mkdir -p "$BUILD" "$REPORT" "$DEPS"
: > "$REPORT/steps.log"

fetch() {  # fetch <dir> <url> <commit>
  if [ ! -d "$1/.git" ]; then
    rm -rf "$1"; mkdir -p "$1"
    git -C "$1" init -q
    git -C "$1" remote add origin "$2"
    git -C "$1" fetch -q --depth 1 origin "$3"
    git -C "$1" checkout -q FETCH_HEAD
  fi
}

# ------------------------------------------------------------------ tools
step "Homebrew packages"
export HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_CLEANUP=1
brew install meson ninja pkg-config cmake boost lv2 serd sord sratom lilv suil \
  jack libsigc++@2 fftw libsndfile libsamplerate liblo glib uv coreutils || true
BREW="$(brew --prefix)"
export PKG_CONFIG_PATH="$DEPS/lib/pkgconfig:$BREW/lib/pkgconfig:$BREW/opt/libsigc++@2/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
export CPPFLAGS="-I$BREW/include ${CPPFLAGS:-}"
export LDFLAGS="-L$BREW/lib ${LDFLAGS:-}"
export MACOSX_DEPLOYMENT_TARGET=12.0

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$RES" "$APP/Contents/Frameworks"

# ------------------------------------------------------------------ Ingen
step "raul (Ingen's utility library)"
fetch "$BUILD/src/raul" "$RAUL_URL" "$RAUL_COMMIT"
(cd "$BUILD/src/raul" && meson setup build --prefix="$DEPS" -Dtests=disabled --wipe >/dev/null 2>&1 || meson setup build --prefix="$DEPS" -Dtests=disabled)
ninja -C "$BUILD/src/raul/build" install

step "Ingen (Poly Effects fork) with the desktop JSON writer"
fetch "$BUILD/src/ingen" "$INGEN_URL" "$INGEN_COMMIT"
cp "$ROOT/desktop/ingen/JsonWriter.cpp" "$BUILD/src/ingen/src/JsonWriter.cpp"
cp "$ROOT/desktop/ingen/JsonWriter.hpp" "$BUILD/src/ingen/include/ingen/JsonWriter.hpp"
rm -rf "$BUILD/src/ingen/build"
(cd "$BUILD/src/ingen" && meson setup build --prefix="$RES/ingen" --libdir=lib --buildtype=release \
   -Dgui=disabled -Ddocs=disabled -Dbindings_py=disabled -Djack=enabled -Dportaudio=disabled \
   -Dlv2dir="$RES/lv2")
ninja -C "$BUILD/src/ingen/build" -j "$JOBS" install
rm -rf "$RES/ingen/include" "$RES/ingen/share/man"

# ------------------------------------------------------------------ JACK
step "JACK"
JACK="$(brew --prefix jack)"
mkdir -p "$RES/jack/bin" "$RES/jack/lib/jack"
cp "$JACK/bin/jackd" "$RES/jack/bin/"
# Homebrew's JACK doesn't include jack_lsp / jack_connect any more: build ours
cc -O2 -o "$RES/jack/bin/jack_lsp" "$ROOT/desktop/jack_tools.c" $(pkg-config --cflags --libs jack)
cp "$RES/jack/bin/jack_lsp" "$RES/jack/bin/jack_connect"
cp "$RES/jack/bin/jack_lsp" "$RES/jack/bin/jack_disconnect"
cp "$JACK"/lib/jack/*.so "$RES/jack/lib/jack/" 2>/dev/null || true
ls "$JACK/lib/jack" | tee "$REPORT/jack-drivers.txt"
chmod -R u+w "$RES/jack"

# ------------------------------------------------------------------ modules
step "LV2 modules"
if [ -z "${SKIP_PLUGINS:-}" ] || [ ! -d "$BUILD/lv2" ]; then
  python3 "$ROOT/desktop/build_plugins.py" --out "$BUILD/lv2" --work "$BUILD/plugins" \
    --report-dir "$REPORT" || true
fi
mkdir -p "$RES/lv2"
cp -R "$BUILD/lv2/." "$RES/lv2/"

# ------------------------------------------------------------------ Python + Qt
step "Python $PYTHON_VERSION and PySide6 $PYSIDE_VERSION"
# a relocatable Python build (python-build-standalone), via uv
uv python install "$PYTHON_VERSION"
PYEXE="$(uv python find --python-preference only-managed "$PYTHON_VERSION")"
PYHOME="$(cd "$(dirname "$PYEXE")/.." && pwd -P)"
cp -R "$PYHOME" "$RES/python"
rm -f "$RES"/python/lib/python3*/EXTERNALLY-MANAGED
PY="$RES/python/bin/python3"
"$PY" -m pip install --no-warn-script-location -q --upgrade pip || true
"$PY" -m pip install --no-warn-script-location -q "PySide6-Essentials==$PYSIDE_VERSION" pyliblo3 pyserial pillow
# Qt parts the Beebo screen doesn't use
SP="$("$PY" -c 'import site; print(site.getsitepackages()[0])')"
rm -rf "$SP/PySide6/Qt/lib/QtWebEngine"* "$SP/PySide6/Qt/lib/QtDesigner"* "$SP/PySide6/Designer.app" \
       "$SP/PySide6/Assistant.app" "$SP/PySide6/Linguist.app" "$SP/PySide6/include" 2>/dev/null || true

# ------------------------------------------------------------------ the screen
step "Beebo screen"
mkdir -p "$RES/ui"
(cd "$ROOT" && tar cf - --exclude ./build --exclude ./.git --exclude ./droplets/third_party \
   --exclude '*/prebuilt-arm64' --exclude ./dist --exclude '__pycache__' .) | (cd "$RES/ui" && tar xf -)
"$PY" "$RES/ui/desktop/prepare_ui.py" "$RES/ui" --qt6
mkdir -p "$RES/factory"
cp -R "$ROOT/desktop/factory/." "$RES/factory/"

# ------------------------------------------------------------------ app bundle
step "App bundle"
cat > "$APP/Contents/MacOS/Beebo" <<'EOF'
#!/bin/sh
RES="$(cd "$(dirname "$0")/../Resources" && pwd)"
export BEEBO_RESOURCES="$RES"
exec "$RES/python/bin/python3" "$RES/ui/desktop/beebo_launcher.py" "$@"
EOF
chmod +x "$APP/Contents/MacOS/Beebo"
VERSION="$(git -C "$ROOT" describe --always --dirty 2>/dev/null || echo dev)"
cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Beebo</string>
  <key>CFBundleDisplayName</key><string>Beebo</string>
  <key>CFBundleIdentifier</key><string>com.github.pedaleffected.beebo</string>
  <key>CFBundleExecutable</key><string>Beebo</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.1</string>
  <key>CFBundleVersion</key><string>$VERSION</string>
  <key>CFBundleIconFile</key><string>Beebo</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSMicrophoneUsageDescription</key><string>Beebo processes the audio coming into your audio interface.</string>
</dict></plist>
EOF
"$PY" "$ROOT/desktop/mac/make_icon.py" "$RES/Beebo.icns" || true

step "Bundle libraries and sign"
python3 "$ROOT/desktop/mac/bundle_dylibs.py" "$APP" | tee "$REPORT/bundle.log"

# ------------------------------------------------------------------ checks
step "Check: Ingen loads the modules"
export LV2_PATH="$RES/lv2" INGEN_MODULE_PATH="$RES/ingen/lib" JACK_DRIVER_DIR="$RES/jack/lib/jack"
export BEEBO_DATA_DIR="$BUILD/check-data"
rm -rf "$BEEBO_DATA_DIR"
"$RES/jack/bin/jackd" -d dummy -r 48000 -p 256 > "$REPORT/check-jackd.log" 2>&1 &
JACKPID=$!
sleep 3
SOCK="/tmp/beebo-check-$$.sock"
# the test runs its own Ingen and restarts it if a module crashes it
BEEBO_DESKTOP=1 "$PY" "$RES/ui/desktop/test_modules.py" "$SOCK" \
  --start "$RES/ingen/bin/ingen" "$RES/factory/start_up.ingen" --log "$REPORT/check-ingen.log" \
  | tee "$REPORT/modules-loaded.txt" || true
mkdir -p "$REPORT/crashes"
cp ~/Library/Logs/DiagnosticReports/ingen* "$REPORT/crashes/" 2>/dev/null || true

# a fresh Ingen for the screen check
"$RES/ingen/bin/ingen" -e -p 2 -S "$SOCK" "$RES/factory/start_up.ingen" >> "$REPORT/check-ingen.log" 2>&1 &
INGENPID=$!
for i in $(seq 1 100); do [ -S "$SOCK" ] && break; sleep 0.2; done

step "Check: the Beebo screen starts"
BEEBO_DESKTOP=1 BEEBO_INGEN_SOCKET="$SOCK" BEEBO_SCREENSHOT="$REPORT/screen.png" BEEBO_SCREENSHOT_AFTER=20000 \
  QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}" \
  "$PY" "$RES/ui/beebo_desktop_ui.py" > "$REPORT/check-ui.log" 2>&1 &
UIPID=$!
for i in $(seq 1 120); do kill -0 $UIPID 2>/dev/null || break; sleep 1; done
kill -9 $UIPID 2>/dev/null || true
kill $INGENPID $JACKPID 2>/dev/null || true
cp ~/Library/Logs/DiagnosticReports/{ingen,python3}* "$REPORT/crashes/" 2>/dev/null || true

step "Package"
cd "$BUILD"
ZIP="Beebo-macOS-$ARCH.zip"
rm -f "$ZIP"
ditto -c -k --sequesterRsrc --keepParent Beebo.app "$ZIP"
du -sh Beebo.app "$ZIP" | tee -a "$REPORT/steps.log"
echo "done: $BUILD/$ZIP"

# reports, also in the log so they can be read without downloading
step "Reports"
for f in plugins-report.md modules-loaded.txt jack-drivers.txt; do
  echo "----- $f"; cat "$REPORT/$f" 2>/dev/null || true
done
echo "----- check-ingen.log (end)"; tail -40 "$REPORT/check-ingen.log" 2>/dev/null || true
echo "----- check-ui.log (end)"; tail -60 "$REPORT/check-ui.log" 2>/dev/null || true
for c in "$REPORT"/crashes/*; do
  [ -f "$c" ] || continue
  echo "----- crash: $(basename "$c")"
  "$PY" - "$c" <<'PYEOF' || head -c 4000 "$c"
import json, sys
text = open(sys.argv[1]).read()
head, _, body = text.partition("\n")
r = json.loads(body)
print(r.get("exception"), r.get("termination", {}).get("indicator", ""))
imgs = r.get("usedImages", [])
for t in r.get("threads", []):
    if t.get("triggered"):
        for fr in t.get("frames", [])[:25]:
            img = imgs[fr.get("imageIndex", 0)].get("name", "?") if imgs else "?"
            print("  %-34s %s" % (img, fr.get("symbol", hex(fr.get("imageOffset", 0)))))
PYEOF
done
