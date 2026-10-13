#include <dlfcn.h>
#include <stdio.h>
#include <math.h>
#include <string.h>
#include <lv2/core/lv2.h>
#define N 64
static int fails = 0;
#define CHECK(c, ...) do { if (!(c)) { fails++; printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); } else { printf("ok:   "); printf(__VA_ARGS__); printf("\n"); } } while (0)
int main(int argc, char** argv) {
  void* lib = dlopen(argv[1], RTLD_NOW); if (!lib) { printf("%s\n", dlerror()); return 1; }
  LV2_Descriptor_Function f = (LV2_Descriptor_Function)dlsym(lib, "lv2_descriptor");
  float back[N], fwd[N], reset[N], out[N], vals[16], steps = 4, glide = 0, cur = -1, bpm = 120, nl = 0.25;
  /* steps in volts: -5, 0, +5, +2.5 -> CV -1, 0, +1, +0.5 */
  float sl[4] = {-5.0f, 0.0f, 5.0f, 2.5f}; float expect[4] = {-1, 0, 1, 0.5};
  for (int i = 0; i < 16; i++) vals[i] = i < 4 ? sl[i] : 0.0f;

  /* ---- external trigger variant ---- */
  const LV2_Descriptor* d = f(1);
  CHECK(d && strcmp(d->URI, "https://github.com/PedalEffected/Beebo#BiPoSeq_ext") == 0, "index 1 URI %s", d ? d->URI : "null");
  LV2_Handle h = d->instantiate(d, 48000, "", NULL);
  d->connect_port(h, 0, back); d->connect_port(h, 1, fwd); d->connect_port(h, 2, &steps);
  d->connect_port(h, 3, reset); d->connect_port(h, 4, &glide);
  for (int i = 0; i < 16; i++) d->connect_port(h, 5 + i, &vals[i]);
  d->connect_port(h, 21, out); d->connect_port(h, 22, &cur);
  d->activate(h);
  memset(back, 0, sizeof back); memset(reset, 0, sizeof reset); memset(fwd, 0, sizeof fwd);
  for (int step = 0; step < 6; step++) {
    if (step > 0) fwd[0] = 1.0f; else fwd[0] = 0; /* one rising edge per block */
    d->run(h, N); fwd[0] = 0; d->run(h, N); /* release */
    int idx = step % 4;
    CHECK((int)cur == idx && fabsf(out[N-1] - expect[idx]) < 1e-5, "ext step %d -> idx %d out %.3f (%.1f V)", step, (int)cur, out[N-1], out[N-1]*5);
  }
  /* back trigger from idx 1 -> 0 */
  back[0] = 1; d->run(h, N); back[0] = 0;
  CHECK((int)cur == 0 && fabsf(out[N-1] + 1) < 1e-5, "ext back trigger -> idx %d out %.1f V", (int)cur, out[N-1]*5);
  back[0] = 1; d->run(h, N); back[0] = 0;
  CHECK((int)cur == 3, "ext back wraps 0 -> %d", (int)cur);
  reset[0] = 1; d->run(h, N); reset[0] = 0;
  CHECK((int)cur == 0, "ext reset -> idx %d", (int)cur);
  /* out-of-range slider is clamped */
  vals[0] = 9.0f; d->run(h, N);
  CHECK(fabsf(out[N-1] - 1) < 1e-5, "typed 9 V clamps to %.1f V", out[N-1]*5);
  vals[0] = -12.0f; d->run(h, N);
  CHECK(fabsf(out[N-1] + 1) < 1e-5, "typed -12 V clamps to %.1f V", out[N-1]*5);
  vals[0] = -1.25f; d->run(h, N);
  CHECK(fabsf(out[N-1]*5 + 1.25f) < 1e-5, "typed -1.25 V gives %.2f V", out[N-1]*5);
  vals[0] = -5.0f;
  /* glide: moving from -5V toward +5V should pass smoothly through 0 */
  glide = 0.01f; fwd[0] = 1; fwd[1] = 1; d->run(h, N); fwd[0] = fwd[1] = 0; d->run(h, N); /* idx -> 1 (0V) */
  float before = out[N-1];
  fwd[0] = 1; d->run(h, N); fwd[0] = 0; /* idx -> 2 (+5V) with glide */
  CHECK(out[N-1] > before && out[N-1] < 1.0f, "ext glide rising smoothly: %.2f V -> %.2f V in %d samples", before*5, out[N-1]*5, N);
  for (int k = 0; k < 2000; k++) d->run(h, N);
  CHECK(fabsf(out[N-1] - 1) < 1e-3, "ext glide settles at %.2f V", out[N-1]*5);
  d->cleanup(h);

  /* ---- BPM variant ---- */
  d = f(0);
  CHECK(d && strcmp(d->URI, "https://github.com/PedalEffected/Beebo#BiPoSeq") == 0, "index 0 URI %s", d ? d->URI : "null");
  CHECK(f(2) == NULL, "only two plugins exported");
  glide = 0; vals[0] = -5.0f;
  h = d->instantiate(d, 48000, "", NULL);
  d->connect_port(h, 0, back); d->connect_port(h, 1, fwd); d->connect_port(h, 2, &steps);
  d->connect_port(h, 3, reset); d->connect_port(h, 4, &glide);
  for (int i = 0; i < 16; i++) d->connect_port(h, 5 + i, &vals[i]);
  d->connect_port(h, 21, out); d->connect_port(h, 22, &cur); d->connect_port(h, 23, &bpm); d->connect_port(h, 24, &nl);
  d->activate(h);
  /* 120 bpm, quarter notes = 24000 samples per step; play gate held high */
  for (int i = 0; i < N; i++) { fwd[i] = 1; back[i] = 0; reset[i] = 0; }
  int seen[4] = {0}; long total = 0; int changes = 0, last = 0;
  for (int b = 0; b < (48000*4)/N; b++) { d->run(h, N); total += N; seen[(int)cur]++; if ((int)cur != last) { changes++; last = (int)cur;
      CHECK(fabsf(out[N-1] - expect[(int)cur]) < 1e-5, "bpm t=%.2fs idx %d out %.1f V", total/48000.0, (int)cur, out[N-1]*5); } }
  CHECK(changes == 7, "bpm 4 s at 120 bpm quarter notes -> %d step changes (expect 7)", changes);
  d->cleanup(h);
  printf(fails ? "\n%d FAILED\n" : "\nALL PASSED\n", fails);
  return fails != 0;
}
