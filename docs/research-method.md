# Research method and evidence

This case study combines incident response, Android recovery and a separate runtime-modification experiment on one family-owned X96Q. The contributions are the observations and implementation for this device, not discovery of Katana or invention of early-return ad patches. The published source and extracts allow partial reproduction; private captures and omitted third-party artifacts limit what a reader can independently verify.

## Questions, observations, conclusions

| Question | Evidence used | Supported conclusion and limit |
|---|---|---|
| Was the TV box contributing to congestion? | Two interface-counter samples; Android historical per-UID totals | Heavy outbound traffic came from the box, with two packages dominating historical totals. No packet capture establishes the attack target or contents. |
| Was this known malware? | Ten embedded executables matched the published Katana hash set | Exact payload matches support the Katana identification. A separate Aisuru key-string match supports a family association, not operator attribution. |
| Did removing apps cover all relevant paths? | Later discovery of a watchdog and ELF on `/Reserve0` | The first cleanup missed artifacts outside app data. Neither active execution of those remnants nor firmware integrity was established. |
| Could a mobile YouTube patch be reused? | Android entry-point and DEX inspection; mobile fingerprints absent; Cobalt bridge present | Mobile patch assumptions did not identify this TV client's video-ad path. Fingerprint absence alone is not proof that a path does not exist. |
| Where did this TV player initialise ads? | Captured runtime source, module registration and loader inspection; observed native source-copy call site | One exact downloaded player had a narrowly identified loader. A full-file digest, length, offset and expected statement bind the modification to that observation. |
| Did the guard run without instrumentation? | Two release-build cold starts and a post-reboot native-log excerpt | The deployed shim reported applying the pin and restoring six imports. These logs do not establish race freedom or successful recovery from every protection failure. |
| Did it suppress an ad? | Original app showed a pre-roll; patched app showed documentary frames in a 32-second sample | A limited comparison supports feasibility. Session/profile differences and variable ad inventory prevent a general effectiveness claim. |

See [incident findings](incident.md), [recovery](recovery.md), and the [ad-guard mechanism and tests](../ad-guard/README.md) for details and source hashes.

## Approaches that did not establish a target

The names `loadAd` and ad-related telemetry were insufficient evidence: inspected Java candidates belonged to a generic rewarded-ad SDK, not a demonstrated TV pre-roll path. Rather than patch those candidates, the investigation followed the Activity into Cobalt and then traced the downloaded player.

Tool limitations also constrained the result. The Android decompiler provider lacked its configured JADX dependency, and full native/JavaScript analysis attempts did not complete. SDK DEX inspection, ARM disassembly, targeted parsing and runtime observations supplied narrower evidence. No completed whole-program call graph is claimed.

## Reproduction levels

1. **Without private inputs:** run the eight host ad-guard tests, inspect the C implementation and source pin, and run the launcher's pure-Java model tests. These check algorithms, rejection paths and controlled slot failures; they do not reproduce playback.
2. **With the exact player capture:** run four additional source-patch tests, including isolation of the changed statement and the expected output digest. The capture is withheld third-party code.
3. **With the exact APK, device link libraries and matching toolchain:** rebuild the shim and compare its full digest with the deployed digest. The unsigned APK repeatability check is separate from signed APK identity.
4. **On matching hardware:** verify launcher remote behaviour, reboot recovery, guard logs and playback. Published screenshots and redacted logs are historical evidence, not a substitute for repeating those experiments.

No raw household logs, guest profiles, signing material or malware samples are needed for the public host tests. No malware execution is required.

## Decisions and residual risks

- Preserve the original YouTube installation and its data for rollback; test the separately signed package before changing Home's target.
- Keep module lifecycle bookkeeping and modify one equal-length statement. Refuse an unknown source rather than infer a new patch from similar text.
- Remove temporary instrumentation from the everyday installation. This reduces runtime dependencies; it does not make the shim risk-free.
- Treat disabled update sources as an owner-maintained configuration choice, not a security improvement in themselves. They do not freeze server-delivered player code.
- Keep the accessibility product distinct from the experiment: Arabic TV Home defaults to stock YouTube and works without the guard.

## What would strengthen the evidence next

These are proposed experiments, not completed results: repeat ad comparisons across multiple sessions with better control of guest state; test mid-roll behaviour and extended playback; inject sustained restoration failures; exercise concurrent source-copy calls on ARM; and measure launch latency before claiming a performance benefit. A trusted firmware recovery and an in-room usability check remain separate unresolved questions.
