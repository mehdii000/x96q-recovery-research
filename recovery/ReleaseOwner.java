package local.reroute.maintenance;

import android.app.admin.DevicePolicyManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.pm.PackageManager;
import android.os.Looper;

/** One-time owner-requested release of the vendor device owner, using normal APIs. */
public final class ReleaseOwner {
    public static void main(String[] args) throws Exception {
        if (android.os.Process.myUid() != 1000) throw new SecurityException("System UID required");
        final String owner = "com.easycontrol.mdm";
        if (Looper.myLooper() == null) Looper.prepareMainLooper();
        Class<?> activityThread = Class.forName("android.app.ActivityThread");
        Object thread = activityThread.getDeclaredMethod("systemMain").invoke(null);
        Context system = (Context) activityThread.getDeclaredMethod("getSystemContext").invoke(thread);
        Context context = system.createPackageContext(owner, 0);
        if (context.getPackageManager().getApplicationInfo(owner, 0).uid != 1000)
            throw new SecurityException("Unexpected owner UID");
        DevicePolicyManager policy = (DevicePolicyManager) context.getSystemService(Context.DEVICE_POLICY_SERVICE);
        System.out.println("owner_before=" + policy.isDeviceOwnerApp(owner));
        if (args.length == 1 && args[0].equals("release")) {
            try {
                context.getPackageManager().setApplicationEnabledSetting(owner, PackageManager.COMPONENT_ENABLED_STATE_DISABLED_USER, 0);
                System.out.println("disabled_before_release=true");
            } catch (SecurityException guarded) {
                System.out.println("disabled_before_release=false");
            }
            if (policy.isDeviceOwnerApp(owner)) policy.clearDeviceOwnerApp(owner);
            context.getPackageManager().setApplicationEnabledSetting(owner, PackageManager.COMPONENT_ENABLED_STATE_DISABLED_USER, 0);
            policy.removeActiveAdmin(new ComponentName(owner, "com.easycontrol.mdm.receiver.DeviceOwnerReceiver"));
        }
        System.out.println("owner_after=" + policy.isDeviceOwnerApp(owner));
        System.out.println("enabled_state=" + context.getPackageManager().getApplicationEnabledSetting(owner));
    }
}
