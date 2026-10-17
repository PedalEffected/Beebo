#!/bin/sh
# Remove Droplets from a Beebo / Hector. Run ON THE PEDAL as the debian user.
# Restores the UI files backed up by the installer (*.orig-droplets).
set -e
LOWER=/media/root-ro/overlay/lower
UI=$LOWER/home/debian/UI

sudo mount -o remount,rw "$LOWER"
sudo rm -rf "$LOWER/usr/lib/lv2/droplets.lv2" "$UI/qml/Droplets.qml"
for f in module_info.py qml/PatchBayEffect.qml; do
    if [ -e "$UI/$f.orig-droplets" ]; then
        sudo mv "$UI/$f.orig-droplets" "$UI/$f"
    fi
done
(cd "$UI" && sudo python3 effect_proto_to_js.py)
sync
echo "Droplets removed. Reboot the pedal. Presets that used Droplets will load without it."
