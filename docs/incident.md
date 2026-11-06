# X96Q incident findings (2026-10-24, follow-up 2026-11-06)

This is a sanitised write-up of the investigation of one X96Q Android TV box on a home network. LAN addresses, hardware addresses, remote endpoints, raw logs and the preserved malware samples are not published. Public indicator hashes are included so others can check their own devices.

**Scope.** These findings are about one client device. They are not evidence of a compromised router, of stolen household credentials, or of other devices on the network being affected; those questions were not tested.

## How it was noticed

The household connection was congested. Two direct reads of the box's `wlan0` counters, 18.6 seconds apart, measured about **27 Mbit/s transmitted** and about 0.013 Mbit/s received, from a TV box that should mostly download. Interface counters are not ISP accounting, and not every transmitted byte necessarily left the house.

## Findings

### 1. Unauthenticated network ADB gave a shell (high)

A TCP-connect scan of 200 common ports on the box found only TCP 5555 open. The ADB service answered a plain `CNXN` handshake as model X96Q and accepted shell commands with **no authentication, key or pairing**. The shell ran as `uid=2000(shell)`. During the later authorised cleanup, the firmware's own `/system/xbin/su 0 id` returned `uid=0(root)`; no exploit or root tool was installed. A fresh demonstration with a newly generated marker confirmed live command execution, not replayed output.

Build properties report Android 10, security patch 2019-12-05, `userdebug`/`test-keys`, `ro.debuggable=1`, `ro.adb.secure=0`. "Manufacturer: Google" is a self-reported property and was not taken as proof of a genuine or certified Google build. The ADB service answered on 5555 while `service.adb.tcp.port` read 12341; the reason was not established.

### 2. Installed Katana botnet payloads (confirmed, high)

`com.system.update` was installed and running several native `libupdate.so` processes. Its APK (SHA-256 `4c480c6c8699218b3ee046159069f35aff9b441ba56134ef8627e29489e8d1fe`) differs from the published wrapper. However, **all ten embedded executable assets match hashes in Nokia Deepfield's Katana indicator set**: ARM/x86 bot payloads, rootkit-related compiler and loader assets, and TinyCC components ([indicators](https://github.com/deepfield/public-research/blob/main/katana/iocs/hashes.csv), [report](https://github.com/deepfield/public-research/blob/main/katana/report.md)).

The APK's DEX strings also contain uninstall-defence and firmware/system persistence routines. These are static capabilities. Neither successful privilege escalation nor a loaded kernel rootkit was demonstrated. A live socket from that package's UID to a remote TCP 6969 endpoint was observed. That is consistent with the campaign's reported protocol, but it is not an exact match to a published IP. The investigator never contacted the remote endpoint.

### 3. Which packages sent the traffic (confirmed)

Android's retained per-UID statistics, covering hourly buckets from 2026-10-23 18:00 to 2026-10-24 02:00 UTC:

| Package | Transmitted | Received | Assessment |
|---|---:|---:|---|
| `com.huawei.qx` | **64,474,165,802 B** | 1,065,550 B | Dominant sender. The package name proves nothing about vendor authenticity. Its APK launches an embedded ARM executable whose family was not resolved. |
| `com.system.update` | **36,852,787,919 B** | 3,670,354 B | The Katana payloads above. |

These are device-reported historical totals, not real-time per-process rates, and not evidence of personal-data exfiltration. The extreme outbound-to-inbound ratio and the verified bot payloads support malicious traffic as the cause of the congestion. Packet payloads and targets were not observed, so no specific attack is claimed.

### 4. Aisuru-consistent executable (high-confidence family association)

`com.android.ota.helper.sync` shipped `libotahelp.so`, which is actually a stripped ARM executable, and several processes with that name were running. The preserved 117,212-byte copy has SHA-256 `610a27ada243e9eab53061065f569b1c58b35c823f77d87b9c12be281095ed79`. Ghidra found the string `PJbiNbbeasddDfsc` at `0x236a4`, which is exactly the generation-two key documented in [Nokia Deepfield's Aisuru research](https://github.com/deepfield/public-research/blob/main/aisuru/README.md). Full decompilation was not completed, so this is a strong family association, not a full attribution.

### 5. Follow-up: reserve-partition remnants (2026-11-06)

Two weeks after the cleanup, a startup review found two files outside the app-data paths checked the first time:

- `/Reserve0/.monitor`: a 98-byte shell loop that invokes `/data/data/com.system.update/files/libupdate.so startup` every 60 s.
- `/Reserve0/.update`: a 437,232-byte ARM ELF, SHA-256 `fe9eeb58cc2212fd92f4eb7618b61e70c7b0d51a254c6461dd773f20fa3f70a6`. Its process-protection routine scans `/proc`, exempts the `com.system.update` / `libupdate.so` / rootkit loader / compiler / tcc paths, and guards against uninstall commands.

In context this is a high-confidence malicious association, but the hash does **not** match the ten payloads above, and its variant and provenance are not established. **No running copy and no startup hook were observed.** A bounded text scan of `/system/etc`, `/vendor/etc` and `/product/etc` found no reference to it, and the app it calls had already been removed. Finding these remnants does not show that they were executing. Both files were copied, hash-verified, removed from the device, and stayed absent after a reboot.

## What was not established

- **How the box was infected.** Package timestamps are device-reported and the clock was wrong. A supply-chain compromise, sideloading and later exploitation all remain possible.
- **Firmware integrity.** No factory reset, reflash, memory acquisition or physical-storage forensics was done. The persistence code means a reset is not established remediation either. The box was cleaned, not certified.
- **BADBOX.** The model has been associated with BADBOX in public reporting. That is background only: the demonstrated payload match here is Katana, plus an Aisuru-consistent executable.
- Full native unpacking and full APK decompilation were not completed.

## Method notes

- Collectors used direct ADB protocol frames with fixed command sets and bounded output and time. They pinned the target to the known hardware address and model, and installed no key, agent or local adb server. These collectors are not published because they contain environment-specific assumptions and have not been prepared or reviewed as reusable tooling.
- Collected executables were never run on the investigator's machine. Analysis was static: Ghidra, ZIP inventory and inert DEX string parsing.
- Personal app content, account stores, passwords, messages, photos and app databases were not collected.
