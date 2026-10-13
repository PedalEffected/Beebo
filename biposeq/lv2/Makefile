#!/usr/bin/make -f
# BiPoSeq - bipolar step sequencer for Beebo / Hector.
#   On the pedal (ARM64):   make && sudo make install
#   Cross-compile for ARM64: make arm64   (needs gcc-aarch64-linux-gnu)
PREFIX     ?= /usr
LV2DIR     ?= $(PREFIX)/lib/lv2
BUNDLE      = biposeq.lv2
NAME        = biposeq
BUILDDIR    = build/$(BUNDLE)
CFLAGS     ?= -O3 -ffast-math -fno-finite-math-only -Wall -Wextra
override CFLAGS += -fPIC -fvisibility=hidden -std=c99 -D_DEFAULT_SOURCE
LDLIBS      = -lm

UNAME := $(shell uname)
ifeq ($(UNAME),Darwin)
  LIB_EXT = .dylib
  SHARED  = -dynamiclib
else
  LIB_EXT = .so
  SHARED  = -shared
endif

all: $(BUILDDIR)/$(NAME)$(LIB_EXT) $(BUILDDIR)/manifest.ttl $(BUILDDIR)/$(NAME).ttl

$(BUILDDIR)/$(NAME)$(LIB_EXT): $(NAME).c
	@mkdir -p $(BUILDDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(SHARED) -o $@ $< $(LDFLAGS) $(LDLIBS)

$(BUILDDIR)/manifest.ttl: manifest.ttl
	@mkdir -p $(BUILDDIR)
	sed 's/\.so>/$(LIB_EXT)>/' $< > $@

$(BUILDDIR)/$(NAME).ttl: $(NAME).ttl
	@mkdir -p $(BUILDDIR)
	cp $< $@

install: all
	install -d $(DESTDIR)$(LV2DIR)/$(BUNDLE)
	install -m755 $(BUILDDIR)/$(NAME)$(LIB_EXT) $(DESTDIR)$(LV2DIR)/$(BUNDLE)/
	install -m644 $(BUILDDIR)/*.ttl $(DESTDIR)$(LV2DIR)/$(BUNDLE)/

uninstall:
	rm -rf $(DESTDIR)$(LV2DIR)/$(BUNDLE)

clean:
	rm -rf build

# Prebuilt binary for the pedal (Cortex-A53, runs on glibc >= 2.17)
arm64:
	$(MAKE) clean
	$(MAKE) CC=aarch64-linux-gnu-gcc CFLAGS="-O3 -mcpu=cortex-a53 -ffast-math -fno-finite-math-only -Wall -Wextra -DLEGACY_GLIBC"
	aarch64-linux-gnu-strip $(BUILDDIR)/$(NAME).so
	rm -rf ../prebuilt-arm64/$(BUNDLE) && mkdir -p ../prebuilt-arm64 && cp -r $(BUILDDIR) ../prebuilt-arm64/

.PHONY: all install uninstall clean arm64
