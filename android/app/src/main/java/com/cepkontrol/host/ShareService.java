package com.cepkontrol.host;

import android.app.Notification;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.graphics.Bitmap;
import android.graphics.PixelFormat;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.Image;
import android.media.ImageReader;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.util.DisplayMetrics;
import android.view.WindowManager;
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import okio.ByteString;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;
import org.json.JSONObject;

public final class ShareService extends Service {
    static final String START = "com.cepkontrol.host.START";
    static final String STOP = "com.cepkontrol.host.STOP";
    static volatile boolean sharing;
    static volatile boolean connected;
    static volatile String activeCode = "";
    static volatile String status = "Hazır";
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ScheduledExecutorService worker = Executors.newSingleThreadScheduledExecutor();
    private final OkHttpClient client = new OkHttpClient.Builder().pingInterval(20, TimeUnit.SECONDS).build();
    private Protocol protocol;
    private MediaProjection projection;
    private VirtualDisplay display;
    private ImageReader reader;
    private WebSocket socket;
    private volatile String session;
    private volatile boolean approved;
    private volatile long pendingFrame;
    private volatile long lastFrameSent;
    private long frameId;
    private long lastSeq = -1;
    private int width;
    private int height;
    private boolean stopped;

    @Override public IBinder onBind(Intent intent) { return null; }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null) return START_NOT_STICKY;
        if (STOP.equals(intent.getAction())) { stopSelf(); return START_NOT_STICKY; }
        if (!START.equals(intent.getAction()) || sharing) return START_NOT_STICKY;
        try {
            protocol = new Protocol();
            activeCode = protocol.code;
            status = "Paylaşım hazırlanıyor";
            Intent stopIntent = new Intent(this, ShareService.class).setAction(STOP);
            PendingIntent stop = PendingIntent.getService(this, 0, stopIntent, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
            Notification notification = new Notification.Builder(this, "share")
                .setSmallIcon(android.R.drawable.ic_menu_share)
                .setContentTitle("CepKontrol ekran paylaşımı")
                .setContentText("Paylaşım açık · durdurmak için dokun")
                .setContentIntent(stop)
                .setOngoing(true)
                .build();
            if (Build.VERSION.SDK_INT >= 29) startForeground(1, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION);
            else startForeground(1, notification);
            int result = intent.getIntExtra("result", 0);
            Intent data = intent.getParcelableExtra("data");
            if (result != android.app.Activity.RESULT_OK || data == null) throw new IllegalArgumentException("Missing screen permission");
            MediaProjectionManager manager = (MediaProjectionManager)getSystemService(MEDIA_PROJECTION_SERVICE);
            projection = manager.getMediaProjection(result, data);
            projection.registerCallback(new MediaProjection.Callback() {
                @Override public void onStop() { main.post(() -> stopSelf()); }
            }, main);
            DisplayMetrics metrics = new DisplayMetrics();
            ((WindowManager)getSystemService(WINDOW_SERVICE)).getDefaultDisplay().getRealMetrics(metrics);
            double scale = Math.min(1.0, Math.min(720.0 / metrics.widthPixels, 1280.0 / metrics.heightPixels));
            width = Math.max(2, ((int)(metrics.widthPixels * scale)) & ~1);
            height = Math.max(2, ((int)(metrics.heightPixels * scale)) & ~1);
            reader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2);
            display = projection.createVirtualDisplay("CepKontrol", width, height, metrics.densityDpi,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR, reader.getSurface(), null, main);
            sharing = true;
            status = "Kod hazır · bilgisayardan bağlan";
            worker.scheduleWithFixedDelay(this::captureFrame, 0, 300, TimeUnit.MILLISECONDS);
            connect();
        } catch (Exception e) {
            status = "Ekran paylaşımı başlatılamadı";
            stopSelf();
        }
        return START_NOT_STICKY;
    }

    private void connect() {
        if (stopped) return;
        approved = false;
        connected = false;
        pendingFrame = 0;
        session = null;
        status = "Sunucuya bağlanıyor";
        Request request = new Request.Builder().url(Protocol.SERVER + "/host/" + protocol.room).build();
        socket = client.newWebSocket(request, new WebSocketListener() {
            @Override public void onOpen(WebSocket ws, Response response) { status = "Kod hazır · bilgisayardan bağlan"; }
            @Override public void onMessage(WebSocket ws, ByteString bytes) {
                if (ws != socket || stopped) return;
                try { receive(ws, protocol.unpack(bytes.toByteArray())); }
                catch (Exception ignored) { /* Unauthenticated or malformed packet. */ }
            }
            @Override public void onFailure(WebSocket ws, Throwable error, Response response) { reconnect(ws); }
            @Override public void onClosed(WebSocket ws, int code, String reason) { reconnect(ws); }
        });
    }

    private void reconnect(WebSocket ws) {
        if (ws != socket || stopped) return;
        socket = null;
        approved = false;
        connected = false;
        session = null;
        status = "Bağlantı kesildi · yeniden deneniyor";
        worker.schedule(this::connect, 2, TimeUnit.SECONDS);
    }

    private void receive(WebSocket ws, JSONObject msg) throws Exception {
        String kind = msg.optString("type");
        if ("hello".equals(kind) && !approved) {
            session = Protocol.randomSession();
            lastSeq = -1;
            JSONObject response = new JSONObject().put("type", "accepted").put("session", session);
            ws.send(ByteString.of(protocol.pack(response)));
            approved = true;
            connected = true;
            status = "Bilgisayar bağlı · ekran paylaşılıyor";
        } else if ("frame_ack".equals(kind) && approved && session.equals(msg.optString("session"))) {
            if (msg.optLong("frame_id", -1) == pendingFrame) pendingFrame = 0;
        } else if ("input".equals(kind) && approved && session.equals(msg.optString("session"))) {
            long seq = msg.optLong("seq", -1);
            if (seq <= lastSeq) return;
            lastSeq = seq;
            JSONObject event = msg.optJSONObject("event");
            if (event == null) return;
            String action = event.optString("kind");
            if ("heartbeat".equals(action)) {
                ws.send(ByteString.of(protocol.pack(new JSONObject().put("type", "heartbeat").put("session", session))));
                return;
            }
            ControlService control = ControlService.active;
            if (control == null) return;
            float x = (float)event.optDouble("x", 0.5);
            float y = (float)event.optDouble("y", 0.5);
            if (!Float.isFinite(x) || !Float.isFinite(y) || x < 0 || x > 1 || y < 0 || y > 1) return;
            if ("keydown".equals(action)) {
                String key = event.optString("key");
                if ("esc".equals(key)) action = "back";
                else if ("backspace".equals(key)) action = "backspace";
                else if ("enter".equals(key)) action = "enter";
                else if ("winleft".equals(key)) action = "home";
                else return;
            } else if ("keyup".equals(action)) return;
            int steps = Math.max(-5, Math.min(5, event.optInt("steps", 0)));
            String value = event.optString("text", "");
            control.input(action, x, y, steps, value);
        }
    }

    private void captureFrame() {
        if (!approved || stopped || reader == null || socket == null || session == null) return;
        long now = android.os.SystemClock.elapsedRealtime();
        if (pendingFrame != 0) {
            if (now - lastFrameSent < 40000) return;
            socket.close(1000, "Viewer stalled");
            return;
        }
        Image image = null;
        Bitmap bitmap = null;
        try {
            image = reader.acquireLatestImage();
            if (image == null) return;
            Image.Plane plane = image.getPlanes()[0];
            ByteBuffer buffer = plane.getBuffer();
            int row = plane.getRowStride();
            int pixel = plane.getPixelStride();
            bitmap = Bitmap.createBitmap(width + (row - pixel * width) / pixel, height, Bitmap.Config.ARGB_8888);
            bitmap.copyPixelsFromBuffer(buffer);
            Bitmap clean = Bitmap.createBitmap(bitmap, 0, 0, width, height);
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            clean.compress(Bitmap.CompressFormat.JPEG, 50, output);
            clean.recycle();
            if (output.size() > 2_000_000) return;
            long id = ++frameId;
            JSONObject frame = new JSONObject().put("type", "frame").put("session", session)
                .put("frame_id", id).put("jpeg", Protocol.jpegBase64(output.toByteArray()));
            pendingFrame = id;
            lastFrameSent = now;
            if (!socket.send(ByteString.of(protocol.pack(frame)))) pendingFrame = 0;
        } catch (Exception ignored) {
            // Rotation and app-protected surfaces may temporarily have no frame.
        } finally {
            if (image != null) image.close();
            if (bitmap != null) bitmap.recycle();
        }
    }

    @Override public void onDestroy() {
        stopped = true;
        sharing = false;
        connected = false;
        activeCode = "";
        status = "Paylaşım durdu";
        if (socket != null) socket.close(1000, "Phone stopped sharing");
        worker.shutdownNow();
        if (display != null) display.release();
        if (reader != null) reader.close();
        if (projection != null) projection.stop();
        client.dispatcher().executorService().shutdown();
        super.onDestroy();
    }
}
