/* LV2 shell around one omins LADSPA plugin (compile together with its .c).

   The LV2 versions of omins that Beebo uses (drobilla.net/plugins/omins/...)
   aren't published, but the original LADSPA code is. This exposes it under
   the same plugin URI and port symbols, so Beebo presets keep working.

   cc -shared -fPIC -I. -D_init=omins_init -D_fini=omins_fini
      -DPLUGIN_URI='"http://drobilla.net/plugins/omins/adenv"'
      adenv.c lv2_wrap.c -o adenv.so
*/
#include <stdint.h>
#include <stdlib.h>
#include "ladspa.h"

#ifdef _WIN32
#  define EXPORT __declspec(dllexport)
#else
#  define EXPORT __attribute__((visibility("default")))
#endif

extern LADSPA_Descriptor** dahdsr_descriptors;   /* set up by omins_init() */
void omins_init(void);

typedef struct {
	const LADSPA_Descriptor* ld;
	LADSPA_Handle            h;
} Wrap;

static const LADSPA_Descriptor* get_ld(void)
{
	if (!dahdsr_descriptors) {
		omins_init();   /* on Linux the loader may already have run it */
	}
	return ladspa_descriptor(0);
}

static void* instantiate(const void* d, double rate, const char* path, const void* const* f)
{
	(void)d; (void)path; (void)f;
	const LADSPA_Descriptor* ld = get_ld();
	if (!ld) {
		return NULL;
	}
	Wrap* w = (Wrap*)calloc(1, sizeof(Wrap));
	w->ld = ld;
	w->h  = ld->instantiate(ld, (unsigned long)rate);
	if (!w->h) {
		free(w);
		return NULL;
	}
	return w;
}

static void connect_port(void* i, uint32_t port, void* data)
{
	Wrap* w = (Wrap*)i;
	w->ld->connect_port(w->h, port, (LADSPA_Data*)data);
}

static void activate(void* i)
{
	Wrap* w = (Wrap*)i;
	if (w->ld->activate) {
		w->ld->activate(w->h);
	}
}

static void run(void* i, uint32_t n)
{
	Wrap* w = (Wrap*)i;
	w->ld->run(w->h, n);
}

static void deactivate(void* i)
{
	Wrap* w = (Wrap*)i;
	if (w->ld->deactivate) {
		w->ld->deactivate(w->h);
	}
}

static void cleanup(void* i)
{
	Wrap* w = (Wrap*)i;
	if (w->ld->cleanup) {
		w->ld->cleanup(w->h);
	}
	free(w);
}

static const void* extension_data(const char* uri)
{
	(void)uri;
	return NULL;
}

/* same layout as LV2_Descriptor in lv2/core/lv2.h */
typedef struct {
	const char* URI;
	void* (*instantiate)(const void*, double, const char*, const void* const*);
	void (*connect_port)(void*, uint32_t, void*);
	void (*activate)(void*);
	void (*run)(void*, uint32_t);
	void (*deactivate)(void*);
	void (*cleanup)(void*);
	const void* (*extension_data)(const char*);
} Descriptor;

static const Descriptor descriptor = {
	PLUGIN_URI, instantiate, connect_port, activate, run, deactivate, cleanup, extension_data
};

EXPORT const Descriptor* lv2_descriptor(uint32_t index)
{
	return index == 0 ? &descriptor : NULL;
}
