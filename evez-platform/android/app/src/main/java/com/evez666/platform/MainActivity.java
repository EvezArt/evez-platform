package com.evez666.platform;

import android.app.Activity;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.speech.RecognizerIntent;
import android.speech.tts.TextToSpeech;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import java.util.ArrayList;
import java.util.Locale;

public class MainActivity extends Activity {

    private WebView webView;
    private TextToSpeech tts;
    private boolean ttsReady = false;
    private static final int STT_REQUEST = 1001;
    private static final String PLATFORM_URL = "http://localhost:8080";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Start background service
        Intent serviceIntent = new Intent(this, PlatformService.class);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(serviceIntent);
        } else {
            startService(serviceIntent);
        }

        // Initialize TTS
        tts = new TextToSpeech(this, status -> {
            if (status == TextToSpeech.SUCCESS) {
                tts.setLanguage(Locale.US);
                tts.setSpeechRate(1.05f);
                tts.setPitch(0.95f);
                ttsReady = true;
            }
        });

        // Create WebView with JS bridge
        webView = new WebView(this);
        setContentView(webView);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setUserAgentString("EVEZ666/0.2.0 Android A16");

        // Add JavaScript bridge for native speech
        webView.addJavascriptInterface(new SpeechBridge(), "EVEZNative");

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                // Inject speech capabilities notification
                view.evaluateJavascript(
                    "window.EVEZ_HAS_NATIVE_SPEECH = true;" +
                    "window.EVEZ_HAS_NATIVE_STT = true;", null);
            }
        });

        webView.setWebChromeClient(new WebChromeClient());
        webView.loadUrl(PLATFORM_URL);
    }

    // JavaScript bridge for native Android speech
    public class SpeechBridge {

        @JavascriptInterface
        public void speak(String text) {
            if (tts != null && ttsReady) {
                tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "evez_" + System.currentTimeMillis());
            }
        }

        @JavascriptInterface
        public void stopSpeaking() {
            if (tts != null) {
                tts.stop();
            }
        }

        @JavascriptInterface
        public void startListening() {
            runOnUiThread(() -> {
                Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
                intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                    RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
                intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.US.toString());
                intent.putExtra(RecognizerIntent.EXTRA_PROMPT, "Speak to EVEZ...");
                try {
                    startActivityForResult(intent, STT_REQUEST);
                } catch (Exception e) {
                    webView.evaluateJavascript(
                        "window.dispatchEvent(new CustomEvent('evez-stt-error', {detail:'" +
                        e.getMessage() + "'}));", null);
                }
            });
        }

        @JavascriptInterface
        public boolean isSpeaking() {
            return tts != null && tts.isSpeaking();
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == STT_REQUEST && resultCode == RESULT_OK && data != null) {
            ArrayList<String> results = data.getStringArrayListExtra(
                RecognizerIntent.EXTRA_RESULTS);
            if (results != null && !results.isEmpty()) {
                String spokenText = results.get(0).replace("'", "\\'");
                webView.evaluateJavascript(
                    "window.dispatchEvent(new CustomEvent('evez-stt-result', " +
                    "{detail:'" + spokenText + "'}));", null);
            }
        }
    }

    @Override
    public void onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        if (tts != null) {
            tts.stop();
            tts.shutdown();
        }
        if (webView != null) {
            webView.destroy();
        }
        super.onDestroy();
    }
}
