import asyncio
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
    slug: str  # n
    name: str  # ot

    # for bulk/polling sensors :3
    def to_discovery_json(self, unique_id, sensor_endpoint):
        return {
            "platform": "sensor",
            "unique_id": f"{unique_id}_{self.slug}",
            "name": self.name,
            "state_topic": f"blueairsensor/{sensor_endpoint}",
            "value_template": f"{{{{ value_json | selectattr('n', 'eq', '{self.slug}') | map(attribute='v') | first }}}}",
            "state_class": "measurement",
            # have to set this to something that isn't whitespace or else it wont treat it as a number
            # "unit_of_measurement": "​",
        }


@dataclass
class Action:
    slug: str  # n
    name: str  # ot


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

    def to_discovery_json(self, unique_id, sensor_endpoint, action_endpoint):
        return {
            "platform": self.ha_type(),
            "unique_id": f"{unique_id}_{self.slug}",
            "name": self.name
        } \
            | ({
                   "state_topic": f"blueairsensor/{sensor_endpoint}",
                   "value_template": f"{{{{ value_json.current.state.reported['{self.slug}'] }}}}",
                   "payload_on": True,
                   "payload_off": False,
                   # "value_template": f"{{{{ value_json.current.state.reported['{self.slug}'] }}}}",
               } if self.sensor is not None else {}) \
            | ({
                   "command_topic": f"blueairaction/{action_endpoint}",
                   "command_template": f'{{ "state": {{ "desired": {{ "{self.slug}": {{{{"true" if value else "false"}}}} }} }} }}',
               } if self.action is not None else {})


@dataclass
class State:
    slug: str  # n
    time: datetime.datetime  # t
    value: str | bool  # v for int, vb for bool


@dataclass
class Schema:
    information: Information

    # sensors: dict[str, Sensor]
    states_endpoint: str
    actions_endpoint: str
    capabilities: dict[str, Capability]


    poll_endpoint: str
    polling_sensors: dict[str, Sensor]

    initial_state: dict[str, State]


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

        # TODO: much of this schema is only useful to the device itself, the only endpoints we have access to are the
        #  polling ones, and the shadow topic which basically returns what the states key has
        #  basically i need to collect things into:
        #  - document objects: visible on the shadow and states key, maybe has an action maybe doesnt
        #  - polling objects: only visible on the polling endpoints, no action, state only
        #  - pure actions: in the actions key but with no capability, action with NO state
        #  there is useful info in the sensors thing, like i can get a slightly more human readable name of each sensor from there

        capabilities = {}

        for slug, raw_cap in self.raw_info["configuration"]["dc"].items():
            cap = Capability(
                slug=slug,
                data_type=int if raw_cap["t"] == "integer" else bool if raw_cap["t"] == "boolean" else None,
            )
            if "a" in raw_cap:  # action
                if raw_cap["a"] in self.raw_info["configuration"]["da"]:
                    raw_action = self.raw_info["configuration"]["da"][raw_cap["a"]]
                    cap.action = Action(
                        slug=raw_action["n"],
                        name=raw_action["ot"],
                    )
            if "s" in raw_cap:  # action
                if raw_cap["s"] in self.raw_info["configuration"]["ds"]:
                    raw_sensor = self.raw_info["configuration"]["ds"][raw_cap["s"]]
                    cap.sensor = Sensor(
                        slug=raw_sensor["n"],
                        name=raw_sensor["ot"],
                    )
            # mentally awesome way to either get a unique name or join
            # no clue if action/sensor ever differs, but eh futureproofing i suppose
            cap.name = (' + '.join({cap.action.name if cap.action is not None else None,
                                    cap.sensor.name if cap.sensor is not None else None} - {None})) or slug

            if cap.action or cap.sensor:
                # filters out stupid shit like firmware version that we Already Have
                capabilities[slug] = cap

        polling_sensors = {}
        for raw_name in self.raw_info["configuration"]["ds"]["rt5s"]["sn"]:
            if raw_name in self.raw_info["configuration"]["ds"]:
                raw_sensor = self.raw_info["configuration"]["ds"][raw_name]
                sensor = Sensor(
                    slug=raw_sensor["n"],
                    name=raw_sensor["ot"],
                )
            else:
                sensor = Sensor(
                    slug=raw_name,
                    name=raw_name
                )
            polling_sensors[raw_name] = sensor

        self.schema = Schema(
            information=information,

            capabilities=capabilities,
            polling_sensors=polling_sensors,

            initial_state=self.raw_info["states"],

            poll_endpoint=self.raw_info["configuration"]["ds"]["rt5s"]["tn"],
            # no this isnt anywhere in the damn api but this is literally also how BA does it in the app fuck off
            states_endpoint=f"$aws/things/{information.id}/shadow/update/documents",
            actions_endpoint=f"$aws/things/{information.id}/shadow/update"
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
                              key: cap.to_discovery_json(
                                  f"blueairhamqtt_{self.schema.information.id.replace('-', '_')}",
                                  self.schema.states_endpoint, self.schema.actions_endpoint) for key, cap
                              in self.schema.capabilities.items()
                          } | {
                              key: sen.to_discovery_json(
                                  f"blueairhamqtt_{self.schema.information.id.replace('-', '_')}",
                                  self.schema.poll_endpoint) for key, sen
                              in self.schema.polling_sensors.items()
                          }
        }

        await mqtt.async_publish(hass,
                                 f"homeassistant/device/blueairhamqtt/blueairhamqtt_{self.schema.information.id.replace('-', '_')}/config",
                                 json.dumps(msg), retain=True)

    async def subscribe_to_updates(self, mqtt_client: AwsMQTT):

        # i tested it, these are the only endpoints that are valid.
        # every other subscription resets the entire damn connection, thanks amerzon!!
        topics_to_subscribe = [
            (self.schema.poll_endpoint, 0),
            (self.schema.states_endpoint, 0)
        ]

        mqtt_client.client.subscribe(topics_to_subscribe)
