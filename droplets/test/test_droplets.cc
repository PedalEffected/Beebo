// Test host for the Droplets LV2 plugin.
// Loads droplets.so like a host would, runs scenarios, writes WAVs, checks
// results, and compares against the Beads engine called directly.
//
//   g++ -O2 -std=c++11 -I$EURORACK -include ../lv2/droplets_compat.h \
//       test_droplets.cc $ENGINE_SOURCES -ldl -o test_droplets
//   ./test_droplets path/to/droplets.so [outdir]

#include <dlfcn.h>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include <lv2/core/lv2.h>

#include "beads/dsp/processor.h"

static int fails = 0;
#define CHECK(c, ...) do { std::printf((c) ? "ok:   " : "FAIL: "); std::printf(__VA_ARGS__); std::printf("\n"); if (!(c)) ++fails; } while (0)

enum Port {
  P_IN_L = 0, P_IN_R, P_OUT_L, P_OUT_R, P_SEED_GATE, P_FREEZE_GATE,
  P_TIME_CV, P_SIZE_CV, P_SHAPE_CV, P_PITCH_CV, P_DENSITY_CV,
  P_FEEDBACK_CV, P_DRY_WET_CV, P_REVERB_CV,
  P_TIME, P_SIZE, P_SHAPE, P_DENSITY, P_PITCH,
  P_TIME_AMT, P_SIZE_AMT, P_SHAPE_AMT, P_PITCH_AMT,
  P_FEEDBACK, P_DRY_WET, P_REVERB, P_FREEZE, P_SEED_BUTTON, P_SEED_LOCK,
  P_QUALITY, P_MONO, P_INPUT_GAIN, P_SYNTH, P_GATE_OUT, P_LAST
};

static void WriteWav(const std::string& path, const std::vector<float>& l,
                     const std::vector<float>& r, int sr) {
  FILE* f = fopen(path.c_str(), "wb");
  if (!f) return;
  const uint32_t n = l.size(), data = n * 4, riff = 36 + data;
  const uint16_t fmt = 1, ch = 2, bits = 16, align = 4;
  const uint32_t fmtlen = 16, rate = sr, bps = sr * 4;
  fwrite("RIFF", 1, 4, f); fwrite(&riff, 4, 1, f); fwrite("WAVEfmt ", 1, 8, f);
  fwrite(&fmtlen, 4, 1, f); fwrite(&fmt, 2, 1, f); fwrite(&ch, 2, 1, f);
  fwrite(&rate, 4, 1, f); fwrite(&bps, 4, 1, f); fwrite(&align, 2, 1, f);
  fwrite(&bits, 2, 1, f); fwrite("data", 1, 4, f); fwrite(&data, 4, 1, f);
  for (uint32_t i = 0; i < n; ++i) {
    int16_t s[2] = { int16_t(std::max(-1.f, std::min(1.f, l[i])) * 32767),
                     int16_t(std::max(-1.f, std::min(1.f, r[i])) * 32767) };
    fwrite(s, 2, 2, f);
  }
  fclose(f);
}

struct Host {
  const LV2_Descriptor* d;
  LV2_Handle h;
  float sr;
  float ctl[P_LAST];
  std::vector<float> buf[P_LAST];
  static const int N = 256;

  Host(const LV2_Descriptor* desc, float rate) : d(desc), sr(rate) {
    h = d->instantiate(d, rate, "", NULL);
    const float defaults[P_LAST] = {0,0,0,0,0,0,0,0,0,0,0,0,0,0,
      0.5f,0.5f,0.5f,0.5f,0, 0,0,0,0, 0.5f,0.5f,0.3f, 0,0,1, 3,0,0,0,0};
    for (int p = 0; p < P_LAST; ++p) {
      ctl[p] = defaults[p];
      if (p <= P_REVERB_CV) { buf[p].assign(N, 0.0f); d->connect_port(h, p, buf[p].data()); }
      else d->connect_port(h, p, &ctl[p]);
    }
    d->activate(h);
  }
  ~Host() { d->cleanup(h); }

  // Render `seconds`; fill(i) sets per-sample inputs (absolute sample index).
  template<typename F>
  double Render(float seconds, std::vector<float>* ol, std::vector<float>* orr, F fill) {
    const long total = long(seconds * sr);
    double cpu = 0;
    for (long pos = 0; pos < total; pos += N) {
      for (int i = 0; i < N; ++i) fill(pos + i, i);
      auto t0 = std::chrono::steady_clock::now();
      d->run(h, N);
      cpu += std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
      ol->insert(ol->end(), buf[P_OUT_L].begin(), buf[P_OUT_L].end());
      orr->insert(orr->end(), buf[P_OUT_R].begin(), buf[P_OUT_R].end());
    }
    return cpu / seconds;  // fraction of real time
  }
};

static bool Finite(const std::vector<float>& v) {
  for (float x : v) if (!std::isfinite(x)) return false;
  return true;
}
static float Rms(const std::vector<float>& v, size_t a = 0, size_t b = 0) {
  if (!b) b = v.size();
  double s = 0; for (size_t i = a; i < b; ++i) s += v[i] * v[i];
  return std::sqrt(s / std::max<size_t>(1, b - a));
}
static float Peak(const std::vector<float>& v) {
  float m = 0; for (float x : v) m = std::max(m, std::fabs(x)); return m;
}

// Plucked test signal: short decaying notes every 0.5 s.
static float Pluck(long i, float sr) {
  const float t = std::fmod(i / sr, 0.5f);
  const float notes[4] = {220.f, 277.18f, 329.63f, 440.f};
  const float f = notes[(long(i / sr / 0.5f)) % 4];
  return 0.5f * std::sin(2 * M_PI * f * t) * std::exp(-t * 8.f);
}

// Energy of the output between times a..b (seconds) - used to find echoes.
static float Window(const std::vector<float>& v, float sr, float a, float b) {
  return Rms(v, size_t(a * sr), size_t(b * sr));
}

int main(int argc, char** argv) {
  if (argc < 2) { std::printf("usage: %s droplets.so [outdir]\n", argv[0]); return 2; }
  const std::string out = argc > 2 ? argv[2] : ".";
  void* lib = dlopen(argv[1], RTLD_NOW);
  if (!lib) { std::printf("%s\n", dlerror()); return 1; }
  auto fn = (LV2_Descriptor_Function)dlsym(lib, "lv2_descriptor");
  const LV2_Descriptor* desc = fn(0);
  CHECK(desc && std::string(desc->URI) == "https://github.com/PedalEffected/Beebo#Droplets", "URI %s", desc ? desc->URI : "null");
  CHECK(fn(1) == NULL, "single plugin exported");

  // 2. Wrapper matches the Beads engine called directly (digital, 48 kHz).
  {
    Host x(desc, 48000);
    x.ctl[P_INPUT_GAIN] = 0.25f; x.ctl[P_DRY_WET] = 1.0f; x.ctl[P_DENSITY] = 0.7f;
    std::vector<float> l, r;
    x.Render(3, &l, &r, [&](long i, int k) { x.buf[P_IN_L][k] = x.buf[P_IN_R][k] = Pluck(i, 48000); });

    // Reference: engine directly, same block size and gain law.
    static uint8_t mem[768 * 1024]; static uint16_t rev[32768];
    memset(mem, 0, sizeof mem); memset(rev, 0, sizeof rev);
    uint8_t* bufs[3] = { mem, mem + 256 * 1024, mem + 512 * 1024 };
    beads::Processor* p = new beads::Processor();
    p->Init(bufs, rev);
    p->Configure(beads::Processor::MEDIA_DIGITAL, false);
    std::vector<float> rl;
    float g = 1.0f;  // same manual-gain smoothing as the plugin
    const float target = 1.0f + 39.0f * powf(0.25f * 0.25f, 2.0f);
    float gain_state = 1.0f;
    for (long pos = 0; pos + 24 <= long(3 * 48000); pos += 24) {
      beads::FloatFrame in[24], o[24]; bool fz[24] = {false};
      ONE_POLE(g, target, 0.01f);
      const float step = (g - gain_state) / 24.f;
      for (int i = 0; i < 24; ++i) {
        gain_state += step;
        float s = Pluck(pos + i, 48000) * gain_state;
        s = std::max(-1.f, std::min(1.f, s));
        in[i].l = in[i].r = s;
      }
      beads::Parameters prm = {};
      prm.time.base = prm.size.base = prm.shape.base = 0.5f; prm.pitch.base = 0;
      beads::ModulatedParameter dens = {0.7f, 0.0f};
      beads::Processor::MixParameters m = {0.5f * 1.005f, 1.0f, 0.3f * 1.005f, false};
      if (m.dry_wet > 1) m.dry_wet = 1;
      p->Process(beads::SEED_BUTTON_STATE_LOCKED, NULL, fz, dens, prm, m, in, o, 24);
      for (int i = 0; i < 24; ++i) rl.push_back(std::max(-1.f, std::min(1.f, o[i].l)));
    }
    delete p;
    // the plugin primes its output with (block + 4) frames of silence
    const size_t lat = 24 + 4;
    double err = 0, ref = 0;
    for (size_t i = 0; i + lat < l.size() && i < rl.size(); ++i) {
      err += std::pow(l[i + lat] - rl[i], 2); ref += rl[i] * rl[i];
    }
    const double rel = std::sqrt(err / std::max(ref, 1e-12));
    CHECK(rel < 1e-3, "wrapper == Beads engine called directly (relative error %.2e, latency %zu samples)", rel, lat);
  }

  // 1. Granular, digital quality, 48 kHz
  {
    Host x(desc, 48000);
    x.ctl[P_INPUT_GAIN] = 0.25f;   // fixed manual gain: deterministic
    x.ctl[P_DRY_WET] = 1.0f;
    x.ctl[P_DENSITY] = 0.7f;
    std::vector<float> l, r;
    const double cpu = x.Render(8, &l, &r, [&](long i, int k) {
      x.buf[P_IN_L][k] = x.buf[P_IN_R][k] = Pluck(i, 48000); });
    WriteWav(out + "/1_granular_digital.wav", l, r, 48000);
    CHECK(Finite(l) && Finite(r), "granular: no NaN/inf");
    CHECK(Rms(l, 48000) > 0.01f && Peak(l) <= 1.0f, "granular: audible wet output (rms %.3f, peak %.2f)", Rms(l, 48000), Peak(l));
    std::printf("      CPU (x86 host): %.1f%% of real time\n", cpu * 100);
  }

  // 3. Clocked delay: SIZE fully clockwise, clock on SEED at 120 BPM.
  {
    Host x(desc, 48000);
    x.ctl[P_SIZE] = 1.0f; x.ctl[P_DRY_WET] = 1.0f; x.ctl[P_FEEDBACK] = 0.0f;
    x.ctl[P_REVERB] = 0.0f; x.ctl[P_INPUT_GAIN] = 0.25f;
    x.ctl[P_DENSITY] = 0.475f;  // ratio table index 9 -> 1x the clock
    x.ctl[P_TIME] = 0.0f;       // multiplier 1
    std::vector<float> l, r;
    const float sr = 48000, period = 0.5f;
    x.Render(10, &l, &r, [&](long i, int k) {
      const float t = i / sr;
      x.buf[P_SEED_GATE][k] = std::fmod(t, period) < 0.005f ? 1.0f : 0.0f;
      // one click at t = 7.25 s, between clock ticks
      x.buf[P_IN_L][k] = x.buf[P_IN_R][k] = (i >= long(7.25f * sr) && i < long(7.25f * sr) + 48) ? 0.8f : 0.0f;
    });
    WriteWav(out + "/3_clocked_delay.wav", l, r, sr);
    // echo expected one clock period after the click
    const float before = Window(l, sr, 7.30f, 7.70f);
    const float echo = Window(l, sr, 7.70f, 7.80f);
    CHECK(Finite(l), "clocked delay: no NaN/inf");
    CHECK(echo > 10 * before && echo > 1e-3f, "clocked delay: echo lands one clock period (0.5 s) after the click (rms %.4f vs %.5f before)", echo, before);
  }

  // 4. Freeze holds the buffer after the input stops.
  {
    Host x(desc, 48000);
    x.ctl[P_DRY_WET] = 1.0f; x.ctl[P_INPUT_GAIN] = 0.25f; x.ctl[P_DENSITY] = 0.7f;
    std::vector<float> l, r;
    x.Render(8, &l, &r, [&](long i, int k) {
      const float t = i / 48000.f;
      x.buf[P_IN_L][k] = x.buf[P_IN_R][k] = t < 4 ? Pluck(i, 48000) : 0.0f;
      x.buf[P_FREEZE_GATE][k] = t > 3.5f ? 1.0f : 0.0f;
    });
    WriteWav(out + "/4_freeze.wav", l, r, 48000);
    CHECK(Window(l, 48000, 6.0f, 8.0f) > 0.005f, "freeze: grains keep playing after input stops (rms %.3f)", Window(l, 48000, 6.0f, 8.0f));
  }

  // 5. Every quality mode at 48 kHz and 44.1 kHz hosts (resampling path).
  const char* qn[4] = {"dirty_tape", "clean_tape", "vintage_digital", "digital"};
  for (float host_sr : {48000.f, 44100.f}) {
    for (int q = 0; q < 4; ++q) {
      Host x(desc, host_sr);
      x.ctl[P_QUALITY] = q; x.ctl[P_DRY_WET] = 0.8f; x.ctl[P_INPUT_GAIN] = 0.25f;
      x.ctl[P_DENSITY] = 0.7f;
      std::vector<float> l, r;
      const double cpu = x.Render(6, &l, &r, [&](long i, int k) {
        x.buf[P_IN_L][k] = x.buf[P_IN_R][k] = Pluck(long(i * 48000.0 / host_sr), 48000); });
      char name[128]; snprintf(name, sizeof name, "%s/5_%s_%d.wav", out.c_str(), qn[q], int(host_sr));
      WriteWav(name, l, r, int(host_sr));
      // the output must keep flowing (no FIFO starvation gaps)
      size_t zero_run = 0, worst = 0;
      for (size_t i = host_sr; i < l.size(); ++i) { zero_run = (l[i] == 0.0f) ? zero_run + 1 : 0; worst = std::max(worst, zero_run); }
      CHECK(Finite(l) && Rms(l, size_t(host_sr)) > 0.01f && worst < 64,
            "quality %-16s @ %5.0f Hz host: output ok (rms %.3f, longest silent run %zu, CPU %.1f%%)",
            qn[q], host_sr, Rms(l, size_t(host_sr)), worst, cpu * 100);
    }
  }

  // 6. Synth mode with nothing patched.
  {
    Host x(desc, 48000);
    x.ctl[P_SYNTH] = 1.0f; x.ctl[P_DRY_WET] = 1.0f; x.ctl[P_DENSITY] = 0.7f;
    std::vector<float> l, r;
    x.Render(4, &l, &r, [&](long, int) {});
    WriteWav(out + "/6_synth.wav", l, r, 48000);
    CHECK(Finite(l) && Rms(l, 48000) > 0.005f, "synth mode: makes sound with no input (rms %.3f)", Rms(l, 48000));
  }

  // 7. CV: pitch CV of +1.0 (= +5 V on Hector) is accepted and stays bounded.
  {
    Host x(desc, 48000);
    x.ctl[P_DRY_WET] = 1.0f; x.ctl[P_INPUT_GAIN] = 0.25f; x.ctl[P_PITCH_AMT] = 1.0f; x.ctl[P_DENSITY] = 0.7f;
    std::vector<float> l, r;
    x.Render(4, &l, &r, [&](long i, int k) {
      x.buf[P_IN_L][k] = x.buf[P_IN_R][k] = Pluck(i, 48000);
      x.buf[P_PITCH_CV][k] = 0.2f;   // +1 V = one octave up
      x.buf[P_TIME_CV][k] = std::sin(i / 48000.f);
    });
    WriteWav(out + "/7_cv.wav", l, r, 48000);
    CHECK(Finite(l) && Peak(l) <= 1.0f && Rms(l, 48000) > 0.005f, "CV inputs: pitch + time modulation stay finite and bounded");
  }

  std::printf(fails ? "\n%d FAILED\n" : "\nALL PASSED\n", fails);
  return fails != 0;
}
