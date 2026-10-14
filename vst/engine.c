/* The CA-72 engine (Rust, engine/ca72-mpc) as mpc-vst-plugins' mpc_engine() (wrapper/engine.h). */
#include <stddef.h>
#include "engine.h"

void *ca72_create(void);
void ca72_destroy(void *e);
void ca72_midi(void *e, const uint8_t *m, int len);
void ca72_set_param(void *e, const char *k, const char *v);
int ca72_get_param(void *e, const char *k, char *buf, int len);
void ca72_render(void *e, int16_t *out, int frames);

static void *create(const char *dir) { (void)dir; return ca72_create(); }

static const mpc_engine_t api = {
    create, ca72_destroy, ca72_midi, ca72_set_param, ca72_get_param, ca72_render, NULL, NULL,
};

const mpc_engine_t *mpc_engine(void) { return &api; }
