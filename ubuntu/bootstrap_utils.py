"""
This python script should only be called 
"""
import argparse
import os
import re
import subprocess
import sys
import traceback
import tzlocal
from typing import Dict, List
"""
PUID=1000
PGID=140
TZ="America/New_York"
USERDIR="/home/USER"
MYSQL_ROOT_PASSWORD="passsword"
"""


def setup_environment() -> None:
    """
    Adds environment variables needed for Docker to /etc/environment

    :raises RuntimeError: if unable to parse output from `id` command
    """
    lines_to_add: List[str] = []

    # Read in existing /etc/environment file (if exists)
    try:
        with open('/etc/environment', 'r') as f:
            existing_env_text = f.read()
        print(existing_env_text)            # TODO: remove
    except FileNotFoundError:
        existing_env_vars: Dict[str, str] = {}
    else:
        # Check existing file to see if we already have entries for environment variables we want to add
        existing_env_vars: Dict[str, str] = {}
        for env_var_name in ['PUID', 'PGID', 'TZ', 'USERDIR', 'MYSQL_ROOT_PASSWORD']:
            env_var_m = re.search(fr'{env_var_name}=(.+)', existing_env_text)
            if env_var_m:
                print(f'Existing value found for "{env_var_name}" environment variable: {env_var_m.group(1)}')
                existing_env_vars[env_var_name] = env_var_m.group(1)    

    # Grab current user PUID and Docker group ID 
    id_output = subprocess.check_output(['id'], encoding='utf-8')

    uid_m = re.search(r'uid=(?P<uid>\d+)\((?P<user>\w+)\)', id_output)
    if not uid_m:
        raise RuntimeError('Could not parse uid from output of `id`')
    else:
        cur_uid = uid_m.group('uid')

    # TODO: replace "_appserverusr" with "docker"
    docker_group_m = re.search(r'(?P<docker_gid>\d+)\(_appserverusr\)', id_output)
    if not docker_group_m:
        raise RuntimeError('Could not parse docker group ID from output of `id`')
    else:
        docker_gid = docker_group_m.group('docker_gid')

    # Grab environment variables and append to /etc/environment
    puid = existing_env_vars.get('PUID', cur_uid)
    lines_to_add.append(f'PUID={puid}')

    pgid = existing_env_vars.get('PGID', docker_gid)
    lines_to_add.append(f'PGID={pgid}')

    tz = existing_env_vars.get('TZ', tzlocal.get_localzone().zone)
    lines_to_add.append(f'TZ="{tz}"')

    user_dir = existing_env_vars.get('USERDIR', os.path.expanduser('~'))
    lines_to_add.append(f'USERDIR="{user_dir}"')

    # TODO: figure out what we need to add for MYSQL_ROOT_PASSWORD

    with open('/etc/environment', 'a+') as f:
        f.write('\n'.join(lines_to_add))


if __name__ == '__main__':
    available_functions = ('setup_environment',)

    parser = argparse.ArgumentParser(description='Helper scripts for home server boostrapping')
    parser.add_argument('util_func', choices=available_functions, help='Util function to run')
    args = parser.parse_args()

    # Run function given via argument
    try:
        locals()[args.util_func]()
    except:
        traceback.print_exc()
        sys.exit(1)
