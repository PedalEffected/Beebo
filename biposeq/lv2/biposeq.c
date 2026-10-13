/*
  BiPoSeq - bipolar 16-step sequencer for Poly Effects Beebo / Hector.

  Two LV2 plugins in one bundle, derived from Poly Effects' poly_step and
  poly_step_bpm (PolyLV2):

    https://github.com/PedalEffected/Beebo#BiPoSeq      (internal BPM clock)
    https://github.com/PedalEffected/Beebo#BiPoSeq_ext  (external triggers)

  Each step value is stored in volts, -5.0 .. +5.0, so a value typed on the
  pedal's keypad is the voltage you get. The output is scaled to Beebo's
  CV range, where 1.0 is +5 V on a Hector jack:

      step -5.0 V -> -1.0
      step  0.0 V ->  0.0
      step +5.0 V -> +1.0

  Copyright 2026 Gary Kane (BiPoSeq)
  Copyright 2020 Loki Davison
  Copyright 2011 David Robillard
  Copyright 2002 Mike Rawes

  This is free software: you can redistribute it and/or modify it
  under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.

  This software is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.
*/

#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>

/* Support both the old and new LV2 header layouts. */
#if defined(__has_include)
#  if __has_include("lv2/core/lv2.h")
#    include "lv2/core/lv2.h"
#  else
#    include "lv2/lv2plug.in/ns/lv2core/lv2.h"
#  endif
#else
#  include "lv2/lv2plug.in/ns/lv2core/lv2.h"
#endif

/* Prebuilt ARM64 binaries link the oldest expf so they load on older
   Debian images (glibc >= 2.17). Enable with -DLEGACY_GLIBC. */
#if defined(LEGACY_GLIBC) && defined(__aarch64__)
__asm__(".symver expf,expf@GLIBC_2.17");
#endif

#define BIPOSEQ_URI "https://github.com/PedalEffected/Beebo"

#define NUM_STEPS 16

/* Port indices, identical to Poly's sequencers so the same screen drives them. */
#define P_BACK      0   /* ext: back trigger   | bpm: back gate */
#define P_FWD       1   /* ext: step trigger   | bpm: play      */
#define P_STEPS     2
#define P_RESET     3
#define P_GLIDE     4
#define P_VAL0      5
#define P_OUT       (NUM_STEPS + 5)   /* 21 */
#define P_CUR_STEP  (NUM_STEPS + 6)   /* 22 */
#define P_BPM       (NUM_STEPS + 7)   /* 23, bpm variant only */
#define P_NOTE_LEN  (NUM_STEPS + 8)   /* 24, bpm variant only */

#define TRIG_HIGH 0.4f    /* about 2 V on Hector    */
#define TRIG_LOW  0.08f   /* about 0.4 V on Hector  */

typedef struct {
	const float* back;
	const float* fwd;
	const float* steps;
	const float* reset;
	const float* glide;
	const float* bpm;
	const float* note_length;
	const float* values[NUM_STEPS];
	float*       out;
	float*       cur_step_out;

	float    inv_srate;
	float    srate;
	float    last_value;
	unsigned step_index;
	bool     prev_fwd;
	bool     prev_back;
	int      samples_elapsed;
} Seq;

#define VOLT_RANGE 5.0f   /* steps are -5..+5 V; 1.0 CV = 5 V on Hector */

/* Step value in volts (-5..+5) -> CV (-1..+1), clamped. */
static inline float
volts_to_cv(float v)
{
	if (v < -VOLT_RANGE) v = -VOLT_RANGE;
	if (v >  VOLT_RANGE) v =  VOLT_RANGE;
	return v / VOLT_RANGE;
}

static inline float
clampf(float x, float lo, float hi)
{
	return x < lo ? lo : (x > hi ? hi : x);
}

static LV2_Handle
instantiate(const LV2_Descriptor* d, double rate, const char* path,
            const LV2_Feature* const* features)
{
	(void)d; (void)path; (void)features;
	Seq* s = (Seq*)calloc(1, sizeof(Seq));
	if (!s) {
		return NULL;
	}
	s->srate     = (float)rate;
	s->inv_srate = 1.0f / s->srate;
	return (LV2_Handle)s;
}

static void
connect_port(LV2_Handle h, uint32_t port, void* data)
{
	Seq* s = (Seq*)h;
	switch (port) {
	case P_BACK:     s->back         = (const float*)data; break;
	case P_FWD:      s->fwd          = (const float*)data; break;
	case P_STEPS:    s->steps        = (const float*)data; break;
	case P_RESET:    s->reset        = (const float*)data; break;
	case P_GLIDE:    s->glide        = (const float*)data; break;
	case P_OUT:      s->out          = (float*)data;       break;
	case P_CUR_STEP: s->cur_step_out = (float*)data;       break;
	case P_BPM:      s->bpm          = (const float*)data; break;
	case P_NOTE_LEN: s->note_length  = (const float*)data; break;
	default:
		if (port >= P_VAL0 && port < P_OUT) {
			s->values[port - P_VAL0] = (const float*)data;
		}
		break;
	}
}

static void
activate(LV2_Handle h)
{
	Seq* s = (Seq*)h;
	s->last_value      = 0.0f;   /* start at 0 V */
	s->step_index      = 0;
	s->prev_fwd        = false;
	s->prev_back       = false;
	s->samples_elapsed = 0;
}

static unsigned
loop_length(const Seq* s)
{
	long n = lrintf(*s->steps);
	if (n < 1) n = 1;
	if (n > NUM_STEPS) n = NUM_STEPS;
	return (unsigned)n;
}

/* One-pole glide, same coefficient as the original modules. */
static inline float
glide_coeff(const Seq* s)
{
	const float g = *s->glide;
	return g > 0.0f ? expf(-s->inv_srate / g) : 0.0f;
}

/* ---- External-trigger variant ------------------------------------- */

static void
run_ext(LV2_Handle h, uint32_t n)
{
	Seq* s = (Seq*)h;
	const unsigned loop = loop_length(s);
	const float a = glide_coeff(s);
	const float b = 1.0f - a;

	float v[NUM_STEPS];
	for (int i = 0; i < NUM_STEPS; ++i) {
		v[i] = volts_to_cv(*s->values[i]);
	}

	unsigned idx  = s->step_index % loop;
	bool pf       = s->prev_fwd;
	bool pb       = s->prev_back;
	float y       = s->last_value;

	for (uint32_t i = 0; i < n; ++i) {
		if (s->reset[i] > TRIG_HIGH) {
			idx = 0;
		} else {
			if (s->fwd[i] > TRIG_HIGH && !pf) {
				pf = true;
				if (++idx >= loop) idx = 0;
			} else if (s->fwd[i] <= TRIG_LOW) {
				pf = false;
			}

			if (s->back[i] > TRIG_HIGH && !pb) {
				pb = true;
				idx = (idx == 0) ? loop - 1 : idx - 1;
			} else if (s->back[i] <= TRIG_LOW) {
				pb = false;
			}
		}
		y = a * y + b * v[idx];
		s->out[i] = y;
	}

	s->step_index = idx;
	s->prev_fwd   = pf;
	s->prev_back  = pb;
	s->last_value = y;
	if (s->cur_step_out) *s->cur_step_out = (float)idx;
}

/* ---- Internal-clock (BPM) variant --------------------------------- */

static void
run_bpm(LV2_Handle h, uint32_t n)
{
	Seq* s = (Seq*)h;
	const unsigned loop = loop_length(s);
	const float a = glide_coeff(s);
	const float b = 1.0f - a;

	const float note_length = clampf(*s->note_length, 0.03125f, 1.0f);
	const float bpm         = clampf(*s->bpm, 10.0f, 320.0f);
	const int samples_per_step =
		(int)(((60.0f / bpm) * s->srate) / (0.25f / note_length));

	float v[NUM_STEPS];
	for (int i = 0; i < NUM_STEPS; ++i) {
		v[i] = volts_to_cv(*s->values[i]);
	}

	unsigned idx = s->step_index % loop;
	int elapsed  = s->samples_elapsed;
	float y      = s->last_value;

	for (uint32_t i = 0; i < n; ++i) {
		++elapsed;
		if (s->reset[i] >= TRIG_HIGH) {
			idx = 0;
			elapsed = 0;
		} else if ((s->fwd[i] >= TRIG_HIGH || s->back[i] >= TRIG_HIGH)
		           && elapsed > samples_per_step) {
			if (s->fwd[i] >= TRIG_HIGH) {
				if (++idx >= loop) idx = 0;
			}
			if (s->back[i] >= TRIG_HIGH) {
				idx = (idx == 0) ? loop - 1 : idx - 1;
			}
			elapsed = 0;
		}
		y = a * y + b * v[idx];
		s->out[i] = y;
	}

	s->step_index      = idx;
	s->samples_elapsed = elapsed;
	s->last_value      = y;
	if (s->cur_step_out) *s->cur_step_out = (float)idx;
}

static void
cleanup(LV2_Handle h)
{
	free(h);
}

static const LV2_Descriptor desc_ext = {
	BIPOSEQ_URI "#BiPoSeq_ext",
	instantiate, connect_port, activate, run_ext, NULL, cleanup, NULL
};

static const LV2_Descriptor desc_bpm = {
	BIPOSEQ_URI "#BiPoSeq",
	instantiate, connect_port, activate, run_bpm, NULL, cleanup, NULL
};

LV2_SYMBOL_EXPORT const LV2_Descriptor*
lv2_descriptor(uint32_t index)
{
	switch (index) {
	case 0:  return &desc_bpm;
	case 1:  return &desc_ext;
	default: return NULL;
	}
}
