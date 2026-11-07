#!/usr/bin/env bash
adb emu kill 2>/dev/null; pkill -f qemu-system 2>/dev/null; exit 0
