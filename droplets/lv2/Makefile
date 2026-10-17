#!/usr/bin/make -f
# Droplets - Beads engine as an LV2 module for Beebo / Hector.
#   make EURORACK=/path/to/pichenettes/eurorack          native build
#   make arm64 EURORACK=... LV2_INCLUDE=...             pedal build -> ../prebuilt-arm64
EURORACK   ?= ../third_party/eurorack
PREFIX     ?= /usr
LV2DIR     ?= $(PREFIX)/lib/lv2
BUNDLE      = droplets.lv2
BUILDDIR    = build/$(BUNDLE)
CXX        ?= g++
CXXFLAGS   ?= -O2 -ffast-math -fno-finite-math-only -Wall -Wno-unused-local-typedefs -Wno-unused-variable -Wno-strict-aliasing
override CXXFLAGS += -std=c++11 -fPIC -fvisibility=hidden -I$(EURORACK) -include droplets_compat.h

ENGINE_SRC = beads/dsp/processor.cc beads/dsp/synth.cc beads/dsp/mu_law.cc \
             beads/dsp/delay_clock.cc beads/dsp/delay_controller.cc \
             beads/dsp/trigger_generator.cc beads/resources.cc \
             stmlib/utils/random.cc stmlib/dsp/units.cc
SRC = droplets.cc $(addprefix $(EURORACK)/,$(ENGINE_SRC))

all: $(BUILDDIR)/droplets.so $(BUILDDIR)/manifest.ttl $(BUILDDIR)/droplets.ttl

$(BUILDDIR)/droplets.so: $(SRC)
	@mkdir -p $(BUILDDIR)
	$(CXX) $(CXXFLAGS) -shared -Wl,--version-script=exports.map -o $@ $(SRC) $(LDFLAGS) -lm

$(BUILDDIR)/%.ttl: %.ttl
	@mkdir -p $(BUILDDIR)
	cp $< $@

install: all
	install -d $(DESTDIR)$(LV2DIR)/$(BUNDLE)
	install -m755 $(BUILDDIR)/droplets.so $(DESTDIR)$(LV2DIR)/$(BUNDLE)/
	install -m644 $(BUILDDIR)/*.ttl $(DESTDIR)$(LV2DIR)/$(BUNDLE)/

# Pedal build: ARM64, linked against glibc 2.17 so it loads on older
# Debian images, with no C++ standard library dependency (nolibcxx.cc).
# Uses Zig as the cross toolchain (pip install ziglang).
# LV2_INCLUDE must contain lv2/core/lv2.h (e.g. a copy of /usr/include/lv2).
ZIG        ?= python3 -m ziglang
LV2_INCLUDE ?= /usr/include
arm64:
	@mkdir -p ../prebuilt-arm64/$(BUNDLE) build/arm64
	for f in $(SRC) nolibcxx.cc; do \
	  $(ZIG) c++ -target aarch64-linux-gnu.2.17 -mcpu=cortex_a53 -O2 -ffast-math \
	    -fno-finite-math-only -std=c++11 -fPIC -fvisibility=hidden -fno-exceptions -fno-rtti \
	    -I$(EURORACK) -I$(LV2_INCLUDE) -include droplets_compat.h \
	    -c $$f -o build/arm64/$$(basename $$f .cc).o || exit 1; \
	done
	$(ZIG) c++ -target aarch64-linux-gnu.2.17 -shared -nostdlib++ \
	  -Wl,--version-script=exports.map -o ../prebuilt-arm64/$(BUNDLE)/droplets.so build/arm64/*.o -lm
	llvm-strip ../prebuilt-arm64/$(BUNDLE)/droplets.so 2>/dev/null || aarch64-linux-gnu-strip ../prebuilt-arm64/$(BUNDLE)/droplets.so
	cp manifest.ttl droplets.ttl ../prebuilt-arm64/$(BUNDLE)/

clean:
	rm -rf build

.PHONY: all install arm64 clean
