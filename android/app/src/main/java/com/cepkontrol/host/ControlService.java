package com.cepkontrol.host;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.GestureDescription;
import android.graphics.Path;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import java.util.ArrayList;

public final class ControlService extends AccessibilityService {
    static volatile ControlService active;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ArrayList<float[]> drag = new ArrayList<>();

    @Override public void onServiceConnected() { active = this; }
    @Override public void onAccessibilityEvent(AccessibilityEvent event) { }
    @Override public void onInterrupt() { }
    @Override public void onDestroy() { if (active == this) active = null; super.onDestroy(); }

    void input(String kind, float x, float y, int steps, String value) {
        main.post(() -> {
            if (active != this || !ShareService.sharing || !ShareService.connected) return;
            switch (kind) {
                case "down":
                    drag.clear();
                    drag.add(new float[]{x, y});
                    break;
                case "move":
                    if (!drag.isEmpty() && drag.size() < 150) drag.add(new float[]{x, y});
                    break;
                case "up":
                    if (drag.isEmpty()) drag.add(new float[]{x, y});
                    drag.add(new float[]{x, y});
                    gesture(drag, drag.size() > 2 ? Math.min(1200, Math.max(100, drag.size() * 35)) : 50);
                    drag.clear();
                    break;
                case "release": drag.clear(); break;
                case "scroll":
                    if (steps != 0) {
                        ArrayList<float[]> swipe = new ArrayList<>();
                        swipe.add(new float[]{.5f, steps > 0 ? .65f : .35f});
                        swipe.add(new float[]{.5f, steps > 0 ? .35f : .65f});
                        gesture(swipe, 220);
                    }
                    break;
                case "text": appendText(value); break;
                case "backspace": deleteText(); break;
                case "enter":
                    AccessibilityNodeInfo node = getRootInActiveWindow();
                    if (node != null) {
                        try {
                            AccessibilityNodeInfo focused = node.findFocus(AccessibilityNodeInfo.FOCUS_INPUT);
                            if (focused != null) {
                                try { if (android.os.Build.VERSION.SDK_INT >= 30) focused.performAction(AccessibilityNodeInfo.ACTION_IME_ENTER); }
                                finally { focused.recycle(); }
                            }
                        } finally { node.recycle(); }
                    }
                    break;
                case "back": performGlobalAction(GLOBAL_ACTION_BACK); break;
                case "home": performGlobalAction(GLOBAL_ACTION_HOME); break;
                case "recents": performGlobalAction(GLOBAL_ACTION_RECENTS); break;
                default: break;
            }
        });
    }

    private void gesture(ArrayList<float[]> points, int duration) {
        if (points.isEmpty()) return;
        android.util.DisplayMetrics metrics = getResources().getDisplayMetrics();
        Path path = new Path();
        path.moveTo(points.get(0)[0] * metrics.widthPixels, points.get(0)[1] * metrics.heightPixels);
        for (int i = 1; i < points.size(); i++) path.lineTo(points.get(i)[0] * metrics.widthPixels, points.get(i)[1] * metrics.heightPixels);
        GestureDescription.Builder builder = new GestureDescription.Builder();
        builder.addStroke(new GestureDescription.StrokeDescription(path, 0, duration));
        dispatchGesture(builder.build(), null, null);
    }

    private void appendText(String value) {
        if (value == null || value.length() > 8 || value.isEmpty()) return;
        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null) return;
        try {
            AccessibilityNodeInfo focused = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT);
            if (focused == null || !focused.isEditable()) return;
            try {
                CharSequence before = focused.getText();
                Bundle args = new Bundle();
                args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,
                    (before == null ? "" : before.toString()) + value);
                focused.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args);
            } finally { focused.recycle(); }
        } finally { root.recycle(); }
    }

    private void deleteText() {
        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null) return;
        try {
            AccessibilityNodeInfo focused = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT);
            if (focused == null || !focused.isEditable()) return;
            try {
                CharSequence before = focused.getText();
                if (before == null || before.length() == 0) return;
                Bundle args = new Bundle();
                args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,
                    before.subSequence(0, before.length() - 1));
                focused.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args);
            } finally { focused.recycle(); }
        } finally { root.recycle(); }
    }
}
