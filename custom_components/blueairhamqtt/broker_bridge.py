from typing import Any

from paho.mqtt.client import Client, MQTTMessage

from homeassistant.components import mqtt
from homeassistant.components.mqtt import ReceiveMessage
from .mqtt_aws import AwsMQTT
from homeassistant.core import HomeAssistant, _LOGGER


async def bridge_brokers(
        hass: HomeAssistant,
        source_broker: AwsMQTT,
):
    source_broker.client.enable_bridge_mode()
    await mqtt.async_wait_for_mqtt_client(hass)

    async def ha_to_aws_callback(msg: ReceiveMessage):
        topic = msg.topic.replace("blueairaction/", "")
        print("ha -> aws", topic, msg.payload)
        source_broker.client.publish(
            topic=topic,
            payload=msg.payload,
            qos=msg.qos,
            retain=msg.retain,
        )

    await mqtt.async_subscribe(hass, "blueairaction/#", ha_to_aws_callback)

    def aws_to_ha_callback(client: Client, userdata: Any, msg: MQTTMessage):
        print("aws -> ha", msg.topic, msg.payload)
        mqtt.publish(
            hass,
            topic=f"blueairsensor/{msg.topic}",
            payload=msg.payload,
            qos=msg.qos,
            retain=msg.retain,
        )

    # source_broker.client.subscribe("#", 0)
    source_broker.client.on_message = aws_to_ha_callback
