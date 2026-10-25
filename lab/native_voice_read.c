/* Test-side batching of the unchanged public native peek ABI. Read-only. */
#include <stdint.h>
typedef int64_t (*peek_fn)(void *, uint64_t, uint32_t);
int read_voice_words(uintptr_t address, void *engine, uint64_t base,
                     uint32_t stride, uint32_t offset, uint32_t lanes,
                     uint32_t words, uint32_t *out) {
    peek_fn peek=(peek_fn)address;
    uint32_t lane,i;
    for(lane=0;lane<lanes;lane++) for(i=0;i<words;i++) {
        int64_t value=peek(engine,base+lane*stride+offset+i*4u,4);
        if(value<0 || !((uint64_t)value>>32)) return -1;
        *out++=(uint32_t)value;
    }
    return 0;
}
