from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant
from .broker_bridge import bridge_brokers
from .device import Device
from .http_aws_blueair import HttpAwsBlueair
from aiohttp import ClientSession

from .mqtt_aws import AwsMQTT
from .const import DOMAIN


async def setup_mqtt(
        username: str,
        password: str,
        hass: HomeAssistant,
        region: str = "us",
        client_session: ClientSession | None = None,
):
    api = HttpAwsBlueair(
        username=username,
        password=password,
        region=region,
        client_session=client_session,
    )

    await api.refresh_access_token()

    api_devices = await api.devices()
    devices = [await Device.create_device(
        api=api,
        uuid=api_device["uuid"],
        name=api_device["name"],
        mac=api_device["mac"],
        type_name=api_device["type"],
    ) for api_device in api_devices]

    broker = await get_or_init_broker(hass, api)

    async def on_connect():
        for device in devices:
            await device.broadcast_discovery(hass)
            await device.subscribe_to_updates(broker)

    broker.connect_callbacks.append(on_connect)
    await on_connect()


async def get_or_init_broker(hass: HomeAssistant, api: HttpAwsBlueair) -> AwsMQTT:
    if "broker" in hass.data[DOMAIN]:
        return hass.data[DOMAIN]["broker"]
    else:
        broker = AwsMQTT(api)
        hass.data[DOMAIN]["broker"] = broker
        await bridge_brokers(hass, broker)
        await broker.connect(hass)
        return broker
