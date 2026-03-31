package com.evez666.platform

import android.annotation.SuppressLint
import android.app.*
import android.content.*
import android.os.*
import android.webkit.*
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.NotificationCompat
import java.io.*

/**
 * EVEZ666 Android A16 — Native WebView + Embedded Platform
 *
 * Features:
 * - Full EVEZ platform UI in native WebView
 * - Background service keeps platform alive 24/7
 * - Boot receiver auto-starts on device restart
 * - JavaScript bridge for native capabilities
 */
class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private val PLATFORM_PORT = 8080

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        webView = WebView(this)
        setContentView(webView)

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            allowFileAccess = true
            allowContentAccess = true
            mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
            mediaPlaybackRequiresUserGesture = false
            userAgentString = "EVEZ666/0.2.0 Android/${Build.VERSION.SDK_INT}"
        }

        webView.webChromeClient = WebChromeClient()

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebRequest?): Boolean {
                return false
            }
        }

        // JavaScript bridge
        webView.addJavascriptInterface(EvezBridge(this), "EvezNative")

        // Start background service
        val serviceIntent = Intent(this, PlatformService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(serviceIntent)
        } else {
            startService(serviceIntent)
        }

        // Load platform UI
        loadPlatform()
    }

    private fun loadPlatform() {
        // Try local first, then embedded
        val url = "http://localhost:$PLATFORM_PORT"
        webView.loadUrl(url)
    }

    override fun onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack()
        } else {
            super.onBackPressed()
        }
    }
}

/**
 * JavaScript bridge for native Android capabilities
 */
class EvezBridge(private val context: Context) {

    @JavascriptInterface
    fun getDeviceInfo(): String {
        return """
            {
                "model": "${Build.MODEL}",
                "manufacturer": "${Build.MANUFACTURER}",
                "sdk": ${Build.VERSION.SDK_INT},
                "release": "${Build.VERSION.RELEASE}",
                "platform": "android"
            }
        """.trimIndent()
    }

    @JavascriptInterface
    fun isOnline(): Boolean {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = cm.activeNetwork ?: return false
        val caps = cm.getNetworkCapabilities(network) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }

    @JavascriptInterface
    fun showToast(message: String) {
        android.widget.Toast.makeText(context, message, android.widget.Toast.LENGTH_SHORT).show()
    }

    @JavascriptInterface
    fun sendNotification(title: String, body: String) {
        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val channelId = "evez_channel"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(channelId, "EVEZ666", NotificationManager.IMPORTANCE_DEFAULT)
            nm.createNotificationChannel(channel)
        }
        val notification = NotificationCompat.Builder(context, channelId)
            .setContentTitle(title)
            .setContentText(body)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .build()
        nm.notify(System.currentTimeMillis().toInt(), notification)
    }
}

/**
 * Foreground service — keeps EVEZ alive 24/7 on Android
 */
class PlatformService : Service() {

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val channelId = "evez_service"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(channelId, "EVEZ Service", NotificationManager.IMPORTANCE_LOW)
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
        val notification = NotificationCompat.Builder(this, channelId)
            .setContentTitle("EVEZ666")
            .setContentText("Cognitive platform running")
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setOngoing(true)
            .build()
        startForeground(1, notification)

        // Keep alive
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null
}

/**
 * Boot receiver — auto-start EVEZ on device boot
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED) {
            val serviceIntent = Intent(context, PlatformService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(serviceIntent)
            } else {
                context.startService(serviceIntent)
            }
        }
    }
}
