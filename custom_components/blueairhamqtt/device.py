import datetime
from functools import cached_property
from typing import Any
from dataclasses import dataclass
from logging import getLogger
from json import dumps
import kpn_senml

from .http_aws_blueair import HttpAwsBlueair
from dataclasses import dataclass, field

_LOGGER = getLogger(__name__)

type AttributeType[T] = T | None


@dataclass
class Firmware:
    current_version: str  # cfv (is this current?)
    mcu_version: str  # mfv
    wifi_version: str  # ofv


@dataclass
class Information:
    name: str
    current_mac_address: str  # cma
    model_number: str  # sku
    serial_number: str  # ds
    firmware: Firmware
    id: str


#
@dataclass
class Sensor:
    mqtt_topic_name: str  # tn
    slug: str  # n
    time_to_live: int  # ttl
    name: str  # ot
    enabled: bool  # e
    # may be 0 if disabled, otherwise is time in ms
    polling_interval: int | None  # i
    sensor_names: list[str]  # sn


@dataclass
class Action:
    slug: str  # n
    name: str  # ot
    mqtt_topic_name: str  # tn
    enabled: bool  # e


@dataclass
class Capability:
    slug: str  # n
    action: Action | None  # a (maps to slug)
    sensor: Sensor | None  # s (maps to slug)
    data_type: type  # t


@dataclass
class State:
    slug: str  # n
    time: datetime.datetime  # t
    value: str | bool  # v for int, vb for bool


@dataclass
class Schema:
    information: Information
    sensors: dict[str, Sensor]
    polling_sensors: dict[str, Sensor]
    actions: dict[str, Action]
    capabilities: dict[str, Capability]
    states: dict[str, State]


@dataclass(slots=True)
class Device:
    @classmethod
    async def create_device(cls, api, uuid, name, mac, type_name):
        _LOGGER.debug("UUID:" + uuid)
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
    raw_info: dict[str, Any] = field(repr=False, init=False)
    schema: None | Schema = None

    uuid: str | None = None
    name: str | None = None
    name_api: str | None = None
    mac: str | None = None
    type_name: str | None = None

    async def build_schema(self):
        _LOGGER.debug(f"refreshing blueair device aws: {self}")
        self.raw_info = await self.api.device_info(self.name_api, self.uuid)

        print(self.raw_info)
        conf = self.raw_info["configuration"]
        firmware = Firmware(
            current_version=conf["di"]["cfv"],
            mcu_version=conf["di"]["mfv"],
            wifi_version=conf["di"]["ofv"],
        )

        information = Information(
            name=conf["di"]["name"],
            current_mac_address=conf["di"]["cma"],
            model_number=conf["di"]["sku"],
            serial_number=conf["di"]["ds"],
            firmware=firmware,
            id=self.raw_info["id"],
        )

        sensors = {
            slug:
            Sensor(
                mqtt_topic_name=raw_sensor["tn"],
                slug=raw_sensor["n"],
                time_to_live=raw_sensor["ttl"],
                name=raw_sensor["ot"],
                sensor_names=raw_sensor.get("sn", None),
                enabled=raw_sensor["e"],
                polling_interval=raw_sensor["i"] if raw_sensor["i"] != 0 else None,
            )
            for slug, raw_sensor in conf["ds"].items() if slug not in ["rt1s", "rt5s", "rt5m", "b5m"]
        }

        polling_sensors = {
            slug:
            Sensor(
                mqtt_topic_name=raw_sensor["tn"],
                slug=raw_sensor["n"],
                time_to_live=raw_sensor["ttl"],
                name=raw_sensor["ot"],
                sensor_names=raw_sensor.get("sn", None),
                enabled=raw_sensor["e"],
                polling_interval=raw_sensor["i"] if raw_sensor["i"] != 0 else None,
            )
            for slug, raw_sensor in conf["ds"].items() if slug in ["rt1s", "rt5s", "rt5m", "b5m"]
        }

        actions = {
            slug:
            Action(
                mqtt_topic_name=raw_action["tn"],
                slug=raw_action["n"],
                name=raw_action["ot"],
                enabled=raw_action["e"],
            )
            for slug, raw_action in conf["da"].items()
        }

        capabilities = {
            slug:
                Capability(
                    slug=raw_cap["n"],
                    data_type=int if raw_cap["t"] == "integer" else bool,
                    action=actions.get(raw_cap.get("a", None), None),
                    sensor=sensors.get(raw_cap.get("s", None), None),
                )
            for slug, raw_cap in conf["dc"].items()
        }

        states = {
            raw_state["n"]:
                State(
                    slug=raw_state["n"],
                    value=raw_state["v"] if "v" in raw_state else raw_state["vb"],
                    time=datetime.datetime.fromtimestamp(raw_state["t"], datetime.timezone.utc)
                )
            for raw_state in self.raw_info["states"]
        }

        self.schema = Schema(
            information=information,
            sensors=sensors,
            actions=actions,
            capabilities=capabilities,
            states=states,
        )

        return self.schema
