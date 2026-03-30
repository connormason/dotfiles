# homeassistant
bae5hau5 HomeAssisant config

### Necessary Workarounds
- pylutron appears to have a bug of some sort, preventing the Lutron component from authenticating even after
generating a cert with [scripts/get_lutron_cert.py](scripts/get_lutron_cert.py). Found a workaround in an
[open homeassistant issue](https://github.com/home-assistant/home-assistant/issues/15421#issuecomment-459453030),
which requires changing a line in the pylutron python package:

  ```
  quick fix :
  in [ /srv/hass/lib/python3.6/site-packages/pylutron_caseta/smartbridge.py ] line 50 :
  ssl_context.verify_mode = ssl.CERT_NONE

  instead of
  ssl_context.verify_mode = ssl.CERT_REQUIRED
  ```
