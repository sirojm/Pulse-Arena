# PULSE ARENA v3.0.1 — v3 Patch 1

**Base**: PULSE ARENA v3.0. All previously requested v3.1 changes have been intentionally excluded.

## Fixed/added
- BLACKOUT: master-video opacity 0 with previous-level restore; long press to arm.
- Quick FX editor: label, address, color, ON/OFF value, Toggle/Momentary/Pulse.
- Quick FX toggle-off: second tap sends OFF and updates button state.
- BPM: OSC Output feedback port 7700, server-sent event push to clients, REST fallback.
- Color: editable HEX field and copy-to-clipboard button.
- Clip glow: reflects REST `connected` and/or OSC Output state; persists beyond finger release while clip is active.

## Known constraints
- No direct Resolume rig was available for physical integration tests.
- OSC commands can be sent without actual execution; monitor in Resolume and enable REST plus OSC Output.
- Default dashboard macro address requires a dashboard mapping in Resolume.
- OSC Output feedback port change requires restarting the bridge.
- Android APK is not included; compatible Android WebView project source remains bundled.
