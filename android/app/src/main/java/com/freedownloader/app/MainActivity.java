package com.freedownloader.app;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.DownloadManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.view.Gravity;
import android.view.Menu;
import android.view.MenuItem;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.webkit.URLUtil;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import java.util.Locale;

/** Native Android shell for the hosted FreeDownloader service. */
public final class MainActivity extends Activity {
    private static final String PREFERENCES = "free_downloader_preferences";
    private static final String SERVER_URL = "server_url";
    private static final int MENU_CHANGE_SERVER = 1;

    private WebView webView;
    private ProgressBar progressBar;
    private SharedPreferences preferences;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        preferences = getSharedPreferences(PREFERENCES, MODE_PRIVATE);
        String serverUrl = preferences.getString(SERVER_URL, getString(R.string.default_server_url));
        if (isPlaceholder(serverUrl)) {
            showServerSetup();
        } else {
            showWebApp(serverUrl);
        }
    }

    private boolean isPlaceholder(String url) {
        return url == null || url.contains("seu-projeto.vercel.app");
    }

    private boolean isValidServerUrl(String url) {
        try {
            Uri uri = Uri.parse(url);
            return "https".equalsIgnoreCase(uri.getScheme()) && uri.getHost() != null;
        } catch (Exception exception) {
            return false;
        }
    }

    private String normalizeServerUrl(String url) {
        String normalized = url.trim();
        return normalized.endsWith("/") ? normalized : normalized + "/";
    }

    private void showServerSetup() {
        setTitle(R.string.setup_title);
        int padding = dp(24);
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setGravity(Gravity.CENTER_VERTICAL);
        content.setPadding(padding, padding, padding, padding);

        TextView title = new TextView(this);
        title.setText(R.string.setup_heading);
        title.setTextColor(Color.rgb(16, 42, 67));
        title.setTextSize(26);
        title.setGravity(Gravity.CENTER);
        content.addView(title, new LinearLayout.LayoutParams(-1, -2));

        TextView description = new TextView(this);
        description.setText(R.string.setup_description);
        description.setTextSize(16);
        description.setPadding(0, dp(16), 0, dp(20));
        content.addView(description, new LinearLayout.LayoutParams(-1, -2));

        EditText serverInput = new EditText(this);
        serverInput.setHint(R.string.server_url_hint);
        serverInput.setInputType(android.text.InputType.TYPE_TEXT_VARIATION_URI);
        serverInput.setSingleLine(true);
        String savedUrl = preferences.getString(SERVER_URL, "");
        if (!isPlaceholder(savedUrl)) serverInput.setText(savedUrl);
        content.addView(serverInput, new LinearLayout.LayoutParams(-1, -2));

        Button save = new Button(this);
        save.setText(R.string.save_and_continue);
        LinearLayout.LayoutParams buttonParams = new LinearLayout.LayoutParams(-1, -2);
        buttonParams.topMargin = dp(20);
        content.addView(save, buttonParams);
        save.setOnClickListener(view -> {
            String serverUrl = normalizeServerUrl(serverInput.getText().toString());
            if (!isValidServerUrl(serverUrl)) {
                serverInput.setError(getString(R.string.invalid_server_url));
                return;
            }
            preferences.edit().putString(SERVER_URL, serverUrl).apply();
            showWebApp(serverUrl);
        });
        setContentView(content);
    }

    @SuppressLint("SetJavaScriptEnabled")
    private void showWebApp(String serverUrl) {
        setTitle(R.string.app_name);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);

        progressBar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progressBar.setMax(100);
        progressBar.setVisibility(View.GONE);
        root.addView(progressBar, new LinearLayout.LayoutParams(-1, dp(3)));

        webView = new WebView(this);
        webView.setBackgroundColor(Color.WHITE);
        webView.getSettings().setJavaScriptEnabled(true);
        webView.getSettings().setDomStorageEnabled(true);
        webView.getSettings().setLoadWithOverviewMode(true);
        webView.getSettings().setUseWideViewPort(true);
        webView.getSettings().setUserAgentString(webView.getSettings().getUserAgentString() + " FreeDownloaderAndroid/1.0");
        CookieManager.getInstance().setAcceptCookie(true);
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int progress) {
                progressBar.setProgress(progress);
                progressBar.setVisibility(progress < 100 ? View.VISIBLE : View.GONE);
            }
        });
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri target = request.getUrl();
                if ("http".equals(target.getScheme()) || "https".equals(target.getScheme())) {
                    return false;
                }
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, target));
                } catch (Exception ignored) {
                    Toast.makeText(MainActivity.this, R.string.unable_to_open_link, Toast.LENGTH_SHORT).show();
                }
                return true;
            }
        });
        webView.setDownloadListener(createDownloadListener());
        root.addView(webView, new LinearLayout.LayoutParams(-1, 0, 1));
        setContentView(root);
        webView.loadUrl(serverUrl);
    }

    private DownloadListener createDownloadListener() {
        return (url, userAgent, contentDisposition, mimetype, contentLength) -> {
            try {
                DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url));
                String cookies = CookieManager.getInstance().getCookie(url);
                if (cookies != null) request.addRequestHeader("Cookie", cookies);
                request.addRequestHeader("User-Agent", userAgent);
                request.setMimeType(mimetype);
                request.setTitle(URLUtil.guessFileName(url, contentDisposition, mimetype));
                request.setDescription(getString(R.string.download_description));
                request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS,
                        URLUtil.guessFileName(url, contentDisposition, mimetype));
                ((DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE)).enqueue(request);
                Toast.makeText(this, R.string.download_started, Toast.LENGTH_SHORT).show();
            } catch (Exception exception) {
                Toast.makeText(this, R.string.download_failed, Toast.LENGTH_LONG).show();
            }
        };
    }

    @Override
    public boolean onCreateOptionsMenu(Menu menu) {
        menu.add(Menu.NONE, MENU_CHANGE_SERVER, Menu.NONE, R.string.change_server)
                .setShowAsAction(MenuItem.SHOW_AS_ACTION_NEVER);
        return true;
    }

    @Override
    public boolean onOptionsItemSelected(MenuItem item) {
        if (item.getItemId() == MENU_CHANGE_SERVER) {
            showServerSetup();
            return true;
        }
        return super.onOptionsItemSelected(item);
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            webView.destroy();
        }
        super.onDestroy();
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
