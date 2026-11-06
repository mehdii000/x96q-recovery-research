#include "slots.h"
static int write_slot(GuardSlot *s,void *value,GuardProtect protect){
    void *page=(void *)((size_t)s->slot&~(size_t)4095);
    if(protect(page,4096,3))return 0;
    __atomic_store_n(s->slot,value,__ATOMIC_RELEASE);
    return protect(page,4096,s->protection)==0;
}
int guard_restore_slots(GuardSlot *slots,size_t count,GuardProtect protect){
    int restored=1;
    for(size_t i=0;i<count;i++)if(!write_slot(&slots[i],slots[i].original,protect))restored=0;
    return restored;
}
int guard_install_slots(GuardSlot *slots,size_t count,GuardProtect protect){
    for(size_t i=0;i<count;i++){
        if(!write_slot(&slots[i],slots[i].replacement,protect)){
            /* Include the current slot: its pointer may already have changed. */
            guard_restore_slots(slots,i+1,protect);
            return 0;
        }
    }
    return 1;
}
