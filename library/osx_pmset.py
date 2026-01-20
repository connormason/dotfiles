#!/usr/bin/python
"""
Module for configuring power management settings exposed by `pmset`
"""
from __future__ import annotations

import re
from typing import Any

""" Module metadata """


ANSIBLE_METADATA: dict[str, Any] = {
    'metadata_version': '1.1',
    'status':           ['preview'],
    'supported_by':     'community',
}

DOCUMENTATION = """
---
module: osx_pmset

short_description: Manage power management configuration exposed by pmset

description: >
  Allows changing power management settings by invoking `pmset`. Configuration
  dicts `on_battery` and `on_charger` can have any key present in the output
  of `pmset -g custom`.

options:
    on_battery:
        description: settings on battery power
    on_charger:
        description: settings when connected to power adapter
"""

EXAMPLES = r""" # """

RETURN = r""" # """


from ansible.module_utils.basic import AnsibleModule  # noqa: E402

""" Parsing/regexes """


PMSET_SECTION_REGEX = re.compile(r'^(?P<section>.+):$')
PMSET_KEY_VAL_REGEX = re.compile(r'^ (?P<key>\w+)\s+(?P<val>.+)$')


def parse_pmset_output(output: str) -> dict[str, dict[str, Any]]:
    """
    Parses `pmset -g custom`
    """
    data: dict[str, dict[str, Any]] = {}

    cur_section: str | None = None
    for line in output.splitlines():
        if (line.strip() == '') or ('Sleep On Power Button' in line):
            pass
        elif m := PMSET_SECTION_REGEX.match(line):
            cur_section = m.group('section')
        elif cur_section and (m := PMSET_KEY_VAL_REGEX.match(line)):
            data.setdefault(cur_section, {})[m.group('key')] = m.group('val')

    return data


"""
Core module logic
"""


def build_module() -> AnsibleModule:
    """
    Build AnsibleModule with argument spec

    :return: :class:`AnsibleModule` obj
    """
    return AnsibleModule(
        argument_spec=dict(
            on_battery=dict(
                type='dict',
                required=False,
                default=dict()
            ),
            on_charger=dict(
                type='dict',
                required=False,
                default=dict()
            ),
        ),
        supports_check_mode=True,
    )


def run_module() -> None:
    """
    Run "osx_pmset" ansible module
    """
    module = build_module()

    _, stdout, _ = module.run_command(['pmset', '-g', 'custom'], check_rc=True)
    output = parse_pmset_output(stdout)

    commands: list[Any] = []
    result:   dict[str, Any] = {
        'changed': False,
        'diff': {
            'before': '',
            'after':  '',
        },
    }

    def add_diff(block: str, param: str, old_value: Any, new_value: Any) -> None:
        result['diff']['before'] += f'{block}.{param}={old_value}\n'
        result['diff']['after'] += f'{block}.{param}={new_value}\n'

    blocks: list[tuple[str, str, Any]] = [
        ('on_battery', '-b', output['Battery Power']),
        ('on_charger', '-c', output['AC Power']),
    ]
    for block, mode_flag, current_values in blocks:
        for param, value in module.params[block].items():
            if value is None:
                continue
            elif param not in current_values:
                module.fail_json(
                    msg=(
                        f'{param} is not present in pmset output. '
                        f'Run `pmset -g custom` to see the list of valid parameters'
                    ),
                    **result,
                )

            orig = current_values[param]
            if isinstance(value, int):
                orig = int(orig)
            if orig != value:
                add_diff(block, param, orig, value)
                commands.append(['pmset', mode_flag, param, value])

    if commands:
        result['changed'] = True
    if module.check_mode:
        module.exit_json(**result)

    for command in commands:
        cmd = [str(v) for v in command]
        module.run_command(cmd, check_rc=True)

    module.exit_json(**result)


def main() -> None:
    run_module()


if __name__ == '__main__':
    main()
