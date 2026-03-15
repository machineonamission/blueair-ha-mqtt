import copy
import datetime
import json
from functools import cached_property
from typing import Any
from dataclasses import dataclass
from logging import getLogger
from json import dumps
import kpn_senml

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant
from .http_aws_blueair import HttpAwsBlueair
from dataclasses import dataclass, field

from .mqtt_aws import AwsMQTT

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
    name: str | None = None  # artificial field, have to grab from action/sensor
    action: Action | None = None  # a (maps to slug)
    sensor: Sensor | None = None  # s (maps to slug)
    data_type: type | None = None  # t

    def ha_type(self):
        if self.sensor is not None and self.action is None:
            if self.data_type == int:
                return "sensor"
            else:
                return "binary_sensor"
        else:
            if self.data_type == int:
                return "number"
            else:
                if self.action is None:
                    return "button"
                else:
                    return "switch"

    def to_discovery_json(self, unique_id):
        return {
            "platform": self.ha_type(),
            "unique_id": f"{unique_id}_{self.slug}",
            "name": self.name
        } \
            | ({
                   # TODO: probably need a state and command template but we will see what happer with this
                   "state_topic": f"blueairsensor/{self.sensor.mqtt_topic_name}",
               } if self.sensor is not None else {}) \
            | ({
                   "command_topic": f"blueairaction/{self.action.mqtt_topic_name}",
               } if self.action is not None else {})


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
    all_capabilities: dict[str, Capability]
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
            # sometimes there's these weird pseudo sensors of the firmware version which we dont need as a fucking capability shut up
            if ("a" in raw_cap or "s" in raw_cap)
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

        # artificially add missing capabilities, easier if its all one data type

        sensors_missing_capability = set(sensors.keys()) - set(
            cap.sensor.slug for cap in capabilities.values() if cap.sensor is not None)
        actions_missing_capability = set(actions.keys()) - set(
            cap.action.slug for cap in capabilities.values() if cap.action is not None)

        all_capabilities = copy.deepcopy(capabilities)

        # deal with perhaps capabilities missing a sensor or action, or missing sensor/action duos that need to be assigned together

        for s in sensors_missing_capability:
            sensor = sensors[s]
            if s not in all_capabilities:
                all_capabilities[s] = Capability(
                    slug=s
                )
            if all_capabilities[s].sensor is None:
                all_capabilities[s].sensor = sensor

        for a in actions_missing_capability:
            action = actions[a]
            if a not in all_capabilities:
                all_capabilities[a] = Capability(
                    slug=a
                )
            if all_capabilities[a].action is None:
                all_capabilities[a].action = action
            if all_capabilities[a].data_type is None:
                # a seems to be some kind of default/suggested value, so its a good place to get a datatype
                all_capabilities[a].data_type = type(conf["da"][a]["a"])

        for cap_group in [capabilities, all_capabilities]:
            for cap in cap_group.values():
                if cap.name is None:
                    # mentally awesome way to either get a unique name or join the
                    cap.name = ' + '.join({cap.action.name if cap.action is not None else None,
                                           cap.sensor.name if cap.sensor is not None else None} - {None})
                if cap.data_type is None:
                    # many typeless actions are bools and its a decent default, idfk leave me alone shut up
                    cap.data_type = bool

        self.schema = Schema(
            information=information,
            sensors=sensors,
            actions=actions,
            capabilities=capabilities,
            all_capabilities=all_capabilities,
            polling_sensors=polling_sensors,
            states=states,
        )

        return self.schema

    async def broadcast_discovery(self, hass: HomeAssistant):
        msg = {
            "device": {
                # 'configuration_url': "",
                "connections": [["mac", self.schema.information.current_mac_address]],
                'identifiers': f"blueairhamqtt_{self.schema.information.id.replace('-', '_')}",
                'name': self.schema.information.name,
                'manufacturer': "BlueAir",
                # 'model': self.schema.information.model_number,
                'model_id': self.schema.information.model_number,
                # 'hw_version': "",
                'sw_version': self.schema.information.firmware.current_version,
                # 'suggested_area': "",
                'serial_number': self.schema.information.serial_number,
            },
            "origin": {
                "name": "blueair-ha-mqtt"
            },
            "components": {
                key: cap.to_discovery_json(f"blueairhamqtt_{self.schema.information.id.replace('-', '_')}") for key, cap
                in self.schema.all_capabilities.items()
            }
        }

        await mqtt.async_publish(hass,
                                 f"homeassistant/device/blueairhamqtt/blueairhamqtt_{self.schema.information.id.replace('-', '_')}/config",
                                 json.dumps(msg), retain=True)

    async def subscribe_to_updates(self, mqtt_client: AwsMQTT):

        # if cap.action is not None:
        #     mqtt_client.client.subscribe(cap.action.mqtt_topic_name)

        # topics = [cap.sensor.mqtt_topic_name
        #           for cap in self.schema.all_capabilities.values()
        #           if cap.sensor is not None and cap.sensor.enabled]
        # mqtt_client.client.subscribe(
        #         [(topic, 0) for topic in topics]
        #     )


        # fucking aws iot means i can only sub to these endpoints, but theyre good endpoints so
        topics_to_subscribe = [
            (f"d/{self.schema.information.id}/s/5s", 0),  # The 5-second telemetry firehose
            (f"$aws/things/{self.schema.information.id}/shadow/update/documents", 0)  # The Shadow updates
        ]

        mqtt_client.client.subscribe(topics_to_subscribe)

        # mqtt_client.client.subscribe(
        #     (f"d/{self.schema.information.id}/#",0)
        #     )
