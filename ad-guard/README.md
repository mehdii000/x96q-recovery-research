# Video-ad loader guard (experimental)

A 9 KB native shim that makes **one specific build** of YouTube for Android TV (2.07.02, 32-bit ARM, as installed on one X96Q) return early from its video-ad loader. It follows the same idea as ReVanced-style patches: find the method that sets up ads and return before it does any work. Here, though, the target is JavaScript that the Cobalt engine copies at runtime, not Dalvik bytecode. It contains no ReVanced code.

> **This is device- and version-specific research, not an ad blocker.** It applies only when every pinned hash matches. Unrecognised source is left unmodified. That does not prove that the native interception has no overhead or failure modes. It has been tested on one box, with one real before/after comparison. It does not touch feed ads, sponsorships inside videos, or server-stitched ads, and it is not claimed to speed anything up. YouTube can change the downloaded player at any time, and this guard will then silently stop matching.

## How it works

YouTube TV is a thin Android wrapper around **Cobalt**, a native engine (`libcoat.so`, about 26 MB) that downloads and runs the TV web app.

1. **Find the target.** Temporary, loopback-only Frida instrumentation on the owner's box captured the exact player source that Cobalt copies into memory: 2,272,858 bytes, SHA-256 `c135f6c2…afff`. In it, `m6("ad",u2a)` registers the `ad` module, and `u2a.load()` calls `G()`. `G()` first calls `super.load()` for module bookkeeping. It then reads ad placements and ad slots from the player response and initialises the ad manager.
2. **Choose the smallest patch.** The guard keeps `super.load()` and replaces the next statement, `var a=i9(this.j).rf;` (20 bytes), with `return;` padded with spaces to the same length. Nothing else in the file changes. The full file digest after patching is pinned too (`bdacc50a…c0c3f8`).
3. **Find where to apply it.** Inside the real process, the source copy came from one call site in the engine, at offset `0x814a6c` from its load base. This was observed before any shim was written.
4. **Ship it without Frida.** The build renames the original `libcoat.so` to `libcobalt.so`, byte-for-byte unchanged, and puts a small shim in its place:
   - The shim forwards `ANativeActivity_onCreate` to the real engine.
   - At load time, it walks the engine's own PLT relocations and redirects only the engine's `memcpy`/`memmove` imports (six slots on this build) to wrappers.
   - Each wrapper performs the real copy. It then checks that it was called from `0x814a6c` with exactly the pinned length.
   - It hashes the whole buffer and checks the 20 expected bytes. Only if everything matches does it write the replacement.
   - After the first copy matching the call site and length, it attempts to restore all six original imports, whether the digest matched or not. Successful restoration is logged. If the source length changes, this boundary is not accepted and the forwarding wrappers remain until process exit.
   - If installing an import fails, it attempts rollback of every touched slot, including a partially written one, and disables further patch attempts. Restoration is best effort: repeated `mprotect` failure can leave a wrapper installed or a page writable. The installation-failure log does not independently prove successful rollback.
5. **Install beside the original.** The package is renamed to `com.google.android.youtube.tx` with a same-length binary substitution and signed with your own key, so it installs next to the stock app instead of replacing it.

There is no Frida, root, proxy, DNS filter, background service or host computer involved at runtime. The APK requests no new permissions.

| File | Role |
|---|---|
| `loader.c` | engine discovery, import redirection, call-site filter, restore, Activity forwarding |
| `ad_patch.c` | freestanding SHA-256, exact-source check and same-length patch, boundary check |
| `slots.c` | import-slot install/restore with page protection and rollback |
| `patch_config.h` | the pinned length, offset, digest and 20 original/replacement bytes |
| `source-pin.json` | the same pins plus the surrounding identifiers, for review |
| `build.py` | builds the APK from inputs you supply and verifies that only three entries changed |

## What you need

Nothing from Google is distributed here. You supply:

- **The original APK**: YouTube for Android TV 2.07.02 from your own device. `build.py` rejects anything whose SHA-256 is not `0cb978cccf1f4d1da60d5957a0f5891a10972395d31c69e7420d49ffb5ac0232`.
  ```sh
  adb shell pm path com.google.android.youtube.tv
  adb pull <that path> YouTubeTV-2.07.02.apk
  ```
- **Link inputs**: 32-bit ARM `libc.so`, `libdl.so` and `liblog.so`. The recorded build used libraries pulled from the same device's `/system/lib`. NDK sysroot stubs for `arm-linux-androideabi` API 21 may also work, but that alternative was not validated here and is not covered by the deployed-shim hash claim. They are only linked against and are not packaged.
- **Tools:**
  - `clang` and `lld` with the ARM target (stock LLVM works; the NDK is not required);
  - `readelf`;
  - Python 3;
  - a JDK for `keytool`;
  - Android SDK `build-tools;36.0.0`.

## Build

```sh
python3 -B build.py --original-apk YouTubeTV-2.07.02.apk --android-libs path/to/arm-libs
# optional: --keystore KS --ks-pass-file FILE --key-alias ALIAS
```

The result is `build/youtube-tv-video-ad-guard-research.apk`, with `build/build-manifest.json` recording every changed entry's before and after digest. The build stops if:

- the APK or engine digest differs from the pin;
- the package rename changes a binary size;
- any of the other 1,586 entries differs from the original;
- the engine bytes change;
- the result fails `apksigner verify` or `zipalign -c`.

**Reproducibility.** With the recorded LLVM toolchain and the same device-library inputs, the shim is byte-identical to the one deployed on the owner's box: 9,328 bytes, SHA-256 `280da8c8ac2a50273d697640dde3582708f700f96995d16ac5b2bd6f69763d76`. Every APK entry matches the deployed APK's contents. Two consecutive builds from this repository produce identical unsigned APKs. This does not promise identical signed APK bytes: the key and ZIP metadata also affect the container.

`--diagnostic` builds an investigation variant. It logs every large copy with its call-site offset and saves the first candidate player source to the app's cache directory. This is a discovery aid, not a reliable capture of the pinned file: the published log shows a 2,093,447-byte diagnostic candidate, distinct from the 2,272,858-byte pinned source observed through instrumentation. A new capture must be traced and reviewed before changing any pin. Do not install a diagnostic build for everyday use, and delete the captured file afterwards.

## Tests

```sh
python3 -B -m unittest discover -s tests -v
AD_GUARD_PLAYER_SOURCE=/path/to/captured-player.js python3 -B -m unittest discover -s tests -v
```

There are 12 tests. Eight run anywhere with a C compiler:

- SHA-256 against Python's for standard vectors and every padding boundary;
- `patch_config.h` consistent with `source-pin.json`;
- right length and statement but wrong digest leaves the buffer untouched;
- empty and short inputs are untouched;
- only the exact call site and length pass the boundary filter;
- three import-slot tests: install then restore, rollback when the page-protection restore fails, and rollback of earlier slots when a later slot fails.

The other four need the captured player source, which is Google's code and is not included. They are reported as skipped without it:

- the exact player changes only the reviewed statement, and the result matches the pinned digest;
- a one-byte change elsewhere is left untouched;
- truncated input is left untouched;
- an already-patched file is left untouched.

On 2026-11-06, all 12 passed against the original capture.

## Evidence from the real box

| Check | Result |
|---|---|
| Frida prototype (temporary, removed afterwards) | Exact original and modified source digests verified in the running app. A recommended video played with the modified player. |
| Clean release build, two cold starts | `Applied pinned video-ad loader early return` and `Restored all 6 native imports`; media session `PLAYING`. See the [log excerpt](../docs/evidence/ad-guard-native-log.txt). |
| Before/after on the same video | Same public Nat Geo Abu Dhabi documentary (`3vnIT4Efi4c`). The original app showed a Ferrero Rocher pre-roll with a skip countdown. The patched app showed advancing documentary frames and **no video ad during 32 sampled seconds**. |
| After a real reboot, launched from Arabic Home | Patch applied, imports restored, guest feed present, playback reached `PLAYING`. Initial black and buffering frames were observed. |
| Package integrity | Original engine bytes unchanged; 1,586 unrelated entries unchanged; new signer verifies; alignment verifies; installed hash matches the built artifact. |

One comparison is an anecdote, not a measurement. Ad delivery varies by session and profile. Mid-rolls, server-stitched ads and other player versions were not tested.

## Review status

A separate AI-agent review was started but **not completed**: the reviewer hit a usage limit. It produced two findings, and both were fixed before the hardware verification:

1. **Partial-hook bookkeeping.** Import slots are now collected before any mutation, and rollback includes the slot that was being written when a failure happened. The protection-failure regression tests failed before the fix and pass after it.
2. **`dlsym(NULL, …)` on 32-bit Android.** `memcpy` and `memmove` are now resolved through an explicit `dlopen("libc.so")` handle.

The author then reviewed the rest: ARM wrapper and call-site ABI, dynamic imports, source pin, slot rollback, native logs, and the package change manifest. **There is no complete independent sign-off.** Treat this as research code.

## Limits, plainly

- One device, one APK build, one player version. The pins are deliberately strict: a new player version means no patch, not a guess.
- It suppresses ad *initialisation* in one module of the TV player. Feed ads, in-video sponsorships and server-side ad insertion are out of scope.
- No measured startup or buffering improvement.
- Android package controls can stop *app* updates, but not the player JavaScript YouTube serves at runtime.
- Using a modified client may conflict with YouTube's Terms of Service. This repository documents what was done on one family device. It does not distribute a patched app, and it is not intended to be used as a product.
