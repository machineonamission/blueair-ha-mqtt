from functools import cached_property
from typing import Any

from logging import getLogger
from json import dumps
import kpn_senml

from .http_aws_blueair import HttpAwsBlueair
from dataclasses import dataclass, field

_LOGGER = getLogger(__name__)

type AttributeType[T] = T | None


@dataclass(slots=True)
class Device:
    @classmethod
    async def create_device(cls, api, uuid, name, mac, type_name):
        _LOGGER.debug("UUID:"+uuid)
        device_aws = cls(
            api=api,
            uuid=uuid,
            name_api=name,
            mac=mac,
            type_name=type_name,
        )
        await device_aws.build_schema()
        _LOGGER.debug(f"create_device blueair device_aws: {device_aws}")
        return device_aws

    api: HttpAwsBlueair = field(repr=False)
    raw_info : dict[str, Any] = field(repr=False, init=False)

    uuid : str | None = None
    name : str | None = None
    name_api : str | None = None
    mac : str | None = None
    type_name : str | None = None

    async def build_schema(self):
        _LOGGER.debug(f"refreshing blueair device aws: {self}")
        self.raw_info = await self.api.device_info(self.name_api, self.uuid)


        print(self.raw_info)
