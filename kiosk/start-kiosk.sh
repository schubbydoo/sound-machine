#!/bin/bash
# Memory Spark Station — Kiosk display startup
# Runs inside xinit on :0 vt1

# Silence the X bell immediately
xset b off
xset b 0 0 0

# Disable screen blanking / DPMS power-off
xset s off
xset s noblank
xset -dpms

# Hide cursor after 1 second of inactivity
if command -v unclutter &>/dev/null; then
    unclutter -idle 0 -root &
fi

# Start a minimal window manager so surf gets proper focus + fullscreen
openbox &
sleep 1

# Wait for the kiosk server (max 30 s)
for i in $(seq 1 30); do
    curl -sf http://localhost:8081/ >/dev/null 2>&1 && break
    sleep 1
done

# Launch surf — webkit-based, much lighter than Chromium on 416 MB
# surf flags: -b = no scrollbars, -d = no disk cache
exec surf -b -d http://localhost:8081
