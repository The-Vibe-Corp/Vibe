#!/usr/bin/env bash
if adb devices | grep -q "emulator-.*device$"; then echo "Emulator läuft bereits"; exit 0; fi
pkill -f qemu-system 2>/dev/null; adb kill-server; adb start-server
nohup emulator -avd medium_tablet -no-window -no-audio -no-boot-anim -gpu swangle_indirect -no-snapshot > /tmp/emu.log 2>&1 &
for i in $(seq 1 120); do
  [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ] && { echo BOOTED; exit 0; }
  sleep 5
done
echo "Emulator-Start fehlgeschlagen, siehe /tmp/emu.log"; exit 1
