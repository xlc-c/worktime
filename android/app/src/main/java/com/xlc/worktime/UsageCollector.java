package com.xlc.worktime;

import android.app.AppOpsManager;
import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.os.PowerManager;
import android.util.Log;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;

/** Polls UsageStatsManager for foreground-app switches (no accessibility needed). */
public final class UsageCollector {

    private static final String TAG = "WorkTime";
    private static final DateTimeFormatter STAMP =
            DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss");
    private static final long WINDOW_MS = 15 * 60 * 1000L;

    private UsageCollector() {}

    public static boolean hasUsageAccess(Context context) {
        AppOpsManager appOps = (AppOpsManager) context.getSystemService(Context.APP_OPS_SERVICE);
        if (appOps == null) return false;
        int mode = appOps.checkOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS,
                android.os.Process.myUid(), context.getPackageName());
        return mode == AppOpsManager.MODE_ALLOWED;
    }

    /**
     * Read new foreground events since the last poll and write them as raw rows.
     * Also writes a heartbeat row for the current app so long sessions still
     * produce a dense enough timeline.
     */
    public static int poll(Context context, Db db) {
        if (db.isPaused()) return 0;
        PowerManager pm = (PowerManager) context.getSystemService(Context.POWER_SERVICE);
        if (pm != null && !pm.isInteractive()) {
            db.setMeta("collector.last_poll", nowStamp());
            return 0;
        }

        long now = System.currentTimeMillis();
        long begin = now - WINDOW_MS;
        String lastPoll = db.getMeta("collector.last_poll", "");
        if (!lastPoll.isEmpty()) {
            try {
                long parsed = LocalDateTime.parse(lastPoll).atZone(ZoneId.systemDefault())
                        .toInstant().toEpochMilli();
                if (parsed > 0 && now - parsed < WINDOW_MS) {
                    begin = Math.max(begin, parsed);
                }
            } catch (Exception ignored) {
                // keep the default window
            }
        }

        android.app.usage.UsageStatsManager usm =
                (android.app.usage.UsageStatsManager)
                        context.getSystemService(Context.USAGE_STATS_SERVICE);
        if (usm == null) return 0;

        android.app.usage.UsageEvents events = usm.queryEvents(begin, now);
        android.app.usage.UsageEvents.Event event = new android.app.usage.UsageEvents.Event();
        int written = 0;
        String currentPackage = db.getMeta("collector.foreground", "");
        while (events != null && events.hasNextEvent()) {
            events.getNextEvent(event);
            int type = event.getEventType();
            boolean foreground = type == android.app.usage.UsageEvents.Event.ACTIVITY_RESUMED;
            if (!foreground) continue;
            currentPackage = event.getPackageName();
            db.insertRaw(stamp(event.getTimeStamp()), label(context, currentPackage),
                    currentPackage, "", 0, 0, "active");
            written++;
            db.setMeta("collector.foreground", currentPackage == null ? "" : currentPackage);
        }

        if (currentPackage != null && !currentPackage.isEmpty()) {
            db.insertRaw(nowStamp(), label(context, currentPackage), currentPackage, "",
                    0, 0, "active");
            written++;
        }
        db.setMeta("collector.last_poll", nowStamp());
        if (written > 0) Log.d(TAG, "captured " + written + " rows");
        return written;
    }

    public static String label(Context context, String packageName) {
        if (packageName == null || packageName.isEmpty()) return "unknown";
        try {
            PackageManager pm = context.getPackageManager();
            ApplicationInfo info = pm.getApplicationInfo(packageName, 0);
            CharSequence name = pm.getApplicationLabel(info);
            return name == null ? packageName : name.toString();
        } catch (Exception exc) {
            return packageName;
        }
    }

    private static String stamp(long millis) {
        return LocalDateTime.ofInstant(Instant.ofEpochMilli(millis), ZoneId.systemDefault())
                .format(STAMP);
    }

    private static String nowStamp() {
        return LocalDateTime.now().format(STAMP);
    }
}
