from .http_aws_blueair import HttpAwsBlueair, AWS_APIKEYS
import paho.mqtt.client as mqtt
import uuid
import json
import ssl
import asyncio

DEVICE_ID = "15eebc7e-5c42-4ce7-ab0d-ec936d09efae"

class AwsMQTT:
    def __init__(self, api: HttpAwsBlueair):
        self.api: HttpAwsBlueair = api
        self.client: mqtt.Client | None = None

    async def connect(self):
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=str(uuid.uuid7()),
            transport="websockets",
            clean_session=True  # TODO: mayyybe not?
        )

            # The exact Client ID verified by Frida
        def on_log(client, userdata, level, buf):
            print(f"[LOG] {buf}")

            # 1. Get the current event loop
        loop = asyncio.get_running_loop()

        # 2. Create a Future object
        future = loop.create_future()

        def on_connect(client, userdata, flags, reason_code, properties):
            if reason_code == 0:
                print("\n[+] Connected successfully.")

                # Subscribe to the exact state topic
                topic_state = f"d/{DEVICE_ID}/s/5s"
                print(f"[*] Subscribing to: {topic_state}")
                client.subscribe(topic_state)

                # Subscribe to the AWS Device Shadow topic
                topic_shadow = f"$aws/things/{DEVICE_ID}/shadow/update/documents"
                print(f"[*] Subscribing to: {topic_shadow}")
                client.subscribe(topic_shadow)
                future.set_result(None)
            else:
                print(f"\n[-] Connection failed with code {reason_code}")
                future.set_exception(Exception(f"Connection failed with code {reason_code}"))

        def on_message(client, userdata, msg):
            print(f"\n[<<< INCOMING MSG <<<] Topic: {msg.topic}")
            try:
                payload = json.loads(msg.payload.decode('utf-8'))
                print(json.dumps(payload, indent=2))
            except json.JSONDecodeError:
                print(msg.payload.decode('utf-8'))

        self.client.on_log = on_log
        self.client.on_connect = on_connect
        self.client.on_message = on_message
        #
        # # Set up TLS
        ssl_context = ssl.create_default_context()
        self.client.tls_set_context(ssl_context)

        custom_headers = {
            "X-Amz-CustomAuthorizer-Name": self.api.ca_name,
            "X-Amz-CustomAuthorizer-Signature": self.api.ca_signature,
            "X-Amz-CustomAuthorizer-Token": self.api.ca_token
        }

        # The path is just standard /mqtt now
        self.client.ws_set_options(path="/mqtt", headers=custom_headers)

        print("[*] Initiating connection...")
        self.client.connect_async(AWS_APIKEYS[self.api.region]["mqttBroker"], 443, 60)
        self.client.loop_start()

        return await future
