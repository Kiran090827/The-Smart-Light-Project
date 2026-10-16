"""Smart Light bridge for the nikki Streams phone SDK."""
import asyncio
import json
import os
from pathlib import Path

from aiohttp import web
from nikki_streams import SDK

PHONE_ADDRESS = os.getenv("PHONE_ADDRESS", "10.172.21.252:3000")
SESSION_ID = os.getenv("NIKKI_SESSION_ID", "")
PORT = int(os.getenv("PORT", "8080"))

clients: set[web.WebSocketResponse] = set()
device = None
connect_task = None
state = {"connected": False, "connecting": False, "lux": None, "threshold": 20.0, "automatic": True,
         "flashlight": False, "last_update": None, "error": None}
loop = None
sdk_initialized = False


async def publish():
    message = json.dumps({"type": "state", **state})
    for ws in tuple(clients):
        if not ws.closed:
            await ws.send_str(message)


async def set_flashlight(on: bool):
    if device is None or not state["connected"]:
        state["error"] = "Phone is not connected. Check the Streams session and phone connection."
        await publish()
        return
    if state["flashlight"] == on:
        return
    try:
        await device.set_light_status(on)
        state["flashlight"] = on
        state["error"] = None
    except Exception as exc:
        state["error"] = f"Flashlight command failed: {exc}"
    await publish()


def phone_callback(event):
    """SDK callback: adapt phone events into dashboard state."""
    if event.type == "statusChange":
        state["connected"] = event.data == "connected"
        state["connecting"] = False
        if not state["connected"]:
            state["flashlight"] = False
    elif event.type == "data":
        payload = event.data or {}
        sensor_data = payload.get("data", payload)
        lux = sensor_data.get("Light", sensor_data.get("light"))
        if isinstance(lux, (int, float)):
            state["lux"] = float(lux)
            state["last_update"] = payload.get("time")
            if state["automatic"]:
                loop.create_task(set_flashlight(state["lux"] < state["threshold"]))
    loop.create_task(publish())


async def index(_request):
    return web.FileResponse(Path(__file__).parent / "index.html")


async def websocket(request):
    ws = web.WebSocketResponse(heartbeat=25)
    await ws.prepare(request)
    clients.add(ws)
    await ws.send_str(json.dumps({"type": "state", **state}))
    async for message in ws:
        if message.type != web.WSMsgType.TEXT:
            continue
        try:
            command = json.loads(message.data)
        except json.JSONDecodeError:
            continue
        if command.get("type") == "threshold":
            state["threshold"] = max(0.0, min(2000.0, float(command.get("value", 20))))
            if state["automatic"] and state["lux"] is not None:
                asyncio.create_task(set_flashlight(state["lux"] < state["threshold"]))
        elif command.get("type") == "automatic":
            state["automatic"] = bool(command.get("value"))
            if state["automatic"] and state["lux"] is not None:
                asyncio.create_task(set_flashlight(state["lux"] < state["threshold"]))
        elif command.get("type") == "manual":
            state["automatic"] = False
            asyncio.create_task(set_flashlight(bool(command.get("value"))))
        elif command.get("type") == "connect":
            await configure_phone(command.get("sessionId", ""), command.get("phoneAddress", ""))
        await publish()
    clients.discard(ws)
    return ws


async def start_phone(app):
    global loop, connect_task
    loop = asyncio.get_running_loop()
    if not SESSION_ID:
        return
    state["connecting"] = True
    connect_task = asyncio.create_task(connect_phone())


async def configure_phone(session_id, phone_address):
    global SESSION_ID, PHONE_ADDRESS, connect_task
    session_id = str(session_id).strip()
    phone_address = str(phone_address).strip()
    if not session_id or not phone_address:
        state["error"] = "Enter both the Streams session ID and phone WebSocket address."
        return
    if sdk_initialized and session_id != SESSION_ID:
        state["error"] = "The Streams session is already initialized. Restart the bridge to switch sessions."
        return
    SESSION_ID = session_id
    PHONE_ADDRESS = phone_address.removeprefix("ws://").removeprefix("wss://")
    state["connecting"] = True
    state["error"] = None
    if connect_task is None or connect_task.done():
        connect_task = asyncio.create_task(connect_phone())


async def connect_phone():
    global device, sdk_initialized
    try:
        if not sdk_initialized:
            SDK.initialize(SESSION_ID)
            sdk_initialized = True
        while True:
            current_device = SDK.create_device(PHONE_ADDRESS, phone_callback)
            device = current_device
            state["connecting"] = True
            await publish()
            try:
                await current_device.connect()
                state["connecting"] = False
                state["error"] = None
                await publish()
                while current_device.is_connected:
                    await asyncio.sleep(0.5)
                state["error"] = "Phone connection lost. Retrying…"
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                state["connected"] = False
                state["connecting"] = False
                state["error"] = f"Phone connection failed: {exc}"
            finally:
                await current_device.disconnect()
            state["connecting"] = True
            await publish()
            await asyncio.sleep(3)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        state["connecting"] = False
        state["error"] = f"Phone bridge stopped: {exc}"
        await publish()


async def stop_phone(_app):
    if connect_task is not None and not connect_task.done():
        connect_task.cancel()
        try:
            await connect_task
        except asyncio.CancelledError:
            pass
    if device is not None:
        await device.disconnect()


app = web.Application()
app.router.add_get("/", index)
app.router.add_get("/ws", websocket)
app.on_startup.append(start_phone)
app.on_cleanup.append(stop_phone)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=PORT)
