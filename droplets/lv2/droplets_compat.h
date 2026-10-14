// Force-included before the Beads/stmlib engine sources.
// - stmlib's portable (non Cortex-M) code paths are selected by TEST.
// - Beads prints debug messages from the audio path in TEST builds; on a
//   pedal those must not run, so printf becomes a no-op here.
#ifndef DROPLETS_COMPAT_H_
#define DROPLETS_COMPAT_H_
#include <cstdio>
#ifndef TEST
#define TEST
#endif
static inline int droplets_silent_printf(const char*, ...) { return 0; }
#define printf droplets_silent_printf
#endif
