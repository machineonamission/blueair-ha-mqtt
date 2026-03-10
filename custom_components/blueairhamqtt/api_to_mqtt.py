from .device import Device
from .http_aws_blueair import HttpAwsBlueair
from aiohttp import ClientSession

from .mqtt_aws import AwsMQTT


async def api_to_mqtt(
        username: str,
        password: str,
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

    broker = AwsMQTT(api)
    await broker.connect()
    # print(api)
    # api_devices = await api.devices()
    # print(api_devices)
