from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

import voluptuous as vol
from homeassistant.components.switch import PLATFORM_SCHEMA
from homeassistant.components.switch import SwitchDevice
from homeassistant.const import CONF_NAME
from homeassistant.helpers import config_validation as cv

from custom_components import particle

if TYPE_CHECKING:
    from ..particle import ParticleDevice

DEPENDENCIES = ['particle']

_LOGGER = logging.getLogger(__name__)

CONF_MODULES              = 'modules'
CONF_DEVICE_ID            = 'device_id'
CONF_AUTO_UPDATE_FIRMWARE = 'auto_update_firmware'
CONF_RELAYS               = 'relays'

RELAY_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME): cv.string,
})

MODULE_SCHEMA = vol.Schema({
    vol.Required(CONF_DEVICE_ID): cv.string,
    vol.Required(CONF_RELAYS):
        vol.Schema({cv.positive_int: RELAY_SCHEMA}),
    vol.Optional(CONF_AUTO_UPDATE_FIRMWARE, default=True): cv.boolean,
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_MODULES, default={}): cv.schema_with_slug_keys(MODULE_SCHEMA),
})


REQUIRED_RELAY_MODULE_FW = 5


def setup_platform(hass, config, add_devices, discovery_info=None) -> bool:
    """
    Set up the Particle relay module switch platform
    """
    if particle.PARTICLE_CLOUD is None:
        _LOGGER.error('A connection has not been made to the Particle Cloud')
        return False

    modules: list[RelayModule] = []
    for module_name, module_config in config[CONF_MODULES].items():
        device_id = module_config['device_id']
        _LOGGER.debug(f'Setting up relay module named {module_name!r} with particle device ID {device_id!r}')

        # Grab Particle Device associated with relay module
        try:
            particle_device = particle.PARTICLE_CLOUD.devices_by_device_id[device_id]
        except KeyError:
            _LOGGER.error(f'Device ID {device_id!r} not found in Particle Cloud devices')
            continue

        # Create RelayModule instance
        _LOGGER.debug(f'Creating RelayModule "{module_name}" w/ {particle_device}...')
        module = RelayModule(particle_device, module_name)

        # Grab RelayModule FW version and update if necessary
        auto_update_firmware: bool = module_config.get('auto_update_firmware', True)
        if auto_update_firmware:
            fw_needs_update = True
            try:
                fw_version = module.get_fw_version()
            except AttributeError:
                _LOGGER.warning(f'RelayModule "{module_name}" does not have required firmware. Updating...')
                fw_needs_update = True
            else:
                if fw_version != REQUIRED_RELAY_MODULE_FW:
                    _LOGGER.warning(f'RelayModule "{module_name}" firmware is out of date. Updating...')
                    fw_needs_update = True

            if fw_needs_update:
                dir_path = Path(__file__).parent
                try:
                    particle_device.flash_firmware(dir_path / 'relay_module_firmware.ino')
                except RuntimeError:
                    _LOGGER.exception('Exception received when flashing relay module firmware')
                    continue

        # Create Relay objects
        relay_dicts = module_config.get(CONF_RELAYS, {})

        relays: list[Relay] = []
        for relay_num, relay_dict in relay_dicts.items():
            relay_name = relay_dict['name']
            _LOGGER.debug(f'Adding Relay @ Particle pin {relay_num} w/ name {relay_name}...')
            relays.append(
                module.add_relay(relay_num, relay_name)
            )

        add_devices(relays)
        modules.append(module)

    if not modules:
        _LOGGER.error('No modules added')
        return False
    return True


# TODO: make API calls async and implement async methods
class Relay(SwitchDevice):
    """
    Representation of an individual relay in a RelayModule

    :param relay_module: RelayModule instance this relay is associated with
    :param num: relay index (Particle pin number relay is attached to)
    :param name: name of relay (device attached to relay)
    """
    def __init__(self, relay_module: RelayModule, num: int, name: str) -> None:
        self.relay_module = relay_module
        self._num         = num
        self._name        = name
        self._state       = False

    @property
    def name(self) -> str:
        """
        Name of the relay
        """
        return self._name

    @property
    def num(self) -> int:
        """
        Particle Photon pin number that the relay is attached to
        """
        return self._num

    @property
    def should_poll(self) -> bool:
        """
        Should the device poll for state (bool). Not necessary for this device
        """
        return False

    @property
    def is_on(self) -> bool:
        """
        True if relay is on, False if not
        """
        return self._state

    def turn_on(self, **kwargs: Any) -> None:
        """
        Turn the device on
        """
        self._state = True
        self.relay_module.turn_on_relay(self.num)
        self.schedule_update_ha_state()

    def turn_off(self, **kwargs: Any) -> None:
        """
        Turn the device off
        """
        self._state = False
        self.relay_module.turn_off_relay(self.num)
        self.schedule_update_ha_state()


class RelayModule:
    """
    Representation of a relay module

    :param particle_device: ParticleDevice instance associated with the Particle Photon controlling the relay module
    :param name: name of the relay module
    """
    def __init__(self, particle_device: ParticleDevice, name: str) -> None:
        self.particle_device: ParticleDevice = particle_device
        self.name:            str            = name
        self.relays:          list[Relay]    = []

        # Make sure we have the required functions
        for func_name in ('get_fw_version', 'turn_on', 'turn_off'):
            if func_name not in self.particle_device.functions:
                raise RuntimeError(f'ParticleDevice is not exposing required "{func_name}()" function')

    def add_relay(self, relay_num: int, relay_name: str) -> Relay:
        """
        Creates a Relay instance and adds it to the RelayModule

        :param relay_num: relay index (Particle pin number)
        :param relay_name: name of relay (what is attached to it)
        :return: Relay instance (SwitchDevice subclass)
        """
        relay = Relay(self, relay_num, relay_name)
        self.relays.append(relay)
        return relay

    def get_fw_version(self) -> int:
        """
        Gets the firmware version installed on the relay module Particle devices

        :return: int firmware version
        """
        return self.particle_device.call_function('get_fw_version')

    def get_relay_state(self, relay_num: int) -> bool:
        """
        Get the state of a relay in the module

        :param relay_num: index of relay to get state of
        """
        return self.particle_device.call_function('get_state', str(relay_num))

    def turn_on_relay(self, relay_num: int) -> int:
        """
        Turns on a relay in the module

        :param relay_num: index of relay to turn on
        :return: index of relay that was turned on
        """
        return self.particle_device.call_function('turn_on', str(relay_num))

    def turn_off_relay(self, relay_num: int) -> int:
        """
        Turns off a relay in the module

        :param relay_num: index of relay to turn off
        :return: index of relay that was turned off
        """
        return self.particle_device.call_function('turn_off', str(relay_num))
