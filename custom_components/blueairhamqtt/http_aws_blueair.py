import functools

from logging import getLogger
from typing import Any
from aiohttp import ClientSession, ClientResponse, FormData

from .const import SENSITIVE_FIELD_NAMES

# #               cn:  a2du5f95w7oz2a.ats.iot.cn-north-1.amazonaws.com.cn"
# #               us:    "a3tpdpjvxk6yog-ats.iot.us-east-2.amazonaws.com"
# #               other:  a3tpdpjvxk6yog-ats.iot.eu-west-1.amazonaws.com"

AWS_APIKEYS = {
    "us": {
        "gigyaRegion": "accounts.us1.gigya.com",
        "restApiId": "on1keymlmh",
        "awsRegion": "us-east-2.amazonaws.com",
        "mqttBroker": "a3tpdpjvxk6yog-ats.iot.us-east-2.amazonaws.com",
        "apiKey": "3_-xUbbrIY8QCbHDWQs1tLXE-CZBQ50SGElcOY5hF1euE11wCoIlNbjMGAFQ6UwhMY",
    },
    "eu": {
        "gigyaRegion": "accounts.eu1.gigya.com",
        "restApiId": "hkgmr8v960",
        "awsRegion": "eu-west-1.amazonaws.com",
        "mqttBroker": "a3tpdpjvxk6yog-ats.iot.eu-west-1.amazonaws.com",
        "apiKey": "3_qRseYzrUJl1VyxvSJANalu_kNgQ83swB1B9uzgms58--5w1ClVNmrFdsDnWVQQCl",
    },
    "cn": {
        "gigyaRegion": "accounts.cn1.sapcdm.cn",
        "restApiId": "ftbkyp79si",
        "awsRegion": "cn-north-1.amazonaws.com.cn",
        "mqttBroker": "a2du5f95w7oz2a.ats.iot.cn-north-1.amazonaws.com.cn",
        "apiKey": "3_h3UEfJnA-zDpFPR9L4412HO7Mz2VVeN4wprbWYafPN1gX0kSnLcZ9VSfFi7bEIIU",
    },
    "au": {
        "gigyaRegion": "accounts.au1.gigya.com",
        "restApiId": "hkgmr8v960",
        "awsRegion": "eu-west-1.amazonaws.com",
        "apiKey": "3_Z2N0mIFC6j2fx1z2sq76R3pwkCMaMX2y9btPb0_PgI_3wfjSJoofFnBbxbtuQksN",
    },
}


def clean_dictionary_for_logging(dictionary: dict[str, Any]) -> dict[str, Any]:
    mutable_dictionary = dictionary.copy()
    for key in dictionary:
        if key.lower() in SENSITIVE_FIELD_NAMES:
            mutable_dictionary[key] = "***"
        if type(mutable_dictionary[key]) is dict:
            mutable_dictionary[key] = clean_dictionary_for_logging(
                mutable_dictionary[key].copy()
            )
        if type(mutable_dictionary[key]) is list:
            new_array = []
            for item in mutable_dictionary[key]:
                if type(item) is dict:
                    new_array.append(clean_dictionary_for_logging(item.copy()))
                else:
                    new_array.append(item)
            mutable_dictionary[key] = new_array

    return mutable_dictionary


def request_with_logging(func):
    async def request_with_logging_wrapper(*args, **kwargs):
        url = kwargs["url"]
        request_message = f"sending {url} request"
        headers = kwargs.get("headers")
        if headers is not None:
            request_message = request_message + f"headers: {headers}"
        params = kwargs.get("params")
        if params is not None:
            request_message = request_message + f"params: {params}"
        json_body = kwargs.get("json_body")
        if json_body is not None:
            request_message = (
                    request_message
                    + f"sending {url} request with {clean_dictionary_for_logging(json_body)}"
            )
        _LOGGER.debug(request_message)
        response = await func(*args, **kwargs)
        _LOGGER.debug(
            f"response headers:{clean_dictionary_for_logging(response.headers)}"
        )
        _LOGGER.debug(f"response status: {response.status}")
        try:
            response_json = await response.json(content_type=None)
            _LOGGER.debug(
                f"response json: {clean_dictionary_for_logging(response_json)}"
            )
        except Exception:
            response_text = await response.text()
            _LOGGER.debug(f"response raw: {response_text}")
        return response

    return request_with_logging_wrapper


from aiohttp import ClientError


class BlueAirAPIError(ClientError):
    pass


class LoginError(BlueAirAPIError):
    pass


class SessionError(BlueAirAPIError):
    pass


_LOGGER = getLogger(__name__)


# credit to blueair_api

def request_with_active_session(func):
    @functools.wraps(func)
    async def request_with_active_session_wrapper(*args, **kwargs) -> ClientResponse:
        _LOGGER.debug("session")
        try:
            return await func(*args, **kwargs)
        except SessionError:
            _LOGGER.debug("got invalid session, attempting to repair and resend")
            self = args[0]
            self.session_token = None
            self.session_secret = None
            self.access_token = None
            self.jwt = None
            response = await func(*args, **kwargs)
            return response

    return request_with_active_session_wrapper


def request_with_errors(func):
    @functools.wraps(func)
    async def request_with_errors_wrapper(*args, **kwargs) -> ClientResponse:
        _LOGGER.debug("checking for errors")
        response: ClientResponse = await func(*args, **kwargs)
        status_code = response.status
        try:
            response_json = await response.json(content_type=None)
            if response_json is not None:
                if "statusCode" in response_json:
                    _LOGGER.debug("response json found, checking status code from response")
                    status_code = response_json["statusCode"]
        except Exception as e:
            _LOGGER.error(f"Error parsing response for errors {e}")
            raise e
        if status_code == 200:
            _LOGGER.debug("response 200")
            return response
        if 400 <= status_code <= 500:
            _LOGGER.debug(f"auth error, {status_code}")
            url = kwargs["url"]
            response_text = await response.text()
            if "accounts.login" in url:
                _LOGGER.debug("login error")
                raise LoginError(response_text)
            else:
                _LOGGER.debug("session error")
                raise SessionError(response_text)
        raise ValueError(f"unknown status code {status_code}")

    return request_with_errors_wrapper


class HttpAwsBlueair:
    def __init__(
            self,
            username: str,
            password: str,
            region: str = "us",
            client_session: ClientSession | None = None,
    ):
        self.username = username
        self.password = password
        self.region = region

        self.session_token = None
        self.session_secret = None

        self.access_token = None

        self.jwt = None

        self.ca_signature: str | None = None
        self.ca_name: str | None = None
        self.ca_token: str | None = None

        if client_session is None:
            self.api_session = ClientSession(raise_for_status=False)
        else:
            self.api_session = client_session

    async def cleanup_client_session(self):
        await self.api_session.close()

    @request_with_errors
    @request_with_logging
    async def _get_request_with_logging_and_errors_raised(
            self, url: str, headers: dict | None = None, params: dict | None = None
    ) -> ClientResponse:
        return await self.api_session.get(url=url, headers=headers, params=params)

    @request_with_errors
    @request_with_logging
    async def _post_request_with_logging_and_errors_raised(
            self,
            url: str,
            json_body: dict | None = None,
            form_data: FormData | None = None,
            headers: dict | None = None,
    ) -> ClientResponse:
        return await self.api_session.post(
            url=url, data=form_data, json=json_body, headers=headers
        )

    async def refresh_session(self) -> None:
        _LOGGER.debug("refresh_session")
        url = f"https://{AWS_APIKEYS[self.region]['gigyaRegion']}/accounts.login"
        form_data = FormData()
        form_data.add_field("apikey", AWS_APIKEYS[self.region]["apiKey"])
        form_data.add_field("loginID", self.username)
        form_data.add_field("password", self.password)
        form_data.add_field("targetEnv", "mobile")
        response: ClientResponse = (
            await self._post_request_with_logging_and_errors_raised(
                url=url, form_data=form_data
            )
        )
        response_json = await response.json(content_type="text/javascript")
        self.session_token = response_json["sessionInfo"]["sessionToken"]
        self.session_secret = response_json["sessionInfo"]["sessionSecret"]

    async def refresh_jwt(self) -> None:
        _LOGGER.debug("refresh_jwt")
        if self.session_token is None or self.session_secret is None:
            await self.refresh_session()
        url = f"https://{AWS_APIKEYS[self.region]['gigyaRegion']}/accounts.getJWT"
        form_data = FormData()
        form_data.add_field("oauth_token", self.session_token)
        form_data.add_field("secret", self.session_secret)
        form_data.add_field("targetEnv", "mobile")
        response: ClientResponse = (
            await self._post_request_with_logging_and_errors_raised(
                url=url, form_data=form_data
            )
        )
        response_json = await response.json(content_type="text/javascript")
        self.jwt = response_json["id_token"]

    async def refresh_access_token(self) -> None:
        _LOGGER.debug("refresh_access_token")
        if self.jwt is None:
            await self.refresh_jwt()
        url = f"https://{AWS_APIKEYS[self.region]['restApiId']}.execute-api.{AWS_APIKEYS[self.region]['awsRegion']}/prod/c/login"
        headers = {"idtoken": self.jwt, "authorization": f"Bearer {self.jwt}"}
        response: ClientResponse = (
            await self._post_request_with_logging_and_errors_raised(
                url=url, headers=headers
            )
        )
        response_json = await response.json()

        # MQTT auth
        self.ca_name = response_json['ba_X-Amz-CustomAuthorizer-Name']
        self.ca_token = response_json['ba_X-Amz-CustomAuthorizer-Token']
        self.ca_signature = response_json['ba_X-Amz-CustomAuthorizer-Signature']

        self.access_token = response_json["access_token"]

    async def get_access_token(self) -> str:
        _LOGGER.debug("get_access_token")
        if self.access_token is None:
            await self.refresh_access_token()
        assert self.access_token is not None
        return self.access_token

    @request_with_active_session
    async def devices(self) -> dict[str, Any]:
        _LOGGER.debug("devices")
        url = f"https://{AWS_APIKEYS[self.region]['restApiId']}.execute-api.{AWS_APIKEYS[self.region]['awsRegion']}/prod/c/registered-devices"
        headers = {
            "Authorization": f"Bearer {await self.get_access_token()}",
        }
        response: ClientResponse = (
            await self._get_request_with_logging_and_errors_raised(
                url=url, headers=headers
            )
        )
        response_json = await response.json()
        return response_json["devices"]

    # @request_with_active_session
    # async def device_sensors(self, device_name, device_uuid, duration: timedelta = timedelta(minutes=5)):
    #     url = f"https://{AWS_APIKEYS[self.region]['restApiId']}.execute-api.{AWS_APIKEYS[self.region]['awsRegion']}/prod/c/{device_name}/r/telemetry/5m/historical"
    #     headers = {
    #         "Authorization": f"Bearer {await self.get_access_token()}",
    #     }
    #     params = {
    #         "did": device_uuid,
    #         "from": int((datetime.now(timezone.utc) - duration).timestamp()),
    #         "to": int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()),
    #         "s": ["pm1", "pm2_5", "pm10", "tVOC", "hcho", "h", "t", "fsp0"]
    #     }
    #     response: ClientResponse = (
    #         await self._get_request_with_logging_and_errors_raised(
    #             url=url, headers=headers, params=params
    #         )
    #     )
    #     response_json = await response.json()
    #     return response_json

    @request_with_active_session
    async def device_info(self, device_name, device_uuid) -> dict[str, Any]:
        _LOGGER.debug("device_info")
        url = f"https://{AWS_APIKEYS[self.region]['restApiId']}.execute-api.{AWS_APIKEYS[self.region]['awsRegion']}/prod/c/{device_name}/r/initial"
        headers = {
            "Authorization": f"Bearer {await self.get_access_token()}",
        }
        json_body = {
            "eventsubscription": {"include": [{"filter": {"o": f"= {device_uuid}, "}}]},
            "deviceconfigquery": [
                {
                    "id": device_uuid,
                    "r": {
                        "r": [
                            "sensors",
                        ],
                    },
                },
            ],
            "includestates": True
        }
        response: ClientResponse = (
            await self._post_request_with_logging_and_errors_raised(
                url=url, headers=headers, json_body=json_body
            )
        )
        response_json = await response.json()
        return response_json["deviceInfo"][0]
