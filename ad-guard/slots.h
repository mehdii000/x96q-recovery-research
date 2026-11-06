#ifndef REROUTE_SLOTS_H
#define REROUTE_SLOTS_H
#include <stddef.h>
typedef struct { void **slot; void *original; void *replacement; int protection; } GuardSlot;
typedef int (*GuardProtect)(void *,size_t,int);
int guard_install_slots(GuardSlot *,size_t,GuardProtect);
int guard_restore_slots(GuardSlot *,size_t,GuardProtect);
#endif
