package com.xlc.worktime;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.ArrayAdapter;
import android.widget.TextView;
import android.widget.Toast;

import java.io.File;
import java.io.FileOutputStream;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;

public class MainActivity extends Activity {

    private Db db;
    private TextView status;
    private TextView summary;
    private ListView list;
    private Button toggle;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable refresh = new Runnable() {
        @Override
        public void run() {
            render();
            handler.postDelayed(this, 10_000L);
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        db = new Db(this);
        status = findViewById(R.id.status);
        summary = findViewById(R.id.summary);
        list = findViewById(R.id.list);
        toggle = findViewById(R.id.toggle);

        toggle.setOnClickListener(v -> {
            if (db.isPaused()) {
                startService(new Intent(this, CaptureService.class)
                        .setAction(CaptureService.ACTION_START));
                db.setPaused(false);
                toast("已开始采集");
            } else {
                startService(new Intent(this, CaptureService.class)
                        .setAction(CaptureService.ACTION_STOP));
                db.setPaused(true);
                toast("已暂停采集");
            }
            render();
        });
        findViewById(R.id.grant).setOnClickListener(v -> {
            try {
                startActivity(new Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS));
            } catch (Exception exc) {
                toast("打不开设置，请手动到「特殊应用权限 → 使用情况访问」授权");
            }
        });
        findViewById(R.id.export).setOnClickListener(v -> exportRaw(false));
        findViewById(R.id.share).setOnClickListener(v -> exportRaw(true));
    }

    @Override
    protected void onResume() {
        super.onResume();
        handler.removeCallbacks(refresh);
        handler.post(refresh);
    }

    @Override
    protected void onPause() {
        handler.removeCallbacks(refresh);
        super.onPause();
    }

    private void render() {
        boolean access = UsageCollector.hasUsageAccess(this);
        boolean paused = db.isPaused();
        if (!access) {
            status.setText("缺少“使用情况访问”权限：点下面的按钮授权后才会有数据");
        } else if (paused) {
            status.setText("已暂停采集");
        } else {
            String last = db.getMeta("collector.last_poll", "");
            String when = last.length() >= 19 ? last.substring(11) : "尚未采样";
            status.setText("采集中 · 最近采样 " + when);
        }
        toggle.setText(paused ? "开始采集" : "暂停采集");

        String today = LocalDate.now().toString();
        Map<String, Long> usage = db.usageByApp(today, 300);
        long total = 0;
        for (Long value : usage.values()) total += value;

        summary.setText("今天 " + today + " · 共 " + human(total)
                + " · " + db.rowCountForDay(today) + " 个采样点");

        List<Map.Entry<String, Long>> entries = new ArrayList<>(usage.entrySet());
        Collections.sort(entries, (a, b) -> Long.compare(b.getValue(), a.getValue()));
        List<String> lines = new ArrayList<>();
        for (Map.Entry<String, Long> entry : entries) {
            lines.add(entry.getKey() + "   " + human(entry.getValue()));
        }
        if (lines.isEmpty()) {
            lines.add("还没有数据：授予权限并开始采集，一分钟后再看这里");
        }
        list.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_list_item_1, lines));
    }

    private void exportRaw(boolean share) {
        String today = LocalDate.now().toString();
        try {
            String json = RawExport.build(db, deviceId(), deviceName(), today);
            File dir = getExternalFilesDir(null);
            if (dir == null) dir = getFilesDir();
            File file = new File(dir, "worktime-raw-" + today + ".json");
            try (FileOutputStream out = new FileOutputStream(file)) {
                out.write(json.getBytes("UTF-8"));
            }
            if (share) {
                Intent send = new Intent(Intent.ACTION_SEND);
                send.setType("application/json");
                send.putExtra(Intent.EXTRA_SUBJECT, "WorkTime 原始事件 " + today);
                send.putExtra(Intent.EXTRA_TEXT, json);
                startActivity(Intent.createChooser(send, "分享到…"));
            } else {
                ClipboardManager cm = (ClipboardManager) getSystemService(
                        Context.CLIPBOARD_SERVICE);
                if (cm != null) {
                    cm.setPrimaryClip(ClipData.newPlainText("worktime-raw", json));
                }
                toast("已导出并复制到剪贴板（" + json.length() + " 字节）\n文件：" + file.getAbsolutePath());
            }
        } catch (Exception exc) {
            toast("导出失败：" + exc.getMessage());
        }
    }

    private String deviceId() {
        String id = db.getMeta("device.id", "");
        if (id.isEmpty()) {
            id = "dev-" + Long.toHexString(System.currentTimeMillis() & 0xffffffffL);
            db.setMeta("device.id", id);
        }
        return id;
    }

    private String deviceName() {
        String name = db.getMeta("device.name", "");
        if (name.isEmpty()) {
            name = android.os.Build.MODEL == null ? "Android" : android.os.Build.MODEL;
            db.setMeta("device.name", name);
        }
        return name;
    }

    private void toast(String message) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show();
    }

    private static String human(long seconds) {
        if (seconds < 60) return seconds + "s";
        long minutes = seconds / 60;
        if (minutes < 60) return minutes + "m";
        return (minutes / 60) + "h" + String.format("%02d", minutes % 60) + "m";
    }
}
