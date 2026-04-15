import asyncio
import uuid
import json
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
import aiomqtt

from .models import SwitchCreate, Switch, SwitchStateUpdate

MQTT_BROKER = "localhost"
MQTT_PORT = 1883

# "Baza danych" w pamięci RAM na potrzeby projektu
switches_db = {}

# Słownik przechowujący eventy asynchroniczne dla oczekujących rejestracji
pending_registrations = {}

mqtt_client: aiomqtt.Client | None = None

async def listen_mqtt(client: aiomqtt.Client):
    """Nasłuchuje wiadomości MQTT w tle (potwierdzenia rejestracji)."""
    await client.subscribe("system/register/ack")
    async for message in client.messages:
        if message.topic.matches("system/register/ack"):
            payload = json.loads(message.payload.decode())
            switch_id = payload.get("uuid")
            # Jeśli czekamy na ten UUID, uwalniamy event
            if switch_id in pending_registrations:
                pending_registrations[switch_id].set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Zarządza połączeniem MQTT podczas startu i zatrzymania aplikacji FastAPI."""
    global mqtt_client
    try:
        async with aiomqtt.Client(hostname=MQTT_BROKER, port=MQTT_PORT) as client:
            mqtt_client = client
            task = asyncio.create_task(listen_mqtt(client))
            yield
            task.cancel()
    except Exception as e:
        print(f"Błąd połączenia MQTT: {e}")
        yield

app = FastAPI(lifespan=lifespan, title="Symulator Włączników Światła MQTT")

@app.post("/switches", response_model=Switch, status_code=201)
async def register_switch(switch_data: SwitchCreate):
    """Dodaje włącznik. Wymaga potwierdzenia (ACK) po MQTT od urządzenia."""
    if not mqtt_client:
        raise HTTPException(status_code=503, detail="Brak połączenia z brokerem MQTT")

    switch_id = str(uuid.uuid4())
    event = asyncio.Event()
    pending_registrations[switch_id] = event

    # Wysyłamy żądanie rejestracji do symulatora
    payload = json.dumps({"uuid": switch_id, "name": switch_data.name})
    await mqtt_client.publish("system/register", payload)

    # Czekamy maksymalnie 5 sekund na odpowiedź (ACK) z symulatora
    try:
        await asyncio.wait_for(event.wait(), timeout=5.0)
    except asyncio.TimeoutError:
        del pending_registrations[switch_id]
        raise HTTPException(status_code=408, detail="Urządzenie nie odpowiedziało w czasie.")

    del pending_registrations[switch_id]
    
    # Zapis do "bazy"
    new_switch = Switch(id=switch_id, name=switch_data.name)
    switches_db[switch_id] = new_switch
    
    return new_switch

@app.put("/switches/{switch_id}/state", response_model=Switch)
async def toggle_switch(switch_id: str, state_update: SwitchStateUpdate):
    """Włącza/wyłącza oświetlenie, wysyła sygnał po MQTT i liczy czas."""
    if switch_id not in switches_db:
        raise HTTPException(status_code=404, detail="Włącznik nie istnieje")
        
    switch = switches_db[switch_id]
    now = datetime.now(timezone.utc)

    # Logika zliczania czasu działania
    if state_update.is_on and not switch.is_on:
        switch.last_turned_on_at = now
    elif not state_update.is_on and switch.is_on:
        time_on = (now - switch.last_turned_on_at).total_seconds()
        switch.total_time_on_seconds += time_on
        switch.last_turned_on_at = None

    switch.is_on = state_update.is_on

    # Poinformowanie symulatora urządzenia o zmianie stanu
    command = "ON" if switch.is_on else "OFF"
    await mqtt_client.publish(f"device/{switch_id}/command", json.dumps({"state": command}))

    return switch

@app.get("/switches/{switch_id}/stats")
async def get_switch_stats(switch_id: str):
    """Zwraca statystyki czasu działania."""
    if switch_id not in switches_db:
        raise HTTPException(status_code=404, detail="Włącznik nie istnieje")
        
    switch = switches_db[switch_id]
    current_total = switch.total_time_on_seconds
    
    # Jeśli jest aktualnie włączony, doliczamy czas "w locie"
    if switch.is_on and switch.last_turned_on_at:
        now = datetime.now(timezone.utc)
        current_total += (now - switch.last_turned_on_at).total_seconds()
        
    return {
        "switch_id": switch_id, 
        "name": switch.name,
        "is_currently_on": switch.is_on,
        "total_seconds_on": round(current_total, 2)
    }