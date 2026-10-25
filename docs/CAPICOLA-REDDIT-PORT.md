# Author release STRETCH replacement

Revision: 1
Status: approved; selected architecture: direct source integration.
User approval: "Yes, let’s do that. Wire his up and replace the existing one."

Replace the existing CAPI STRETCH backend with hy3na-k1ng's shared release-default engine. Use the supplied ZIP as authority, not an inferred generic Capicola revision. Retain exact originals and AGPL attribution. Preserve CC_CLEAN, GEN_BLEND_FIXED=0.0f, GEN_BLEND_ZERO, GEN_WSOLA, GEN_BUILD=0, stereo pairing, Catmull-Rom PCM read, 640-sample leash/crossfade, original search and one-search-per-frame scheduling, retrigger correction and SHARC SIMD/fast paths. No fidelity tradeoff for performance.

Adapt only target memory placement, existing binary CAPI transport/status, and STRETCH dispatch. Combine author hot L1 and cold L2 code with existing Plaits source hook. Keep voice state in a disjoint L2 window at 0x200e0000; reserve ring state in our existing 8 MiB sample carve-out, leaving Plaits constants/stacks/lane state intact. Do not add author's REPITCH/GRID/SLICE/BARS or OS1.17 controls. OFF executes stock STRETCH; ON adopts author's native block-switch semantics. Existing CPU image with binary icon, native Arp, managed Flex is preserved byte-for-byte.

Oracle: unchanged author host generator and all 14 published golden replays; relocated target/native PCM compared with identical input and event records, max1e-4 RMS1e-5 (stock OFF exact). Cover stereo, reverse/loop, pitch/time rates, retrigger, source changes, panel transport, all-feature protected sections and repeat builds. Capture final output and causal custom mute where feasible; report actual evidence separately. Golden tests are not proof of physical timing or listening quality.

Deliver source adapter, pinned original files/license, reproducible all-feature OS1.16 SYX, comparison reports and reproduction commands. Required lab source suite, SINE replay, target layout/link guards and upload depacker/startup checks. No dependency update, hardware upload, commit, push or publication.

Risks: target memory ownership/timing on physical device remains unverified; host-to-target compiler numeric differences require measured tolerances. Failed equivalence must be fixed or reported, never hidden by lowering quality or changing the oracle. Old artifacts and explicit legacy build modes remain reproducible.
