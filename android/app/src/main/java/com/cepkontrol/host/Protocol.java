package com.cepkontrol.host;

import android.util.Base64;
import org.json.JSONObject;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

final class Protocol {
    static final String SERVER = "wss://acikdestek-sunucu.tailcb8d95.ts.net";
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final byte[] AAD = "AcikDestek/v1".getBytes(StandardCharsets.UTF_8);
    final String room;
    final String code;
    private final SecretKeySpec key;

    Protocol() throws Exception {
        byte[] roomBytes = new byte[4];
        RANDOM.nextBytes(roomBytes);
        long roomNumber = 100000000L + (Integer.toUnsignedLong(java.nio.ByteBuffer.wrap(roomBytes).getInt()) % 900000000L);
        room = Long.toString(roomNumber);
        byte[] secret = new byte[16];
        RANDOM.nextBytes(secret);
        String alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
        StringBuilder base32 = new StringBuilder();
        int buffer = 0, bits = 0;
        for (byte b : secret) {
            buffer = (buffer << 8) | (b & 255);
            bits += 8;
            while (bits >= 5) {
                bits -= 5;
                base32.append(alphabet.charAt((buffer >>> bits) & 31));
            }
        }
        if (bits > 0) base32.append(alphabet.charAt((buffer << (5 - bits)) & 31));
        code = "AD2." + room + "." + base32;
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(("AcikDestek/v2/" + base32).getBytes(StandardCharsets.UTF_8));
        key = new SecretKeySpec(digest, "AES");
    }

    byte[] pack(JSONObject object) throws Exception {
        byte[] nonce = new byte[12];
        RANDOM.nextBytes(nonce);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(128, nonce));
        cipher.updateAAD(AAD);
        byte[] encrypted = cipher.doFinal(object.toString().getBytes(StandardCharsets.UTF_8));
        byte[] packet = Arrays.copyOf(nonce, nonce.length + encrypted.length);
        System.arraycopy(encrypted, 0, packet, nonce.length, encrypted.length);
        return packet;
    }

    JSONObject unpack(byte[] packet) throws Exception {
        if (packet.length < 28 || packet.length > 16384) throw new IllegalArgumentException("Invalid input packet");
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, Arrays.copyOf(packet, 12)));
        cipher.updateAAD(AAD);
        return new JSONObject(new String(cipher.doFinal(packet, 12, packet.length - 12), StandardCharsets.UTF_8));
    }

    static String randomSession() {
        byte[] bytes = new byte[16];
        RANDOM.nextBytes(bytes);
        StringBuilder result = new StringBuilder(32);
        for (byte b : bytes) result.append(String.format(java.util.Locale.ROOT, "%02x", b & 255));
        return result.toString();
    }

    static String jpegBase64(byte[] jpeg) {
        return Base64.encodeToString(jpeg, Base64.NO_WRAP);
    }
}
