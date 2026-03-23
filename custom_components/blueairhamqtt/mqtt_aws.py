from typing import Any, Callable, Awaitable, Coroutine

from paho.mqtt.enums import MQTTErrorCode

from homeassistant.core import HomeAssistant
from .http_aws_blueair import HttpAwsBlueair, AWS_APIKEYS
import paho.mqtt.client as mqtt
import uuid
import json
import ssl
import asyncio


class AwsMQTT:
    def __init__(self, api: HttpAwsBlueair):
        self.api: HttpAwsBlueair = api
        self.client: mqtt.Client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=str(uuid.uuid7()),
            transport="websockets",
            clean_session=True
        )
        self.connect_callbacks: list[Callable[[], Coroutine[None, None, None]]] = []

    async def run_on_connect(self):
        for callback in self.connect_callbacks:
            await callback()

    async def connect(self, hass: HomeAssistant):
        def on_log(client, userdata, level, buf):
            print(f"[LOG] {buf}")

        # to return once connected
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        def on_connect(client, userdata, flags, reason_code, properties):
            if reason_code == 0:
                print("\n[+] Connected successfully.")
                if not future.done():
                    future.set_result(None)
            else:
                print(f"\n[-] Connection failed with code {reason_code}")
                future.set_exception(Exception(f"Connection failed with code {reason_code}"))

            loop.create_task(self.run_on_connect())

        # def on_message(client, userdata, msg):
        #     print(f"\n[<<< INCOMING MSG <<<] Topic: {msg.topic}")
        #     try:
        #         payload = json.loads(msg.payload.decode('utf-8'))
        #         print(json.dumps(payload, indent=2))
        #     except json.JSONDecodeError:
        #         print(msg.payload.decode('utf-8'))

        def on_disconnect(*args, **kwargs):
            print("on_disconnect", args, kwargs)

        self.client.on_log = on_log
        self.client.on_connect = on_connect
        self.client.on_disconnect = on_disconnect
        self.client.on_connect_fail = print

        self.client.subscribe_callback()

        # self.client.on_message = on_message
        #
        # # Set up TLS
        def setup_ssl():
            ssl_context = ssl.create_default_context()
            self.client.tls_set_context(ssl_context)

        await hass.async_add_executor_job(setup_ssl)

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
