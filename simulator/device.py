import asyncio
import aiomqtt
import json
import sys

MQTT_BROKER = "localhost"
MQTT_PORT = 1883

async def main():
    try:
        async with aiomqtt.Client(hostname=MQTT_BROKER, port=MQTT_PORT) as client:
            await client.subscribe("system/register")
            await client.subscribe("device/+/command")
            
            print("Symulator włączników uruchomiony. Czekam na komunikaty z FastAPI...\n")

            async for message in client.messages:
                topic = str(message.topic)
                payload_str = message.payload.decode()
                
                try:
                    payload = json.loads(payload_str)
                except json.JSONDecodeError:
                    continue

                if topic == "system/register":
                    switch_id = payload.get("uuid")
                    name = payload.get("name")
                    print(f"[REJESTRACJA] Wykryto próbę dodania włącznika: {name} ({switch_id})")
                    
                    await asyncio.sleep(0.5) # Symulacja opóźnienia sieci
                    
                    ack_payload = json.dumps({"uuid": switch_id})
                    await client.publish("system/register/ack", ack_payload)
                    print(f"[ACK] Wysłano potwierdzenie rejestracji dla: {switch_id}")

                # 2. Odbiór informacji o włączeniu/wyłączeniu
                elif topic.startswith("device/") and topic.endswith("/command"):
                    switch_id = topic.split("/")[1]
                    state = payload.get("state")
                    ikona = "💡" if state == "ON" else "🌑"
                    print(f"[STEROWANIE] Zmiana stanu włącznika {switch_id} -> {state} {ikona}")
                    
    except aiomqtt.exceptions.MqttError as e:
        print(f"Błąd połączenia z MQTT: {e}. Upewnij się, że broker (Mosquitto) działa.")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())