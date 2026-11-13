package com.xlc.worktime;

import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Local store. The schema mirrors the desktop collector's SQLite schema
 * (raw_activity / focus_events / meta) so an exported database or raw export
 * can be fed into the same segmentation pipeline.
 */
public class Db extends SQLiteOpenHelper {

    public static final String NAME = "worktime.db";
    public static final int VERSION = 1;

    public Db(Context context) {
        super(context, NAME, null, VERSION);
    }

    @Override
    public void onCreate(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE IF NOT EXISTS raw_activity ("
                + "id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, app TEXT,"
                + " proc TEXT, title TEXT, pid INTEGER, idle_sec REAL DEFAULT 0,"
                + " screen TEXT DEFAULT 'active')");
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_raw_ts ON raw_activity(ts)");
        db.execSQL("CREATE TABLE IF NOT EXISTS focus_events ("
                + "id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, app TEXT,"
                + " title TEXT, text_preview TEXT)");
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_focus_ts ON focus_events(ts)");
        db.execSQL("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)");
    }

    @Override
    public void onUpgrade(SQLiteDatabase db, int oldVersion, int newVersion) {
        // Additive migrations only; v1 has a single version.
    }

    public void insertRaw(String ts, String app, String proc, String title,
                          long pid, double idleSeconds, String screen) {
        SQLiteDatabase db = getWritableDatabase();
        db.execSQL("INSERT INTO raw_activity(ts, app, proc, title, pid, idle_sec, screen)"
                        + " VALUES(?,?,?,?,?,?,?)",
                new Object[]{ts, app, proc, title, pid, idleSeconds, screen});
    }

    public void insertFocus(String ts, String app, String title, String textPreview) {
        SQLiteDatabase db = getWritableDatabase();
        db.execSQL("INSERT INTO focus_events(ts, app, title, text_preview) VALUES(?,?,?,?)",
                new Object[]{ts, app, title, textPreview});
    }

    public void setMeta(String key, String value) {
        SQLiteDatabase db = getWritableDatabase();
        // INSERT OR REPLACE: works on the SQLite shipped with Android 8 (26),
        // where UPSERT (ON CONFLICT ... DO UPDATE) is not available yet.
        db.execSQL("INSERT OR REPLACE INTO meta(key, value) VALUES(?,?)",
                new Object[]{key, value});
    }

    public String getMeta(String key, String fallback) {
        SQLiteDatabase db = getReadableDatabase();
        Cursor c = null;
        try {
            c = db.rawQuery("SELECT value FROM meta WHERE key = ?", new String[]{key});
            if (c.moveToFirst()) {
                return c.getString(0);
            }
        } finally {
            if (c != null) c.close();
        }
        return fallback;
    }

    public boolean isPaused() {
        return "1".equals(getMeta("collector.paused", "0"));
    }

    public void setPaused(boolean paused) {
        setMeta("collector.paused", paused ? "1" : "0");
    }

    /** Rows for one day, ordered, for export and usage summaries. */
    public List<Row> rowsForDay(String date) {
        List<Row> rows = new ArrayList<>();
        SQLiteDatabase db = getReadableDatabase();
        Cursor c = null;
        try {
            c = db.rawQuery("SELECT ts, app, proc, title FROM raw_activity"
                    + " WHERE ts >= ? AND ts <= ? ORDER BY ts",
                    new String[]{date + "T00:00:00", date + "T23:59:59"});
            while (c.moveToNext()) {
                rows.add(new Row(c.getString(0), c.getString(1), c.getString(2), c.getString(3)));
            }
        } finally {
            if (c != null) c.close();
        }
        return rows;
    }

    public int rowCountForDay(String date) {
        SQLiteDatabase db = getReadableDatabase();
        Cursor c = null;
        try {
            c = db.rawQuery("SELECT COUNT(*) FROM raw_activity"
                    + " WHERE ts >= ? AND ts <= ?",
                    new String[]{date + "T00:00:00", date + "T23:59:59"});
            if (c.moveToFirst()) return c.getInt(0);
        } finally {
            if (c != null) c.close();
        }
        return 0;
    }

    /**
     * Sum foreground time per app from consecutive samples.
     * A gap longer than {@code capSeconds} is treated as the cap (screen off,
     * service killed, ...), matching the desktop tiling rules.
     */
    public Map<String, Long> usageByApp(String date, long capSeconds) {
        List<Row> rows = rowsForDay(date);
        Map<String, Long> out = new LinkedHashMap<>();
        for (int i = 0; i < rows.size(); i++) {
            Row row = rows.get(i);
            long seconds = 60;
            if (i + 1 < rows.size()) {
                long gap = secondsBetween(row.ts, rows.get(i + 1).ts);
                seconds = Math.max(1, Math.min(gap, capSeconds));
            }
            String key = row.app == null || row.app.isEmpty() ? "unknown" : row.app;
            Long current = out.get(key);
            out.put(key, (current == null ? 0 : current) + seconds);
        }
        return out;
    }

    private static long secondsBetween(String a, String b) {
        try {
            java.time.LocalDateTime ta = java.time.LocalDateTime.parse(a);
            java.time.LocalDateTime tb = java.time.LocalDateTime.parse(b);
            return java.time.Duration.between(ta, tb).getSeconds();
        } catch (Exception exc) {
            return 60;
        }
    }

    public static class Row {
        public final String ts;
        public final String app;
        public final String proc;
        public final String title;

        Row(String ts, String app, String proc, String title) {
            this.ts = ts;
            this.app = app;
            this.proc = proc;
            this.title = title;
        }
    }
}
