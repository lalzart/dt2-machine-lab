# Author CAPI boot-buffer repair

Revision: 1. Approved by user's direct instruction to fix the custom firmware after the reported hardware exception. Lane: source-reimplementation maintenance; uninterrupted repair authorized.

EVIDENCE: failed SYX a70f91d7998253b3baeda919dc2156ec3fd51a4e3532462eb92591913879505a contains a 1,314,460-byte decoded DSP boot stream. Stock OS1.16 CPU code allocates two 0x100000-byte buffers at0x400cd174/0x400cd19e, stores a one-byte boot command at the output start, then calls the MAIN depacker at0x4013815c with output+1. It checks decoded length+1 only after the write, at0x400cd20c. Previous tests executed a different bootstrap depacker into an oversized scratch buffer, and CPU boot used stock section7.

INFERENCE: this definite output-buffer overflow can corrupt CPU heap objects and explains the supplied callback crash. The exact photographed device history is not captured; do not claim an exact device replay.

Selected repair: encode all-zero appended author voice/ring regions as standard ADI BFLAG_FILL blocks. Preserve exact final loaded bytes, all DSP instructions, initial state, CPU MAIN, feature/UI controls and original author source. Add stock-version guarded checks of compressed input <=1MiB and decoded DSP output+boot-command <=1MiB. No CPU buffer enlargement or algorithm/resource-quality change.

Deliverable: separately named EXPERIMENTAL_ALL_FEATURES_CAPI_REDDIT_R2_OS1.16.syx plus reproduction and failure evidence. Retain and mark the original build withdrawn after hardware failure.

Acceptance: execute the actual MAIN depacker on old and new packed section7 streams; old build must cross the true output-allocation boundary and new build must stay inside with intact canaries and exact decoded content. Require exact final loaded memory (including all zero initialization), exact stock/native CPU, old-versus-new native author PCM, 14 host goldens, full stereo/Plaits/final-ring routing, repeat target packaging/startup, source tests and SINE. Device upload, hardware timing/listening, commit, push and publication remain outside this request.

State/control: no algorithmic, UI or state-operation changes. Source authority and licenses remain the pinned supplied archive and original source-port contract. Existing final validation parameters/tolerances remain unchanged. Actual hardware confirmation remains a separate observation after this local repair.
