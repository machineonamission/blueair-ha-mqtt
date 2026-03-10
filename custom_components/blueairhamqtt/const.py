# Configuration Constants
from enum import Enum
from homeassistant.const import Platform

DOMAIN: str = "blueairhamqtt"

# Integration Setting Constants
CONFIG_FLOW_VERSION: int = 2


REGION_EU = "eu"
REGION_USA = "us"
REGION_AU = "au"
REGION_CN = "cn"
REGIONS = [REGION_USA, REGION_EU, REGION_AU, REGION_CN]

SENSITIVE_FIELD_NAMES = [
    "username",
    "password",
]

DATA_DEVICES: str = "api_devices"
DATA_AWS_DEVICES: str = "api_aws_devices"
