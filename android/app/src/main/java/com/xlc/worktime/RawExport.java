package com.xlc.worktime;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.List;

/**
 * Builds the cross-platform "worktime-raw" v1 export (see docs/PLATFORMS.md).
 * The desktop app imports it with: wt import-raw --file raw.json
 */
public final class RawExport {

    public static final String FORMAT = "worktime-raw";
    public static final int VERSION = 1;

    private RawExport() {}

    public static String build(Db db, String deviceId, String deviceName, String date)
            throws Exception {
        JSONObject root = new JSONObject();
        root.put("format", FORMAT);
        root.put("version", VERSION);
        root.put("platform", "android");
        JSONObject device = new JSONObject();
        device.put("id", deviceId);
        device.put("name", deviceName);
        root.put("device", device);
        root.put("exported_at", nowStamp());

        List<Db.Row> rows = db.rowsForDay(date);
        JSONArray activity = new JSONArray();
        for (Db.Row row : rows) {
            JSONObject item = new JSONObject();
            item.put("ts", row.ts);
            item.put("app", row.app == null ? "" : row.app);
            item.put("proc", row.proc == null ? "" : row.proc);
            item.put("title", row.title == null ? "" : row.title);
            item.put("pid", 0);
            item.put("idle_sec", 0);
            item.put("screen", "active");
            activity.put(item);
        }
        JSONObject day = new JSONObject();
        day.put("activity", activity);
        day.put("focus", new JSONArray());
        JSONObject days = new JSONObject();
        days.put(date, day);
        root.put("days", days);
        return root.toString(1);
    }

    private static String nowStamp() {
        return java.time.LocalDateTime.now()
                .format(java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss"));
    }
}
