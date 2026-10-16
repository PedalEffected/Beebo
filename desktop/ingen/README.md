# Ingen changes for the desktop build

The Beebo screen talks to Ingen (Poly Effects' fork, polyeffects/ingen) over a
socket, and expects Ingen's replies as JSON. On the pedal that JSON comes from
a change to the serd library that Poly Effects hasn't published, so Poly's
Ingen doesn't build against the serd you can install today.

These two files replace `src/JsonWriter.cpp` and
`include/ingen/JsonWriter.hpp` in polyeffects/ingen (commit 8dae740). They
produce the same JSON straight from Ingen's messages, with stock serd. The
desktop build copies them over the Ingen source before building.

Same license as Ingen (AGPL-3.0-or-later).
