package com.cepkontrol.host;

import android.app.Activity;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.media.projection.MediaProjectionManager;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.graphics.Color;
import android.view.Gravity;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

public final class MainActivity extends Activity {
    private static final int REQUEST_CAPTURE = 7;
    private TextView status;
    private TextView code;
    private final android.os.Handler handler = new android.os.Handler(android.os.Looper.getMainLooper());
    private final Runnable refresh = new Runnable() {
        @Override public void run() {
            if (status != null) {
                status.setText(ShareService.status);
                code.setText(ShareService.activeCode.isEmpty() ? "" : ShareService.activeCode);
                handler.postDelayed(this, 400);
            }
        }
    };

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel channel = new NotificationChannel("share", "Ekran paylaşımı", NotificationManager.IMPORTANCE_LOW);
            getSystemService(NotificationManager.class).createNotificationChannel(channel);
        }
        LinearLayout page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        page.setPadding(dp(24), dp(36), dp(24), dp(24));
        page.setBackgroundColor(Color.rgb(12, 20, 37));
        TextView title = text("CepKontrol", 27, 0xff46dfb2);
        page.addView(title);
        TextView description = text("Telefon ekranını bilgisayarından gör ve kontrol et. Başlatınca Android ekran paylaşımı izni isteyecek.", 16, Color.WHITE);
        description.setPadding(0, dp(18), 0, dp(18));
        page.addView(description);
        status = text("Hazır", 15, Color.LTGRAY);
        page.addView(status);
        code = text("", 19, Color.WHITE);
        code.setTextIsSelectable(true);
        code.setPadding(0, dp(18), 0, dp(18));
        page.addView(code);
        Button copy = button("Kodu kopyala");
        copy.setOnClickListener(v -> {
            if (!ShareService.activeCode.isEmpty()) {
                ((ClipboardManager)getSystemService(Context.CLIPBOARD_SERVICE)).setPrimaryClip(ClipData.newPlainText("CepKontrol kodu", ShareService.activeCode));
            }
        });
        page.addView(copy);
        Button start = button("Ekran paylaşımını başlat");
        start.setOnClickListener(v -> {
            if (ShareService.sharing) return;
            MediaProjectionManager manager = (MediaProjectionManager)getSystemService(MEDIA_PROJECTION_SERVICE);
            startActivityForResult(manager.createScreenCaptureIntent(), REQUEST_CAPTURE);
        });
        page.addView(start);
        Button access = button("Dokunma iznini aç");
        access.setOnClickListener(v -> startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)));
        page.addView(access);
        Button stop = button("Paylaşımı durdur");
        stop.setOnClickListener(v -> startService(new Intent(this, ShareService.class).setAction(ShareService.STOP)));
        page.addView(stop);
        TextView note = text("Bilgisayarda CepKontrol → Bilgisayardan bağlan alanına kodu yaz. Kontrol için Android Erişilebilirlik ayarlarında CepKontrol dokunma kontrolünü aç. Paylaşımı bildirimden veya buradan durdurabilirsin.", 13, Color.LTGRAY);
        note.setPadding(0, dp(18), 0, 0);
        page.addView(note);
        setContentView(page);
    }

    @Override protected void onResume() { super.onResume(); handler.removeCallbacks(refresh); handler.post(refresh); }
    @Override protected void onPause() { handler.removeCallbacks(refresh); super.onPause(); }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request != REQUEST_CAPTURE || result != RESULT_OK || data == null) return;
        Intent service = new Intent(this, ShareService.class);
        service.setAction(ShareService.START);
        service.putExtra("result", result);
        service.putExtra("data", data);
        startForegroundService(service);
    }

    private int dp(int value) { return (int)(value * getResources().getDisplayMetrics().density); }
    private TextView text(String value, int size, int color) {
        TextView view = new TextView(this);
        view.setText(value); view.setTextSize(size); view.setTextColor(color);
        return view;
    }
    private Button button(String value) {
        Button view = new Button(this);
        view.setText(value);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
        params.topMargin = dp(8);
        view.setLayoutParams(params);
        return view;
    }
}
