package com.xlc.worktime;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;

/**
 * Foreground service: samples foreground apps every minute and writes raw rows.
 * Battery-friendly on purpose (one UsageStats query per minute, no wake locks
 * beyond the foreground service itself).
 */
public class CaptureService extends Service {

    public static final String ACTION_START = "com.xlc.worktime.START";
    public static final String ACTION_STOP = "com.xlc.worktime.STOP";
    public static final String CHANNEL_ID = "worktime_capture";
    public static final int NOTIFICATION_ID = 42;
    private static final long INTERVAL_MS = 60_000L;

    private Handler handler;
    private Db db;
    private final Runnable tick = new Runnable() {
        @Override
        public void run() {
            try {
                UsageCollector.poll(CaptureService.this, db);
            } catch (Exception exc) {
                android.util.Log.e("WorkTime", "poll failed", exc);
            }
            if (handler != null) handler.postDelayed(this, INTERVAL_MS);
        }
    };

    @Override
    public void onCreate() {
        super.onCreate();
        db = new Db(this);
        handler = new Handler(Looper.getMainLooper());
        createChannel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent == null ? ACTION_START : intent.getAction();
        if (ACTION_STOP.equals(action)) {
            db.setPaused(true);
            stopForeground(true);
            stopSelf();
            return START_NOT_STICKY;
        }
        startForeground(NOTIFICATION_ID, buildNotification());
        db.setPaused(false);
        db.setMeta("collector.started_at", nowStamp());
        handler.removeCallbacks(tick);
        handler.post(tick);
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        if (handler != null) handler.removeCallbacks(tick);
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) {
                NotificationChannel channel = new NotificationChannel(
                        CHANNEL_ID, "采集状态",
                        NotificationManager.IMPORTANCE_LOW);
                channel.setDescription("WorkTime 正在记录前台应用");
                nm.createNotificationChannel(channel);
            }
        }
    }

    private Notification buildNotification() {
        Intent open = new Intent(this, MainActivity.class);
        PendingIntent pending = PendingIntent.getActivity(this, 0, open,
                PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder builder = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? new Notification.Builder(this, CHANNEL_ID)
                : new Notification.Builder(this);
        return builder
                .setContentTitle("WorkTime 正在采集")
                .setContentText("只记录前台应用与时长，数据留在本机")
                .setSmallIcon(android.R.drawable.ic_menu_recent_history)
                .setContentIntent(pending)
                .setOngoing(true)
                .build();
    }

    private static String nowStamp() {
        return java.time.LocalDateTime.now()
                .format(java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss"));
    }
}
