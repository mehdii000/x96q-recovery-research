#ifndef REROUTE_AD_PATCH_H
#define REROUTE_AD_PATCH_H
#include <stddef.h>
void guard_sha256(const unsigned char *, size_t, unsigned char[32]);
int guard_patch(unsigned char *, size_t);
int guard_boundary(size_t return_address, size_t engine_base, size_t length);
#endif
