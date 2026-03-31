package com.evez666.platform;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import java.io.BufferedReader;
import java.io.File;
import java.io.InputStreamReader;

public class PlatformService extends Service {

    private static final String CHANNEL_ID = "evez_platform";
    private static final int NOTIFICATION_ID = 1;
    private Process platformProcess;

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
        startForeground(NOTIFICATION_ID, buildNotification());
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        startPlatform();
        return START_STICKY;
    }

    private void startPlatform() {
        try {
            // Find platform directory
            File platformDir = new File(getExternalFilesDir(null), "evez-platform");
            if (!platformDir.exists()) {
                platformDir = new File("/data/data/com.evez666.platform/files/evez-platform");
            }

            if (platformDir.exists()) {
                ProcessBuilder pb = new ProcessBuilder("python3", "main.py");
                pb.directory(platformDir);
                pb.environment().put("EVEZ_PORT", "8080");
                pb.environment().put("EVEZ_DATA", new File(platformDir, "data").getAbsolutePath());
                pb.redirectErrorStream(true);
                platformProcess = pb.start();
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID, "EVEZ Platform", NotificationManager.IMPORTANCE_LOW);
            channel.setDescription("EVEZ cognitive platform running");
            NotificationManager manager = getSystemService(NotificationManager.class);
            if (manager != null) manager.createNotificationChannel(channel);
        }
    }

    private Notification buildNotification() {
        Notification.Builder builder;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            builder = new Notification.Builder(this, CHANNEL_ID);
        } else {
            builder = new Notification.Builder(this);
        }
        return builder
            .setContentTitle("EVEZ666")
            .setContentText("Cognitive platform running")
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .build();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onDestroy() {
        if (platformProcess != null) {
            platformProcess.destroy();
        }
        super.onDestroy();
    }
}
