Test host for Droplets. Loads the built plugin like an LV2 host would and runs
19 checks (engine match, grains, freeze, clocked delay, quality modes at 48 and
44.1 kHz, synth mode, CV), writing a WAV per scenario.

    T=../third_party/eurorack
    for f in beads/dsp/processor.cc beads/dsp/synth.cc beads/dsp/mu_law.cc \
             beads/dsp/delay_clock.cc beads/dsp/delay_controller.cc \
             beads/dsp/trigger_generator.cc beads/resources.cc \
             stmlib/utils/random.cc stmlib/dsp/units.cc; do
      g++ -O2 -std=c++11 -I$T -include ../lv2/droplets_compat.h -c $T/$f -o $(echo $f | tr / _).o
    done
    g++ -O2 -std=c++11 -DTEST -I$T -c test_droplets.cc -o test.o
    g++ *.o -ldl -o test_droplets
    ./test_droplets ../lv2/build/droplets.lv2/droplets.so /tmp
