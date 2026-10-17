// Droplets - an LV2 port of the Beads granular texture processor for
// Poly Effects Beebo / Hector.
//
// The sound engine (beads/dsp, stmlib) is Emilie Gillet's open-source
// Mutable Instruments code, MIT license, used unmodified. This file only
// replaces the hardware layer: panel, CV inputs, gates and the codec.
//
// Copyright 2026 Gary Kane (Droplets LV2 wrapper)
// Engine: Copyright Emilie Gillet (MIT license, see third_party/LICENSE-beads)
//
// Permission is hereby granted, free of charge, to any person obtaining a
// copy of this software and associated documentation files (the "Software"),
// to deal in the Software without restriction, including without limitation
// the rights to use, copy, modify, merge, publish, distribute, sublicense,
// and/or sell copies of the Software, and to permit persons to whom the
// Software is furnished to do so, subject to the following conditions:
// The above copyright notice and this permission notice shall be included in
// all copies or substantial portions of the Software.
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <new>

#if defined(__has_include)
#  if __has_include("lv2/core/lv2.h")
#    include "lv2/core/lv2.h"
#  else
#    include "lv2/lv2plug.in/ns/lv2core/lv2.h"
#  endif
#else
#  include "lv2/lv2plug.in/ns/lv2core/lv2.h"
#endif

#include "stmlib/dsp/dsp.h"
#include "stmlib/utils/gate_flags.h"
#include "beads/dsp/processor.h"
#include "beads/dsp/synth.h"

#define DROPLETS_URI "https://github.com/PedalEffected/Beebo#Droplets"

using namespace beads;
using namespace stmlib;

namespace {

// ---------------------------------------------------------------- ports
enum Port {
  P_IN_L = 0, P_IN_R, P_OUT_L, P_OUT_R,
  // gates (CV, high above 0.4 = about 2 V on Hector)
  P_SEED_GATE, P_FREEZE_GATE,
  // CV inputs, Hector scale: 1.0 = 5 V
  P_TIME_CV, P_SIZE_CV, P_SHAPE_CV, P_PITCH_CV, P_DENSITY_CV,
  P_FEEDBACK_CV, P_DRY_WET_CV, P_REVERB_CV,
  // panel
  P_TIME, P_SIZE, P_SHAPE, P_DENSITY, P_PITCH,
  P_TIME_AMT, P_SIZE_AMT, P_SHAPE_AMT, P_PITCH_AMT,
  P_FEEDBACK, P_DRY_WET, P_REVERB,
  P_FREEZE, P_SEED_BUTTON, P_SEED_LOCK,
  P_QUALITY, P_MONO, P_INPUT_GAIN, P_SYNTH, P_GATE_OUT,
  P_LAST
};

const float kGateHigh = 0.4f;            // ~2 V
const float kCvDetectThreshold = 0.002f; // ~10 mV
const float kCvDetectHold = 1.0f;        // seconds without signal = unpatched
const float kSeedDetectHold = 5.0f;      // seconds without a clock = unpatched
const int kEngineBlockRate = 2000;       // as on the module: 24 frames @ 48 kHz
const size_t kMaxBlock = 24;

// ------------------------------------------------- input gain + soft clip
// Float version of beads/gain_control.cc (automatic gain when the GAIN
// setting is 0, manual gain with media-dependent soft clipping otherwise).
class InputGain {
 public:
  enum Mode { CLIP_OFF, CLIP_ON, CLIP_DYNAMIC };

  void Init(float sr, Mode mode, bool reset) {
    if (reset) {
      stable_agc_peak_ = agc_peak_ = peak_ = 0.5f;
      gain_ = 1.0f;
      soft_clipping_amount_ = 0.0f;
      manual_gain_ = 1.0f;
      time_ = 0;
    }
    mode_ = mode;
    ignore_time_ = size_t(sr * 1.0f);
    active_time_ = size_t(sr * 6.0f);
    one_hertz_ = 1.0f / sr;
  }

  void Process(float setting, const FloatFrame* in, FloatFrame* out,
               size_t size) {
    const float hz = float(size) * one_hertz_;
    if (time_ < ignore_time_) {
      agc_peak_ = 0.5f;
    } else if (time_ < active_time_) {
      SLOPE(agc_peak_, peak_, 10.0f * hz, 2.0f * hz);
      stable_agc_peak_ = agc_peak_;
    } else {
      SLOPE(agc_peak_, peak_, 5.0f * hz,
            (peak_ > stable_agc_peak_ ? 0.5f : 0.01f) * hz);
    }
    if (time_ > ignore_time_ || peak_ > 0.001f) time_ += size;
    if (time_ >= active_time_) time_ = active_time_;

    const bool auto_gain = setting <= 0.0f;
    float manual = setting * setting;
    manual *= manual;
    manual = 1.0f + 39.0f * manual;
    ONE_POLE(manual_gain_, manual, 0.01f);
    const float optimal = std::min(0.9f / std::min(agc_peak_, 0.9f), 40.0f);
    const float target_gain = auto_gain ? optimal : manual_gain_;

    float clip;
    if (mode_ == CLIP_OFF) clip = 0.0f;
    else if (mode_ == CLIP_ON) clip = 1.0f;
    else { clip = 2.0f * (manual_gain_ / optimal - 0.75f); CONSTRAIN(clip, 0.0f, 1.0f); }

    const float g_step = (target_gain - gain_) / float(size);
    const float c_step = (clip - soft_clipping_amount_) / float(size);
    for (size_t i = 0; i < size; ++i) {
      float l = in[i].l, r = in[i].r;
      const float peak = std::max(fabsf(l), fabsf(r));
      SLOPE(peak_, peak, 0.1f, 2.0f * one_hertz_);
      gain_ += g_step;
      soft_clipping_amount_ += c_step;
      l *= gain_;
      r *= gain_;
      if (!auto_gain) {
        if (mode_ == CLIP_OFF) {
          CONSTRAIN(l, -1.0f, 1.0f); CONSTRAIN(r, -1.0f, 1.0f);
        } else {
          const float bias = 0.05f;
          const float sl = (1.0f - bias) * SoftClip(l + bias) - bias;
          const float sr = (1.0f - bias) * SoftClip(r + bias) - bias;
          CONSTRAIN(l, -1.0f, 1.0f); CONSTRAIN(r, -1.0f, 1.0f);
          l = Crossfade(l, sl, soft_clipping_amount_);
          r = Crossfade(r, sr, soft_clipping_amount_);
        }
      }
      out[i].l = l;
      out[i].r = r;
    }
  }

 private:
  float peak_, agc_peak_, stable_agc_peak_, gain_, soft_clipping_amount_;
  float manual_gain_, one_hertz_;
  Mode mode_;
  size_t time_, ignore_time_, active_time_;
};

// ------------------------------------------------------- resampling
// The module changes its codec rate with the quality setting (24, 32 or
// 48 kHz). The pedal runs at one fixed rate, so we resample around the
// engine: 4th-order low-pass + cubic interpolation.
struct Biquad {
  float b0, b1, b2, a1, a2, z1, z2;
  void LowPass(float fc_over_fs, float q) {
    const float w = 2.0f * float(M_PI) * fc_over_fs;
    const float alpha = sinf(w) / (2.0f * q), c = cosf(w);
    const float a0 = 1.0f + alpha;
    b0 = (1.0f - c) * 0.5f / a0; b1 = (1.0f - c) / a0; b2 = b0;
    a1 = -2.0f * c / a0; a2 = (1.0f - alpha) / a0;
    z1 = z2 = 0.0f;
  }
  inline float Process(float x) {
    const float y = b0 * x + z1;
    z1 = b1 * x - a1 * y + z2;
    z2 = b2 * x - a2 * y;
    return y;
  }
};

struct LowPass4 {
  Biquad s[2][2];  // [channel][stage]
  bool active;
  void Init(float fc_over_fs) {
    active = fc_over_fs < 0.49f;
    for (int c = 0; c < 2; ++c) {
      s[c][0].LowPass(std::min(fc_over_fs, 0.49f), 0.5412f);
      s[c][1].LowPass(std::min(fc_over_fs, 0.49f), 1.3066f);
    }
  }
  inline void Process(float* l, float* r) {
    if (!active) return;
    *l = s[0][1].Process(s[0][0].Process(*l));
    *r = s[1][1].Process(s[1][0].Process(*r));
  }
};

// Frame carried across the rate change: audio plus the two gates.
struct Slot { float l, r; bool seed, freeze; };

class Resampler {
 public:
  void Init(float from, float to) {
    step_ = from / to;
    phase_ = 0.0f;
    for (int i = 0; i < 4; ++i) hist_[i] = Slot{0, 0, false, false};
  }
  // Push one input slot; call Emit() until it returns false.
  inline void Push(const Slot& s) {
    hist_[0] = hist_[1]; hist_[1] = hist_[2]; hist_[2] = hist_[3]; hist_[3] = s;
    phase_ -= 1.0f;
  }
  inline bool Emit(Slot* out) {
    if (phase_ >= 0.0f) return false;
    const float t = phase_ + 1.0f;  // position between hist_[1] and hist_[2]
    out->l = Cubic(hist_[0].l, hist_[1].l, hist_[2].l, hist_[3].l, t);
    out->r = Cubic(hist_[0].r, hist_[1].r, hist_[2].r, hist_[3].r, t);
    out->seed = hist_[2].seed;
    out->freeze = hist_[2].freeze;
    phase_ += step_;
    return true;
  }
 private:
  static inline float Cubic(float xm1, float x0, float x1, float x2, float t) {
    const float c = (x1 - xm1) * 0.5f;
    const float v = x0 - x1;
    const float w = c + v;
    const float a = w + v + (x2 - x0) * 0.5f;
    const float b = w + a;
    return (((a * t) - b) * t + c) * t + x0;
  }
  Slot hist_[4];
  float step_, phase_;
};

// Simple FIFO of slots.
template<size_t N>
struct SlotFifo {
  Slot data[N];
  size_t r = 0, w = 0, n = 0;
  void Clear() { r = w = n = 0; }
  inline bool Push(const Slot& s) {
    if (n == N) return false;
    data[w] = s; w = (w + 1) % N; ++n; return true;
  }
  inline bool Pop(Slot* s) {
    if (!n) return false;
    *s = data[r]; r = (r + 1) % N; --n; return true;
  }
};

// Remembers whether a CV input has carried any signal recently. The module
// does this with jack-switch normalization; LV2 can't see cables.
struct PatchDetector {
  float silent_time;
  float hold;
  void Init(float h) { hold = h; silent_time = h; }
  inline bool Process(bool active, float dt) {
    silent_time = active ? 0.0f : std::min(silent_time + dt, hold);
    return silent_time < hold;
  }
};

// ---------------------------------------------------------------- plugin
struct Droplets {
  const float* port[P_LAST];

  Processor* processor;
  Synth* synth;
  uint8_t* delay_memory;      // 768 KB, as on the module
  uint16_t* reverb_memory;    // 64 KB

  InputGain input_gain;

  float host_sr;
  float engine_sr;
  bool synth_mode;
  int media;
  bool mono;
  size_t block;               // engine frames per block

  bool resample;
  LowPass4 pre_filter, post_filter;
  Resampler down, up;
  SlotFifo<256> engine_in, engine_out;

  GateFlags previous_seed;
  SlotFifo<512> seed_delay_line;  // 2.5 ms seed delay, as on the module
  size_t seed_delay;

  PatchDetector cv_detect[P_REVERB_CV - P_TIME_CV + 1];
  PatchDetector seed_detect;
  bool seed_patched;
  bool cv_patched[P_REVERB_CV - P_TIME_CV + 1];

  bool configured;

  void Configure() {
    media = int(lrintf(*port[P_QUALITY]));
    CONSTRAIN(media, 0, 3);
    mono = *port[P_MONO] > 0.5f;
    synth_mode = *port[P_SYNTH] > 0.5f;

    processor->Configure(Processor::Media(media), mono);
    engine_sr = synth_mode ? 48000.0f : processor->sample_rate();
    block = size_t(engine_sr / kEngineBlockRate);
    if (block > kMaxBlock) block = kMaxBlock;

    input_gain.Init(engine_sr,
        media == Processor::MEDIA_DIRTY_TAPE ? InputGain::CLIP_ON
        : media == Processor::MEDIA_CLEAN_TAPE ? InputGain::CLIP_DYNAMIC
        : InputGain::CLIP_OFF, !configured);

    resample = fabsf(engine_sr - host_sr) > 1.0f;
    const float nyquist_guard = 0.45f * std::min(engine_sr, host_sr);
    pre_filter.Init(nyquist_guard / host_sr);
    post_filter.Init(nyquist_guard / host_sr);
    down.Init(host_sr, engine_sr);
    up.Init(engine_sr, host_sr);
    engine_in.Clear();
    engine_out.Clear();
    // Prime the output with one block of silence so the host never starves.
    for (size_t i = 0; i < block + 4; ++i) engine_out.Push(Slot{0, 0, false, false});

    seed_delay = size_t(engine_sr * 0.0025f);
    seed_delay_line.Clear();
    for (size_t i = 0; i < seed_delay; ++i) seed_delay_line.Push(Slot{0, 0, false, false});
    configured = true;
  }

  static float cv(const float* p) { return p ? *p : 0.0f; }

  // Run one engine block from engine_in into engine_out.
  void RenderBlock(const float* cv_now) {
    FloatFrame in[kMaxBlock], gained[kMaxBlock], out[kMaxBlock];
    bool freeze[kMaxBlock];
    GateFlags seed[kMaxBlock];
    bool any_seed = false;

    for (size_t i = 0; i < block; ++i) {
      Slot s = {0, 0, false, false};
      engine_in.Pop(&s);
      in[i].l = s.l;
      in[i].r = mono ? s.l : s.r;
      freeze[i] = s.freeze || *port[P_FREEZE] > 0.5f;
      // delay the seed gate by 2.5 ms so CV can settle first
      Slot d = {0, 0, false, false};
      seed_delay_line.Push(s);
      seed_delay_line.Pop(&d);
      previous_seed = seed[i] = ExtractGateFlags(previous_seed, d.seed);
      any_seed |= d.seed;
    }

    const float dt = float(block) / engine_sr;
    seed_patched = seed_detect.Process(any_seed, dt);

    // --- knobs + CV, scaled like the module's CV inputs (+-5 V full scale)
    Parameters p;
    const float cv_scale[5] = { 1.6f, 1.6f, 1.6f, 60.0f, 1.0f };
    RandomizedParameter* rp[4] = { &p.time, &p.size, &p.shape, &p.pitch };
    const int base_port[4] = { P_TIME, P_SIZE, P_SHAPE, P_PITCH };
    const int amt_port[4] = { P_TIME_AMT, P_SIZE_AMT, P_SHAPE_AMT, P_PITCH_AMT };
    for (int k = 0; k < 4; ++k) {
      rp[k]->base = *port[base_port[k]];
      rp[k]->attenuverter = *port[amt_port[k]];
      CONSTRAIN(rp[k]->attenuverter, -1.0f, 1.0f);
      rp[k]->has_cv = cv_patched[k];
      float c = cv_now[k] * cv_scale[k];
      if (k < 3) { CONSTRAIN(c, -1.6f, 1.6f); } else { CONSTRAIN(c, -60.0f, 60.0f); }
      rp[k]->cv = c;
    }
    CONSTRAIN(p.time.base, 0.0f, 1.0f);
    CONSTRAIN(p.size.base, 0.0f, 1.0f);
    CONSTRAIN(p.shape.base, 0.0f, 1.0f);
    CONSTRAIN(p.pitch.base, -24.0f, 24.0f);
    p.monophonic_mode = false;

    ModulatedParameter d;
    d.base = *port[P_DENSITY];
    CONSTRAIN(d.base, 0.0f, 1.0f);
    d.cv = cv_patched[4] ? cv_now[4] : 0.0f;
    CONSTRAIN(d.cv, -1.0f, 1.0f);

    float mix[3];
    const int mix_port[3] = { P_FEEDBACK, P_DRY_WET, P_REVERB };
    for (int k = 0; k < 3; ++k) {
      mix[k] = *port[mix_port[k]] * 1.005f + (cv_patched[5 + k] ? cv_now[5 + k] : 0.0f);
      CONSTRAIN(mix[k], 0.0f, 1.0f);
    }
    Processor::MixParameters m;
    m.feedback = mix[0];
    m.dry_wet = mix[1];
    m.reverb_amount = mix[2];
    m.output_gate = *port[P_GATE_OUT] > 0.5f;

    const SeedButtonState seed_button = *port[P_SEED_LOCK] > 0.5f
        ? SEED_BUTTON_STATE_LOCKED
        : (*port[P_SEED_BUTTON] > 0.5f ? SEED_BUTTON_STATE_ON : SEED_BUTTON_STATE_OFF);

    const GateFlags* seed_input = seed_patched ? seed : NULL;
    if (!seed_patched) previous_seed = GATE_FLAG_LOW;

    if (synth_mode) {
      synth->Render(seed_button, seed_input, freeze,
                    Synth::Resolution(media), d, p, m, out, block);
    } else {
      input_gain.Process(*port[P_INPUT_GAIN], in, gained, block);
      processor->Process(seed_button, seed_input, freeze, d, p, m,
                         gained, out, block);
    }

    for (size_t i = 0; i < block; ++i) {
      float l = out[i].l, r = out[i].r;
      CONSTRAIN(l, -1.0f, 1.0f);
      CONSTRAIN(r, -1.0f, 1.0f);
      engine_out.Push(Slot{l, r, false, false});
    }
  }

  void Run(uint32_t n) {
    const int media_now = int(lrintf(*port[P_QUALITY]));
    const bool mono_now = *port[P_MONO] > 0.5f;
    const bool synth_now = *port[P_SYNTH] > 0.5f;
    if (!configured || media_now != media || mono_now != mono || synth_now != synth_mode) {
      Configure();
    }

    const float zero = 0.0f;
    const float* in_l = port[P_IN_L] ? port[P_IN_L] : &zero;
    const float* in_r = port[P_IN_R] ? port[P_IN_R] : &zero;
    const int in_l_step = port[P_IN_L] ? 1 : 0, in_r_step = port[P_IN_R] ? 1 : 0;
    float* out_l = (float*)port[P_OUT_L];
    float* out_r = (float*)port[P_OUT_R];

    const float dt = 1.0f / host_sr;
    for (uint32_t i = 0; i < n; ++i) {
      // CV patch detection at host rate
      float cv_now[P_REVERB_CV - P_TIME_CV + 1];
      for (int k = 0; k <= P_REVERB_CV - P_TIME_CV; ++k) {
        const float* p = port[P_TIME_CV + k];
        cv_now[k] = p ? p[i] : 0.0f;
        cv_patched[k] = cv_detect[k].Process(fabsf(cv_now[k]) > kCvDetectThreshold, dt);
      }

      Slot s;
      s.l = in_l[i * in_l_step];
      s.r = in_r[i * in_r_step];
      s.seed = port[P_SEED_GATE] && port[P_SEED_GATE][i] > kGateHigh;
      s.freeze = port[P_FREEZE_GATE] && port[P_FREEZE_GATE][i] > kGateHigh;

      if (resample) {
        pre_filter.Process(&s.l, &s.r);
        down.Push(s);
        Slot e;
        while (down.Emit(&e)) engine_in.Push(e);
      } else {
        engine_in.Push(s);
      }

      while (engine_in.n >= block) RenderBlock(cv_now);

      Slot o = {0, 0, false, false};
      if (resample) {
        // feed the upsampler until it has an output for this host frame
        while (!up.Emit(&o)) {
          Slot e;
          if (!engine_out.Pop(&e)) { o = Slot{0, 0, false, false}; break; }
          up.Push(e);
        }
        post_filter.Process(&o.l, &o.r);
      } else {
        engine_out.Pop(&o);
      }
      out_l[i] = o.l;
      out_r[i] = o.r;
    }
  }
};

// --------------------------------------------------------------- LV2 glue
LV2_Handle instantiate(const LV2_Descriptor*, double rate, const char*,
                       const LV2_Feature* const*) {
  Droplets* d = new (std::nothrow) Droplets();
  if (!d) return NULL;
  d->processor = new (std::nothrow) Processor();
  d->synth = new (std::nothrow) Synth();
  d->delay_memory = static_cast<uint8_t*>(calloc(768 * 1024, 1));
  d->reverb_memory = static_cast<uint16_t*>(calloc(32768, sizeof(uint16_t)));
  if (!d->processor || !d->synth || !d->delay_memory || !d->reverb_memory) {
    delete d->processor; delete d->synth;
    free(d->delay_memory); free(d->reverb_memory); delete d;
    return NULL;
  }
  d->host_sr = float(rate);
  return d;
}

void connect_port(LV2_Handle h, uint32_t p, void* data) {
  if (p < P_LAST) static_cast<Droplets*>(h)->port[p] = static_cast<const float*>(data);
}

void activate(LV2_Handle h) {
  Droplets* d = static_cast<Droplets*>(h);
  uint8_t* buffers[3] = {
    d->delay_memory, d->delay_memory + 256 * 1024, d->delay_memory + 512 * 1024
  };
  memset(d->delay_memory, 0, 768 * 1024);
  memset(d->reverb_memory, 0, 32768 * sizeof(uint16_t));
  d->processor->Init(buffers, d->reverb_memory);
  d->synth->Init(d->reverb_memory);
  for (auto& c : d->cv_detect) c.Init(kCvDetectHold);
  d->seed_detect.Init(kSeedDetectHold);
  d->previous_seed = GATE_FLAG_LOW;
  d->configured = false;
}

void run(LV2_Handle h, uint32_t n) {
  Droplets* d = static_cast<Droplets*>(h);
  static const float kDefaults[P_LAST] = {
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0.5f, 0.5f, 0.5f, 0.5f, 0.0f,   // time size shape density pitch
    0, 0, 0, 0,                      // amounts
    0.5f, 0.5f, 0.3f,                // feedback dry/wet reverb
    0, 0, 1,                         // freeze seed lock (latched, as on power-up)
    3, 0, 0, 0, 0                    // quality mono gain synth gate
  };
  // Any control a host leaves unconnected falls back to its default.
  for (int p = P_TIME; p < P_LAST; ++p) {
    if (!d->port[p]) d->port[p] = &kDefaults[p];
  }
  if (!d->port[P_OUT_L] || !d->port[P_OUT_R]) return;
  d->Run(n);
}

void cleanup(LV2_Handle h) {
  Droplets* d = static_cast<Droplets*>(h);
  delete d->processor;
  delete d->synth;
  free(d->delay_memory);
  free(d->reverb_memory);
  delete d;
}

const LV2_Descriptor descriptor = {
  DROPLETS_URI, instantiate, connect_port, activate, run, NULL, cleanup, NULL
};

}  // namespace

LV2_SYMBOL_EXPORT const LV2_Descriptor* lv2_descriptor(uint32_t index) {
  return index == 0 ? &descriptor : NULL;
}
