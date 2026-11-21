package org.livingtext.lunacontrol;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.bluetooth.*;
import android.bluetooth.le.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.os.*;
import android.webkit.*;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.IOException;
import java.util.*;

@SuppressLint({"MissingPermission", "SetJavaScriptEnabled"})
public class MainActivity extends Activity {
    private static final UUID SERVICE = UUID.fromString("41750001-71bd-4d43-8c75-326c756e6100");
    private static final UUID COMMAND = UUID.fromString("41750002-71bd-4d43-8c75-326c756e6100");
    private static final UUID STATUS = UUID.fromString("41750003-71bd-4d43-8c75-326c756e6100");
    private static final UUID CCC = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb");
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Map<String, BluetoothDevice> devices = new LinkedHashMap<>();
    private final ArrayDeque<byte[]> writes = new ArrayDeque<>();
    private WebView web;
    private BluetoothAdapter adapter;
    private BluetoothGatt gatt;
    private BluetoothGattCharacteristic command;
    private BluetoothLeScanner scanner;
    private BluetoothDevice pairing;
    private boolean ready, writing, scanning, foreground;
    private Runnable scanTimeout;

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        getWindow().setStatusBarColor(0xff10282d);
        getWindow().setNavigationBarColor(0xff10282d);
        adapter = getSystemService(BluetoothManager.class).getAdapter();
        web = new WebView(this);
        web.setBackgroundColor(0xff10282d);
        web.getSettings().setJavaScriptEnabled(true);
        web.getSettings().setAllowFileAccess(false);
        web.getSettings().setAllowContentAccess(false);
        web.getSettings().setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        web.addJavascriptInterface(new Bridge(), "Luna");
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return true;
            }
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                String path = request.getUrl().getPath();
                if ("https".equals(request.getUrl().getScheme()) &&
                        "luna.local".equals(request.getUrl().getHost()) &&
                        Arrays.asList("/index.html", "/app.js", "/style.css").contains(path)) {
                    try {
                        String mime = path.endsWith(".js") ? "text/javascript" :
                                path.endsWith(".css") ? "text/css" : "text/html";
                        return new WebResourceResponse(mime, "UTF-8", getAssets().open(path.substring(1)));
                    } catch (IOException ignored) { }
                }
                return new WebResourceResponse("text/plain", "UTF-8", 403, "Blocked", Map.of(),
                        new java.io.ByteArrayInputStream(new byte[0]));
            }
        });
        setContentView(web);
        web.loadUrl("https://luna.local/index.html");
        IntentFilter filter = new IntentFilter(BluetoothDevice.ACTION_BOND_STATE_CHANGED);
        filter.addAction(BluetoothAdapter.ACTION_STATE_CHANGED);
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(receiver, filter, Context.RECEIVER_EXPORTED);
        else registerReceiver(receiver, filter);
    }

    private void event(String type, Object data) {
        handler.post(() -> {
            if (web != null) web.evaluateJavascript(
                    "window.nativeEvent&&window.nativeEvent(" +
                    JSONObject.quote(type) + "," +
                    (data instanceof String ? JSONObject.quote((String) data) : String.valueOf(data)) + ")", null);
        });
    }

    private boolean permissions() {
        return checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN) == PackageManager.PERMISSION_GRANTED &&
                checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED;
    }

    private void scan() {
        if (!permissions()) {
            requestPermissions(new String[]{Manifest.permission.BLUETOOTH_SCAN,
                    Manifest.permission.BLUETOOTH_CONNECT}, 1);
            return;
        }
        if (adapter == null) { event("error", "This phone has no Bluetooth adapter."); return; }
        if (!adapter.isEnabled()) {
            startActivityForResult(new Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE), 2);
            return;
        }
        close();
        devices.clear();
        event("devices", new JSONArray());
        scanner = adapter.getBluetoothLeScanner();
        if (scanner == null) { event("error", "Bluetooth scanner unavailable."); return; }
        scanning = true;
        scanner.startScan(List.of(new ScanFilter.Builder().setServiceUuid(new ParcelUuid(SERVICE)).build()),
                new ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build(), scanCallback);
        event("connection", "Searching for Luna…");
        scanTimeout = () -> {
            stopScan();
            event("connection", devices.isEmpty() ? "No Luna found. Check the Pi service and pairing window." :
                    "Choose Luna below.");
        };
        handler.postDelayed(scanTimeout, 15000);
    }

    private void stopScan() {
        if (scanning && scanner != null && permissions()) scanner.stopScan(scanCallback);
        scanning = false;
        if (scanTimeout != null) handler.removeCallbacks(scanTimeout);
    }

    private final ScanCallback scanCallback = new ScanCallback() {
        @Override public void onScanResult(int type, ScanResult result) {
            handler.post(() -> {
                if (!scanning) return;
                BluetoothDevice device = result.getDevice();
                devices.put(device.getAddress(), device);
                JSONArray list = new JSONArray();
                for (BluetoothDevice found : devices.values()) {
                    try {
                        list.put(new JSONObject().put("address", found.getAddress())
                                .put("name", found.getName() == null ? "Luna" : found.getName()));
                    } catch (org.json.JSONException ignored) { }
                }
                event("devices", list);
            });
        }
        @Override public void onScanFailed(int error) {
            handler.post(() -> { stopScan(); event("error", "Bluetooth scan failed (" + error + "). Try again."); });
        }
    };

    private void connect(String address) {
        if (!permissions() || !devices.containsKey(address)) return;
        BluetoothDevice device = devices.get(address);
        close();
        pairing = device;
        if (device.getBondState() != BluetoothDevice.BOND_BONDED) {
            event("connection", "Approve Bluetooth pairing on the phone and Pi.");
            if (!device.createBond()) event("error", "Could not start pairing. Open the Pi pairing window first.");
        } else openGatt(device);
    }

    private void openGatt(BluetoothDevice device) {
        if (!foreground) return;
        pairing = null;
        event("connection", "Connecting…");
        gatt = device.connectGatt(this, false, callback, BluetoothDevice.TRANSPORT_LE);
    }

    private final BroadcastReceiver receiver = new BroadcastReceiver() {
        @Override public void onReceive(Context context, Intent intent) {
            if (!permissions()) return;
            if (BluetoothAdapter.ACTION_STATE_CHANGED.equals(intent.getAction())) {
                if (!adapter.isEnabled()) close();
            } else if (pairing != null) {
                if (pairing.getBondState() == BluetoothDevice.BOND_BONDED) openGatt(pairing);
                else if (pairing.getBondState() == BluetoothDevice.BOND_NONE) {
                    pairing = null;
                    event("error", "Pairing was cancelled. Check the Pi agent and try again.");
                }
            }
        }
    };

    private final BluetoothGattCallback callback = new BluetoothGattCallback() {
        @Override public void onConnectionStateChange(BluetoothGatt current, int status, int state) {
            handler.post(() -> {
                if (current != gatt) { current.close(); return; }
                if (status == BluetoothGatt.GATT_SUCCESS && state == BluetoothProfile.STATE_CONNECTED) {
                    event("connection", "Discovering controls…");
                    if (!current.discoverServices()) fail("Could not discover services.");
                } else {
                    close();
                    event("connection", "Disconnected · Luna returns to idle + microphone");
                }
            });
        }
        @Override public void onServicesDiscovered(BluetoothGatt current, int status) {
            handler.post(() -> {
                if (current != gatt) return;
                BluetoothGattService service = current.getService(SERVICE);
                if (status != BluetoothGatt.GATT_SUCCESS || service == null) {
                    fail("Luna control service was not found."); return;
                }
                command = service.getCharacteristic(COMMAND);
                BluetoothGattCharacteristic state = service.getCharacteristic(STATUS);
                BluetoothGattDescriptor descriptor = state == null ? null : state.getDescriptor(CCC);
                if (command == null || descriptor == null ||
                        !current.setCharacteristicNotification(state, true)) {
                    fail("Luna's Bluetooth characteristics are incomplete."); return;
                }
                boolean accepted;
                if (Build.VERSION.SDK_INT >= 33) {
                    accepted = current.writeDescriptor(descriptor, BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE) ==
                            BluetoothStatusCodes.SUCCESS;
                } else {
                    descriptor.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
                    accepted = current.writeDescriptor(descriptor);
                }
                if (!accepted) fail("Could not subscribe to Luna's status.");
            });
        }
        @Override public void onDescriptorWrite(BluetoothGatt current, BluetoothGattDescriptor descriptor, int status) {
            handler.post(() -> {
                if (current != gatt) return;
                if (status != BluetoothGatt.GATT_SUCCESS) {
                    fail("Status subscription failed. Check Bluetooth pairing."); return;
                }
                ready = true;
                event("connected", true);
                event("connection", "Connected · tap Take control");
            });
        }
        @Override public void onCharacteristicChanged(BluetoothGatt current, BluetoothGattCharacteristic characteristic,
                                                       byte[] value) {
            if (current == gatt && STATUS.equals(characteristic.getUuid())) receive(value);
        }
        @Override public void onCharacteristicChanged(BluetoothGatt current, BluetoothGattCharacteristic characteristic) {
            if (current == gatt && STATUS.equals(characteristic.getUuid())) receive(characteristic.getValue());
        }
        @Override public void onCharacteristicWrite(BluetoothGatt current, BluetoothGattCharacteristic characteristic, int status) {
            handler.post(() -> {
                if (current != gatt) return;
                writing = false;
                if (status != BluetoothGatt.GATT_SUCCESS) fail("Bluetooth write failed. Luna will return to idle.");
                else drain();
            });
        }
    };

    private void receive(byte[] bytes) {
        JSONArray values = new JSONArray();
        for (byte value : bytes) values.put(value & 255);
        event("status", values);
    }

    private void fail(String message) { close(); event("error", message); }

    private void enqueue(byte[] packet) {
        if (!ready || gatt == null || !foreground) return;
        int opcode = packet[1] & 255;
        if (opcode == 1 || opcode == 4) writes.removeIf(old -> old[1] == packet[1]);
        if (opcode == 3) writes.clear();
        if (writes.size() >= 12) { fail("Bluetooth queue stalled. Reconnect to resume."); return; }
        writes.add(packet);
        drain();
    }

    private void drain() {
        if (writing || writes.isEmpty() || gatt == null || command == null) return;
        byte[] packet = writes.remove();
        writing = true;
        boolean accepted;
        if (Build.VERSION.SDK_INT >= 33) {
            accepted = gatt.writeCharacteristic(command, packet, BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT)
                    == BluetoothStatusCodes.SUCCESS;
        } else {
            command.setWriteType(BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT);
            command.setValue(packet);
            accepted = gatt.writeCharacteristic(command);
        }
        if (!accepted) fail("Bluetooth was busy or disconnected. Reconnect to resume.");
    }

    private void close() {
        stopScan();
        ready = writing = false;
        pairing = null;
        writes.clear();
        command = null;
        BluetoothGatt old = gatt;
        gatt = null;
        if (old != null) {
            if (permissions()) old.disconnect();
            old.close();
        }
        event("connected", false);
    }

    public class Bridge {
        @JavascriptInterface public void scan() { handler.post(MainActivity.this::scan); }
        @JavascriptInterface public void connect(String address) { handler.post(() -> MainActivity.this.connect(address)); }
        @JavascriptInterface public void disconnect() { handler.post(MainActivity.this::close); }
        @JavascriptInterface public void send(String json) {
            try {
                JSONArray list = new JSONArray(json);
                if (list.length() < 2 || list.length() > 20 || list.getInt(0) != 1) return;
                byte[] packet = new byte[list.length()];
                for (int i = 0; i < packet.length; i++) packet[i] = (byte) list.getInt(i);
                handler.post(() -> enqueue(packet));
            } catch (org.json.JSONException ignored) { }
        }
    }

    @Override public void onRequestPermissionsResult(int code, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(code, permissions, results);
        if (code == 1 && permissions()) scan();
        else event("error", "Nearby devices permission is required. Enable it in Android app settings.");
    }
    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request == 2 && result == RESULT_OK) scan();
    }
    @Override protected void onResume() {
        super.onResume();
        foreground = true;
        if (pairing != null && permissions() && pairing.getBondState() == BluetoothDevice.BOND_BONDED) openGatt(pairing);
    }
    @Override protected void onPause() {
        foreground = false;
        if (pairing == null) close();
        else stopScan();
        super.onPause();
    }
    @Override protected void onDestroy() {
        close();
        unregisterReceiver(receiver);
        web.removeJavascriptInterface("Luna");
        web.destroy();
        web = null;
        super.onDestroy();
    }
}
