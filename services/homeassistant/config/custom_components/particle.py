from __future__ import annotations

import functools
import logging
import time
from typing import Any
from typing import Dict
from typing import List

import requests
import voluptuous as vol
from homeassistant.const import CONF_PASSWORD
from homeassistant.const import CONF_USERNAME
from homeassistant.const import EVENT_HOMEASSISTANT_START
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers import config_validation as cv

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'particle'
REQUIREMENTS = ['requests']

DEFAULT_API_PREFIX = 'https://api.particle.io/v1'

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    }),
}, extra=vol.ALLOW_EXTRA)


PARTICLE_CLOUD = None


def setup(hass, config):
    """
    Set up the particle component
    """
    username = config[DOMAIN][CONF_USERNAME]
    password = config[DOMAIN][CONF_PASSWORD]

    # Connect to Particle Cloud
    global PARTICLE_CLOUD
    try:
        PARTICLE_CLOUD = ParticleCloud(username, password)
    except Exception:
        _LOGGER.exception('Exception received when connecting to Particle Cloud')
        return False
    else:
        device_ids = [device.device_id for device in PARTICLE_CLOUD.devices]
        _LOGGER.info(f'Particle connected with device IDs: {device_ids}')

    def stop_particle(event):
        pass

    def start_particle(event):
        hass.bus.listen_once(EVENT_HOMEASSISTANT_STOP, stop_particle)

    hass.bus.listen_once(EVENT_HOMEASSISTANT_START, start_particle)
    return True


DEFAULT_API_PREFIX = 'https://api.particle.io/v1'


class ParticleDevice:
    """
    Object representing a Particle device. Functions exposed by the device will be exposed as methods of this object.
    """
    def __init__(self, particle_cloud: ParticleCloud, device_id: str, name: str, serial_number: str) -> None:
        self.particle_cloud = particle_cloud
        self.device_id = device_id
        self.name = name
        self.serial_number = serial_number

        self._api_prefix = self.particle_cloud.api_prefix
        self._access_token = self.particle_cloud._access_token
        self._api_endpoint = self._api_prefix + f'/devices/{self.device_id}'

        self._get_device_info()

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} device_id="{self.device_id}", name="{self.name}">'

    def __dir__(self) -> List[str]:
        attrs = super().__dir__()
        attrs.extend(self.functions)
        return attrs

    def __getattr__(self, name: str) -> Any:
        if name in self.functions:
            return functools.partial(self.call_function, name)
        else:
            raise AttributeError(f'"{self.__class__.__name__}" object has no attribute "{name}"')

    def _get_device_info(self) -> Dict[str, Any]:
        """
        Gets more detailed device info for a given device ID

        :param device_id: device ID to get detailed info from
        """
        _LOGGER.debug('Getting extended device info...')

        params = {'access_token': self._access_token}
        resp = requests.get(self._api_endpoint, params=params)
        resp.raise_for_status()
        self._device_info = resp.json()

        self.variables = self._device_info['variables']
        self.functions = self._device_info['functions'] or []
        return self._device_info

    def ping(self, timeout: float = None) -> bool:
        """
        Ping the device to determine if it is online

        :param timeout: time to wait for ping request to return before returning False
        :return: True if the device is online, False if not
        """
        _LOGGER.debug('Pinging device...')

        params = {'access_token': self._access_token}
        try:
            resp = requests.put(f'{self._api_endpoint}/ping', params=params, timeout=timeout)
        except requests.exceptions.Timeout:
            _LOGGER.debug(f'Timeout received after {timeout} seconds when pinging device')
            return False

        resp.raise_for_status()
        return resp.json()['online']

    def call_function(self, func_name: str, argument: str = '') -> Any:
        """
        Calls a published function on the device

        :param func_name: name of function to call
        :param argument: argument to call function with. Will be converted to a str
        :raises AttributeError: if the device does not have a function named func_name
        :return: return value of function
        """
        if func_name not in self.functions:
            raise AttributeError(f'Device does not have function {func_name}()')

        _LOGGER.debug(f'Calling device function "{func_name}()" with argument "{argument}"')

        data = {'arg': str(argument)}
        params = {'access_token': self._access_token}
        resp = requests.post(f'{self._api_endpoint}/{func_name}', data=data, params=params)
        resp.raise_for_status()

        retval = resp.json()['return_value']
        _LOGGER.debug(f'Device function "{func_name}()" returned {retval}')
        return retval

    # TODO: not currently working correctly?
    def flash_firmware(self, source_filepath: str, failure_timeout: float = 120, ping_interval: float = 5) -> bool:
        """
        Flash device firmware from source code

        :param source_filepath: path to source code file
        :param failure_timeout: time to wait for device to come back online after flash before raising RuntimeError
        :param ping_interval: time between pings to device after flash to verify success
        :raises RunetimeError: if update does not complete successfully or device does not come back online before
                               failure_timeout
        """
        _LOGGER.debug(f'Flashing device firmware from {source_filepath}...')

        params = {'access_token': self._access_token}
        resp = requests.put(self._api_endpoint, params=params, files={'fw': source_filepath})
        resp.raise_for_status()

        status = resp.json()['status']
        if status != 'Update started':
            raise RuntimeError(f'Update failed to start with status: {status}')

        _LOGGER.debug('Waiting for device to come back online after FW update')
        device_online = False
        update_start_time = time.time()
        while (time.time() < (update_start_time + failure_timeout)) and not device_online:
            device_online = self.ping(timeout=ping_interval)

        if not device_online:
            raise RuntimeError(f'Device did not come back online within {failure_timeout} of firmware flash')

        _LOGGER.debug('Device back online after firmware update')
        _LOGGER.debug('Grabbing updated device info...')
        self._get_device_info()


class ParticleCloud:
    """
    Object representing the Particle Cloud
    """
    def __init__(self, username: str, password: str, api_prefix: str = DEFAULT_API_PREFIX) -> None:
        self.api_prefix = api_prefix
        self._access_token = self._login(username, password)    # TODO: does this need to be kept alive?
        _LOGGER.info('Logged into Particle Cloud')

        self.devices_by_device_id = self._get_devices()
        self.devices = list(self.devices_by_device_id.values())

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} w/ {len(self.devices)} devices>'

    def _login(self, username: str, password: str) -> str:
        """
        Grabs an access token using the given username and password

        :param username: Particle Cloud username
        :param password: Particle Cloud password
        :return: access token used for API calls
        """
        _LOGGER.debug('Acquiring Particle Cloud access token...')

        oauth_url = 'https://api.particle.io/oauth/token'
        data = {
            'username': username,
            'password': password,
            'grant_type': 'password',
        }
        resp = requests.post(oauth_url, auth=('particle', 'particle'), data=data)
        resp.raise_for_status()
        return resp.json()['access_token']

    def _get_devices(self) -> Dict[str, ParticleDevice]:
        """
        Gets the devices associated with the Particle Cloud account

        :return: dict mapping device ID to ParticleDevice
        """
        _LOGGER.debug('Getting devices from Particle Cloud...')

        params = {'access_token': self._access_token}
        resp = requests.get(self.api_prefix + '/devices', params=params)
        resp.raise_for_status()

        devices = {}
        for device_json in resp.json():
            device_id = device_json['id']
            device = ParticleDevice(
                self,
                device_id=device_id,
                name=device_json['name'],
                serial_number=device_json['serial_number']
            )

            _LOGGER.debug(f'Discovered {device!r}')
            devices[device_id] = device

        return devices
