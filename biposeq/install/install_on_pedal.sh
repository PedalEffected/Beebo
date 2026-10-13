#!/bin/sh
# Install BiPoSeq on a Beebo / Hector. Run ON THE PEDAL as the debian user,
# from inside the biposeq folder:
#
#     sh install/install_on_pedal.sh            # install
#     sh install/install_on_pedal.sh --check    # dry run: show what would change
#
# Uses the method from Poly Effects' add-module.md: the pedal's real files live
# on a read-only "lower" layer, so we remount it read-write, copy, and sync.
set -e
cd "$(dirname "$0")/.."

LOWER=/media/root-ro/overlay/lower
UI=/home/debian/UI
LV2=/usr/lib/lv2

for p in "$LOWER$UI/module_info.py" "$LOWER$LV2" prebuilt-arm64/biposeq.lv2/biposeq.so ui/BiPoSeq.qml; do
    if [ ! -e "$p" ]; then
        echo "ERROR: $p not found. Nothing was changed."
        exit 1
    fi
done

if [ "$1" = "--check" ]; then
    python3 install/biposeq_ui.py "$LOWER$UI" --check
    echo "  would copy prebuilt-arm64/biposeq.lv2 -> $LOWER$LV2/"
    exit 0
fi

echo "Making the pedal's system layer writable..."
sudo mount -o remount,rw "$LOWER"

echo "Installing the BiPoSeq plugin..."
sudo rm -rf "$LOWER$LV2/biposeq.lv2"
sudo cp -r prebuilt-arm64/biposeq.lv2 "$LOWER$LV2/"

echo "Adding BiPoSeq to the UI..."
sudo python3 install/biposeq_ui.py "$LOWER$UI"
(cd "$LOWER$UI" && sudo python3 effect_proto_to_js.py)

sync
echo
echo "Done. Reboot the pedal, then look for BiPoSeq under 'cv generators'."
