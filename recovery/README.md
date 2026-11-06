# Releasing a vendor device-owner app

`ReleaseOwner.java` is the one-off helper used to release the X96Q's vendor MDM, `com.easycontrol.mdm`, which was registered as Android **device owner**. While it is device owner, it can re-enable itself and enforce policy. `pm disable-user` and `dpm remove-active-admin` run from a shell were refused or did not hold.

The policy operations use public `DevicePolicyManager` APIs; obtaining the system context uses reflective access to hidden `ActivityThread` methods and depends on this firmware. It runs as the system UID through `app_process`, in the MDM package's own context, and does:

1. `inspect`: prints whether the package is device owner. This is the default.
2. `release`:
   - disable the package for user 0;
   - `clearDeviceOwnerApp`;
   - disable it again;
   - `removeActiveAdmin` for its receiver;
   - print the final state.

The order matters. On this box, releasing ownership while the package was still enabled let management come back. Disabling first made the release hold across restarts. The package was later removed for user 0 entirely.

## How it was run

The box's firmware ships a world-usable `/system/xbin/su`, so system UID was reachable without installing anything:

```sh
javac -source 8 -target 8 -bootclasspath $ANDROID_HOME/platforms/android-36/android.jar -d out ReleaseOwner.java
$ANDROID_HOME/build-tools/36.0.0/d8 --lib $ANDROID_HOME/platforms/android-36/android.jar --min-api 21 --output out out/local/reroute/maintenance/*.class
adb push out/classes.dex /data/local/tmp/owner-release.dex
adb shell "/system/xbin/su 1000 sh -c 'CLASSPATH=/data/local/tmp/owner-release.dex app_process /system/bin local.reroute.maintenance.ReleaseOwner inspect'"
# … then the same with `release`, then:
adb shell rm /data/local/tmp/owner-release.dex
```

The helper refuses to run unless its UID is 1000 and the target package's UID is 1000.

## Caveats

- The package name and receiver class are hard-coded for this firmware. Read the code before adapting it.
- It only makes sense on a device you own and already control at system level. On a properly secured device you cannot run code as system UID, which is the point.
- Releasing device owner removes whatever the vendor enforced, including anything legitimate. On this box the vendor management came with no documentation and kept restarting.
