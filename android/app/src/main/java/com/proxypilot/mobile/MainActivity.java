package com.proxypilot.mobile;

import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.view.View;
import android.view.WindowManager;
import android.webkit.DownloadListener;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import androidx.appcompat.app.AppCompatActivity;

public class MainActivity extends AppCompatActivity {

    private WebView webView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().setFlags(WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS);

        webView = new WebView(this);
        setContentView(webView);

        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(true);
        // 离线打包的 HTML 走 file:// 协议，需要打开这个才能跨域 fetch 远端 json/订阅
        s.setAllowUniversalAccessFromFileURLs(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);
        s.setDisplayZoomControls(false);
        s.setMediaPlaybackRequiresUserGesture(false);

        // 拦截所有自定义 scheme 跳转（clash://、v2rayng://、sing-box://），
        // 由本应用负责调起对应客户端；同时把外部 https 链接也抛给系统浏览器。
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                if (url == null) return false;
                if (url.startsWith("http://") || url.startsWith("https://")
                        || url.startsWith("file://") || url.startsWith("about:")) {
                    return false;   // 让 WebView 自己处理
                }
                try {
                    Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
                    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                    startActivity(intent);
                } catch (Exception ignored) {
                }
                return true;
            }
        });

        webView.setDownloadListener(new DownloadListener() {
            @Override public void onDownloadStart(String url, String u1, String u2, String u3, long l) {
                // 订阅链接可直接在新窗口打开预览
                Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
                try { startActivity(intent); } catch (Exception ignored) {}
            }
        });

        // 隐藏滚动条 & 滚动条占位（沉浸感）
        webView.setVerticalScrollBarEnabled(false);
        webView.setHorizontalScrollBarEnabled(false);
        webView.setOverScrollMode(View.OVER_SCROLL_NEVER);

        webView.loadUrl("file:///android_asset/index.html");
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }
}