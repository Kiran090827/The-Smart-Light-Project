# Smart Light

A live dashboard that connects the nikki Streams phone to a web page. Incoming ambient-light readings are compared with a lux threshold; when the reading falls below it, the app sends the phone's flashlight command and updates the dashboard.

## Run it

1. In the Streams app, create or open your session, connect the Android phone, and enable the **Light** sensor. Keep the phone and computer on the same local network. Use the current WebSocket address shown in Streams. The current configured address is `10.172.21.252:3000`; it may change when the phone or computer changes networks, so update `PHONE_ADDRESS` if it does.
2. Install Python 3.10 or newer, then from this folder run:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   $env:NIKKI_SESSION_ID = "YOUR_STREAMS_SESSION_ID"
   $env:PHONE_ADDRESS = "10.172.21.252:3000"
   py server.py
   ```

   Find the session ID in the Streams app. The provided guide does not include it; it is required by `SDK.initialize()` and should be kept private. The phone address is already set to the supplied address by default.
3. Start the bridge, then open it on the computer at [http://localhost:8080](http://localhost:8080). To use the dashboard on the phone, connect the phone and computer to the same Wi-Fi and open `http://<computer-wi-fi-ip>:8080` on the phone. The laptop's currently observed Wi-Fi IPv4 address is `10.172.21.60`, so its dashboard URL is [http://10.172.21.60:8080](http://10.172.21.60:8080). This address can change when the laptop reconnects to a network; use `ipconfig` and check **Wireless LAN adapter Wi-Fi** for the current IPv4 address. The bridge listens on the local network for this purpose; allow Python through Windows Firewall on **Private networks** if Windows asks. Keep this on a trusted local network.
4. In the dashboard's **Connect Nikki Streams** section, enter the session ID and the current WebSocket address shown by the Streams app, then tap **Connect phone**. The address field starts with the supplied address but can be changed if Streams shows a different one. You can connect from the computer or from the phone browser.

## How it works

```text
Phone light sensor → nikki Streams event → Python callback → lux threshold comparison
                                                    ↓
Web dashboard ← local WebSocket ← updated state ← flashlight command → phone
```

The Python bridge uses `SDK.initialize(session_id)`, creates a device for the phone address, and connects in a background task so the dashboard stays available while the phone connection is attempted. It retries the phone connection every three seconds after a failure or disconnect. It reads `Light` from each sensor event (lux), then calls `device.set_light_status(True)` below the threshold or `False` at/above it. The page receives sensor values and the last flashlight command successfully sent over a local WebSocket. The SDK does not return a separate hardware-state acknowledgment, so the displayed flashlight state reflects successful command delivery. The default threshold is **20 lux**; adjust it on the page. Automatic mode is enabled on startup. Manual control disables automation until it is re-enabled.

The dashboard reflects the requested flashlight state after the SDK command succeeds. Connection errors and command failures are shown in the page. Sensor event availability depends on enabling the Light sensor in Streams.
