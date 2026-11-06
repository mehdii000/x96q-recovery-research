#include "ad_patch.h"
#include "slots.h"

/* The shim is freestanding ARM C; these are the Android API 21 ABI fields used. */
typedef unsigned int u32;
typedef unsigned short u16;
typedef struct { u32 type,offset,vaddr,paddr,filesz,memsz,flags,align; } Phdr;
typedef struct { int tag; u32 value; } Dyn;
typedef struct { u32 offset,info; } Rel;
typedef struct { u32 name,value,size; unsigned char info,other; u16 section; } Sym;
typedef struct { size_t base; const char *name; const Phdr *headers; u16 count; } DlInfo;
extern int dl_iterate_phdr(int (*)(DlInfo *,size_t,void *),void *);
extern void *dlopen(const char *,int);
extern void *dlsym(void *,const char *);
extern int mprotect(void *,size_t,int);
extern int __android_log_print(int,const char *,const char *,...);

typedef void *(*Copy)(void *,const void *,size_t);
static GuardSlot hooks[16];
static unsigned hook_count;
static size_t engine_base,relro_begin,relro_end;
static Copy real_copy,real_move;
static int finished;
#ifdef GUARD_DIAGNOSTIC
extern int open(const char *,int,...);
extern int write(int,const void *,unsigned);
extern int close(int);
static unsigned diagnostic_count;
static int diagnostic_captured;
static int contains(const unsigned char *data,size_t length,const char *needle){
    size_t n=0;while(needle[n])n++;
    for(size_t i=0;n<=length&&i<=length-n;i++){
        size_t j=0;while(j<n&&data[i+j]==(unsigned char)needle[j])j++;
        if(j==n)return 1;
    }
    return 0;
}
static void diagnose_copy(void *dest,size_t length,size_t caller){
    if(length<1000000)return;
    if(__atomic_fetch_add(&diagnostic_count,1,__ATOMIC_RELAXED)<8)
        __android_log_print(4,"ReRouteAdGuard","Copy size=%u caller offset=%x",(unsigned)length,(unsigned)(caller-engine_base));
    if(length<2000000||length>8000000||diagnostic_captured)return;
    const unsigned char *data=dest;
    if(!contains(data,length,"ad-created")||!contains(data,length,".adPlacements")||!contains(data,length,".adSlots"))return;
    if(__atomic_exchange_n(&diagnostic_captured,1,__ATOMIC_ACQ_REL))return;
    int fd=open("/data/data/com.google.android.youtube.tx/cache/reroute-player-source.js",0x241,0600);
    if(fd<0)return;
    size_t at=0;while(at<length){int n=write(fd,data+at,(unsigned)(length-at));if(n<=0)break;at+=(unsigned)n;}
    close(fd);
    __android_log_print(4,"ReRouteAdGuard","Captured diagnostic player source %u/%u bytes",(unsigned)at,(unsigned)length);
}
#endif

static int equal(const char *a,const char *b){while(*a&&*a==*b){a++;b++;}return *a==*b;}
static int suffix(const char *s,const char *tail){
    size_t a=0,b=0;while(s[a])a++;while(tail[b])b++;
    return a>=b&&equal(s+a-b,tail);
}
static size_t pointer_value(size_t value){return value<engine_base?engine_base+value:value;}
static void restore_hooks(void){
    int restored=guard_restore_slots(hooks,hook_count,mprotect);
    __android_log_print(restored?4:6,"ReRouteAdGuard",restored?"Restored all %u native imports":"Native import restoration failed (%u retained records)",hook_count);
}
static void after_copy(void *dest,size_t length,size_t caller){
#ifdef GUARD_DIAGNOSTIC
    diagnose_copy(dest,length,caller);
#endif
    if(__atomic_load_n(&finished,__ATOMIC_ACQUIRE)||!guard_boundary(caller,engine_base,length))return;
    /* Only one thread owns the checked source-copy boundary. */
    if(__atomic_exchange_n(&finished,1,__ATOMIC_ACQ_REL))return;
    int patched=guard_patch(dest,length);
    __android_log_print(4,"ReRouteAdGuard",patched?"Applied pinned video-ad loader early return":"Unknown player source; left unchanged");
    restore_hooks();
}
static __attribute__((noinline)) void *copy_wrapper(void *dest,const void *src,size_t length){
    size_t caller=(size_t)__builtin_return_address(0);
    void *result=real_copy(dest,src,length);
    after_copy(dest,length,caller);
    return result;
}
static __attribute__((noinline)) void *move_wrapper(void *dest,const void *src,size_t length){
    size_t caller=(size_t)__builtin_return_address(0);
    void *result=real_move(dest,src,length);
    after_copy(dest,length,caller);
    return result;
}
static int inspect_engine(DlInfo *info,size_t info_size,void *unused){
    (void)info_size;(void)unused;
    if(!info->name||!suffix(info->name,"libcobalt.so"))return 0;
    engine_base=info->base;
    const Dyn *dynamic=0;
    for(unsigned i=0;i<info->count;i++){
        const Phdr *p=&info->headers[i];
        if(p->type==2)dynamic=(const Dyn *)(engine_base+p->vaddr);
        if(p->type==0x6474e552u){
            relro_begin=(engine_base+p->vaddr)&~(size_t)4095;
            relro_end=(engine_base+p->vaddr+p->memsz+4095)&~(size_t)4095;
        }
    }
    if(!dynamic)return 1;
    const Sym *symbols=0;const char *strings=0;const Rel *relocations=0;
    size_t bytes=0;int format=0;
    for(unsigned i=0;i<128&&dynamic[i].tag;i++){
        switch(dynamic[i].tag){
            case 6:symbols=(const Sym *)pointer_value(dynamic[i].value);break;
            case 5:strings=(const char *)pointer_value(dynamic[i].value);break;
            case 23:relocations=(const Rel *)pointer_value(dynamic[i].value);break;
            case 2:bytes=dynamic[i].value;break;
            case 20:format=(int)dynamic[i].value;break;
        }
    }
    if(!symbols||!strings||!relocations||format!=17||bytes>1024*1024)return 1;
    for(size_t i=0;i<bytes/sizeof(Rel)&&hook_count<16;i++){
        const Rel *r=&relocations[i];if((r->info&255)!=22)continue;
        const char *name=strings+symbols[r->info>>8].name;
        int copy=equal(name,"memcpy")||equal(name,"__aeabi_memcpy")||equal(name,"__aeabi_memcpy4")||equal(name,"__aeabi_memcpy8");
        int move=equal(name,"memmove")||equal(name,"__aeabi_memmove")||equal(name,"__aeabi_memmove4")||equal(name,"__aeabi_memmove8");
        if(!copy&&!move)continue;
        GuardSlot *h=&hooks[hook_count++];h->slot=(void **)(engine_base+r->offset);h->original=*h->slot;
        h->replacement=copy?(void *)copy_wrapper:(void *)move_wrapper;
        h->protection=(size_t)h->slot>=relro_begin&&(size_t)h->slot<relro_end?1:3;
    }
    if(!guard_install_slots(hooks,hook_count,mprotect)){
        __atomic_store_n(&finished,1,__ATOMIC_RELEASE);
        __android_log_print(6,"ReRouteAdGuard","Import installation failed; rolled back and disabled guard");
        return 1;
    }
    __android_log_print(4,"ReRouteAdGuard","Watching source boundary with %u native imports",hook_count);
    return 1;
}
__attribute__((constructor)) static void initialize(void){
    void *libc=dlopen("libc.so",2);
    real_copy=libc?(Copy)dlsym(libc,"memcpy"):0;
    real_move=libc?(Copy)dlsym(libc,"memmove"):0;
    if(real_copy&&real_move)dl_iterate_phdr(inspect_engine,0);
    else __android_log_print(6,"ReRouteAdGuard","Could not resolve Android copy functions; guard inactive");
}
__attribute__((visibility("default"))) void ANativeActivity_onCreate(void *activity,void *saved,size_t size){
    typedef void (*Start)(void *,void *,size_t);
    void *library=dlopen("libcobalt.so",2);
    Start start=library?(Start)dlsym(library,"ANativeActivity_onCreate"):0;
    if(start)start(activity,saved,size);
    else __android_log_print(6,"ReRouteAdGuard","Could not forward Cobalt Activity entry");
}
