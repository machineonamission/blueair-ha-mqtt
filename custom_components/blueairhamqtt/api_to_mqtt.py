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

    broker = AwsMQTT(api)
    await broker.init()
    # print(api)
    # api_devices = await api.devices()
    # print(api_devices)
