#!/usr/bin/env python3
"""
Extract and analyze Claude Code session logs.
"""
from __future__ import annotations

import abc
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import ClassVar
from typing import Literal
from typing import TypedDict
from typing import cast
from typing import get_args

if TYPE_CHECKING:
    from collections.abc import Sequence

# ===================
# Filepath resolution
# ===================


def get_projects_dir() -> Path:
    """
    Return the path to the Claude Code projects directory.

    :return: Path to the ``~/.claude/projects`` directory.
    """
    return Path.home() / '.claude' / 'projects'


def get_subagents_dir(session_path: Path) -> Path:
    """
    Get the subagents directory for a session.

    :param session_path: Path to the session JSONL file.
    :return: Path to the subagents directory for the given session.
    """
    session_id = session_path.stem
    return session_path.parent / session_id / 'subagents'


def list_subagent_files(session_path: Path) -> dict[str, Path]:
    """
    List all subagent log files for a session.

    :param session_path: Path to the session JSONL file.
    :return: dictionary mapping agent_id to the subagent file path.
    """
    subagents_dir = get_subagents_dir(session_path)

    result: dict[str, Path] = {}
    if subagents_dir.exists() and subagents_dir.is_dir():
        for f in subagents_dir.glob('agent-*.jsonl'):
            agent_id = f.stem.replace('agent-', '')
            result[agent_id] = f

    return result


def find_subagent_file(agent_id: str) -> Path | None:
    """
    Search all projects for a subagent file matching the given agent ID.

    :param agent_id: short hex identifier for the subagent.
    :return: Path to the subagent file if found, ``None`` otherwise.
    """
    projects_dir = get_projects_dir()
    if not projects_dir.exists():
        return None

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue

        # Search all session directories for subagent files
        for session_dir in project_dir.iterdir():
            if session_dir.is_dir():
                subagent_file = session_dir / 'subagents' / f'agent-{agent_id}.jsonl'
                if subagent_file.exists():
                    return subagent_file

    return None


# ==============
# Project lookup
# ==============


def list_projects() -> list[str]:
    """
    List all project directories.

    :return: sorted list of project directory names.
    """
    projects_dir = get_projects_dir()
    if not projects_dir.exists():
        print('No projects directory found', file=sys.stderr)
        return []

    return sorted([d.name for d in projects_dir.iterdir() if d.is_dir()])


def find_project(query: str) -> list[str]:
    """
    Find project directory matching query.

    :param query: case-insensitive substring to match against project names.
    :return: list of matching project directory names.
    """
    return [p for p in list_projects() if query.lower() in p.lower()]


# ==============
# Session lookup
# ==============


def list_sessions(project: str, *, limit: int = 10) -> list[Path]:
    """
    List recent sessions for a project.

    :param project: project directory name.
    :param limit: maximum number of sessions to return.
    :return: list of session file paths sorted by modification time (most recent first).
    """
    project_dir = get_projects_dir() / project
    if not project_dir.exists():
        print(f'Project not found: {project}', file=sys.stderr)
        return []

    sessions = sorted(
        project_dir.glob('*.jsonl'),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    return sessions[:limit]


def resolve_session_path(session_arg: str) -> Path:
    """
    Resolve a session argument to a full path.

    Accepts:

        - Full absolute path
        - Path with ~ expansion
        - Just session UUID (searches all projects)
        - Just filename (searches all projects)
        - Agent ID (searches subagents folders)
        - Subagent path like <session-id>/subagents/agent-<id>.jsonl

    :param session_arg: session identifier in any of the accepted formats.
    :return: resolved path to the session or subagent JSONL file.
    """

    # Try as-is first (handles absolute paths and ~ expansion)
    path = Path(session_arg).expanduser()
    if path.exists():
        return path

    # Check if it looks like a subagent path (contains /subagents/)
    if ('/subagents/' in session_arg) or ('\\subagents\\' in session_arg):

        # Try to resolve relative to projects dir
        projects_dir = get_projects_dir()
        if projects_dir.exists():
            for project_dir in projects_dir.iterdir():
                if project_dir.is_dir():
                    candidate = project_dir / session_arg
                    if candidate.exists():
                        return candidate

        return path

    # Check if this might be an agent ID (short hex string without extension)
    if (
        (not session_arg.endswith('.jsonl'))
        and (len(session_arg) <= 10)
        and all(c in '0123456789abcdef' for c in session_arg.lower())
        and (subagent_file := find_subagent_file(session_arg))
    ):
        return subagent_file

    # If it looks like a UUID or filename, search for it
    filename = session_arg if session_arg.endswith('.jsonl') else f'{session_arg}.jsonl'

    projects_dir = get_projects_dir()
    if projects_dir.exists():

        # Search all project directories
        for project_dir in projects_dir.iterdir():
            if project_dir.is_dir():
                candidate = project_dir / filename
                if candidate.exists():
                    return candidate

    # Return the original expanded path (will fail with clear error message)
    return path


def require_session_path(session_arg: str) -> Path:
    """
    Resolve and validate a session path, exiting with an error if not found.

    :param session_arg: session identifier in any accepted format.
    :return: resolved path to an existing session JSONL file.
    """
    session_path = resolve_session_path(session_arg)
    if not session_path.exists():
        print(
            f"Session file not found: {session_arg}\n"
            "Tip: You can use just the session UUID (e.g., 'b06de9e3-038a-466f-a505-68ad558e402a')",
            file=sys.stderr,
        )
        sys.exit(1)
    return session_path


# ===========================
# Session log info extraction
# ===========================


def parse_content_item(item: dict, line_num: int, verbose: bool = False) -> list[str]:
    """
    Parse a single content item and return formatted string.

    :param item: dictionary representing a content item (text, tool_use, or tool_result).
    :param line_num: line number in the JSONL file where this item was found.
    :param verbose: whether to include full untruncated content.
    :return: list of formatted output strings for the content item.
    """
    output: list[str] = []
    item_type = item.get('type')

    if item_type == 'text':
        if text := item.get('text', '').strip():
            if verbose:
                output.append(f'[{line_num}] TEXT: {text}')
            else:
                output.append(f"[{line_num}] TEXT: {text[:200]}{'...' if len(text) > 200 else ''}")

    elif item_type == 'tool_use':
        name    = item.get('name', 'unknown')
        tool_id = item.get('id', '')[:12]
        inp     = item.get('input', {})
        output.append(f'[{line_num}] TOOL: {name} (id={tool_id})')

        if verbose and isinstance(inp, dict):
            for k, v in inp.items():
                val_str = str(v)
                output.append(f'    {k}: {val_str}')

    elif item_type == 'tool_result':
        tool_id  = item.get('tool_use_id', '')[:12]
        is_error = item.get('is_error', False)
        content  = str(item.get('content', ''))
        status   = 'ERROR' if is_error else 'OK'
        if verbose:
            output.append(f'[{line_num}] RESULT ({status}, id={tool_id}): {content}')
        else:
            output.append(f"[{line_num}] RESULT ({status}): {content[:200]}{'...' if len(content) > 200 else ''}")

    return output


def extract_session(
    session_path: Path,
    *,
    agent_id: str | None = None,
    errors_only: bool = False,
    verbose: bool = False,
    line_range: tuple[int, int] | None = None,
) -> list[str]:
    """
    Extract and format session log content.

    If agent_id is specified and the agent has a separate log file in subagents/,
    reads from that file instead of filtering the main session.

    :param session_path: Path to the session JSONL file.
    :param agent_id: optional agent ID to filter by, or to look up a separate subagent log.
    :param errors_only: whether to only include tool error results.
    :param verbose: whether to include full untruncated content.
    :param line_range: optional ``(start, end)`` tuple to restrict output to a line range.
    :return: list of formatted output strings extracted from the session.
    """
    output: list[str] = []
    actual_path = session_path

    # If agent_id specified, check if there's a separate subagent log file
    if agent_id:
        subagent_files = list_subagent_files(session_path)
        if agent_id in subagent_files:
            actual_path = subagent_files[agent_id]
            # When reading from subagent file, don't filter by agent_id
            # since the file only contains that agent's activity
            agent_id = None

    with actual_path.open() as f:
        for i, line in enumerate(f):
            line_num = i + 1
            if line_range and ((line_num < line_range[0]) or (line_num > line_range[1])):
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = data.get('type')

            # Handle user messages (only in subagent logs - shows the prompt)
            if msg_type == 'user':
                message = data.get('message', {})
                if isinstance(message, dict):
                    content = message.get('content', '')
                    if isinstance(content, str) and content.strip():
                        if verbose:
                            output.append(f'[{line_num}] USER: {content.strip()}')
                        else:
                            text = content.strip()[:200]
                            output.append(f"[{line_num}] USER: {text}{'...' if len(content) > 200 else ''}")

            # Handle assistant messages (only in subagent logs)
            elif msg_type == 'assistant':
                message = data.get('message', {})
                if isinstance(message, dict):
                    content = message.get('content', [])
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict):
                                if errors_only:
                                    if (item.get('type') == 'tool_result') and item.get('is_error'):
                                        output.extend(parse_content_item(item, line_num, verbose))
                                else:
                                    output.extend(parse_content_item(item, line_num, verbose))

            # Handle progress messages (agent activity)
            elif (msg_type == 'progress') and ('data' in data):
                progress_data = data['data']
                msg_agent_id  = progress_data.get('agentId')

                # Filter by agent ID if specified
                if agent_id and (msg_agent_id != agent_id):
                    continue

                msg = progress_data.get('message', {}).get('message', {})
                if not isinstance(msg, dict):
                    continue

                content = msg.get('content', [])
                if not isinstance(content, list):
                    continue

                for item in content:
                    if not isinstance(item, dict):
                        continue

                    # Filter for errors only if requested
                    if errors_only:
                        if (item.get('type') == 'tool_result') and item.get('is_error'):
                            output.extend(parse_content_item(item, line_num, verbose))
                    else:
                        output.extend(parse_content_item(item, line_num, verbose))

    return output


class ErrorInfo(TypedDict):
    """
    Typed dictionary for tool error information (returned by :func:`find_errors`).
    """
    line:     int
    agent_id: str
    content:  str
    tool_id:  str


def find_errors(session_path: Path, pattern: str | None = None) -> list[ErrorInfo]:
    """
    Find all tool errors in a session, optionally filtering by pattern.

    :param session_path: Path to the session JSONL file.
    :param pattern: optional case-insensitive substring to filter error content.
    :return: list of error dictionaries with line, agent_id, content, and tool_id.
    """
    errors: list[ErrorInfo] = []
    with session_path.open() as f:
        for i, line in enumerate(f):
            line_num = i + 1
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            if (data.get('type') == 'progress') and ('data' in data):
                agent_id = data['data'].get('agentId', 'main')
                msg      = data['data'].get('message', {}).get('message', {})

                if isinstance(msg, dict):
                    content = msg.get('content', [])
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and (item.get('type') == 'tool_result') and item.get('is_error'):
                                error_content = str(item.get('content', ''))
                                if pattern and (pattern.lower() not in error_content.lower()):
                                    continue

                                errors.append({
                                    'line':     line_num,
                                    'agent_id': agent_id,
                                    'content':  error_content[:500],
                                    'tool_id':  item.get('tool_use_id', '')
                                })
    return errors


class SessionAgentInfo(TypedDict):
    """
    Typed dictionary for agent info from a session (returned by :func:`list_agents`).
    """
    has_separate_log: bool
    log_path:         Path | None


def list_agents(session_path: Path) -> dict[str, SessionAgentInfo]:
    """
    List all unique agent IDs in a session.

    :param session_path: Path to the session JSONL file.
    :return: dictionary mapping agent_id to info with ``has_separate_log`` and ``log_path`` keys.
    """
    agents: dict[str, SessionAgentInfo] = {}

    # Get agents from the main session log (progress messages)
    with session_path.open() as f:
        for line in f:
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            if (data.get('type') == 'progress') and ('data' in data):
                agent_id = data['data'].get('agentId')
                if agent_id and (agent_id not in agents):
                    agents[agent_id] = {'has_separate_log': False, 'log_path': None}

    # Check for separate subagent log files
    subagent_files = list_subagent_files(session_path)
    for agent_id, log_path in subagent_files.items():
        if agent_id in agents:
            agents[agent_id]['has_separate_log'] = True
            agents[agent_id]['log_path']         = log_path
        else:
            # Agent has a log file but no progress messages in main session
            agents[agent_id] = {'has_separate_log': True, 'log_path': log_path}

    return agents


# =============================
# Session hierarchy compilation
# =============================


Status = Literal['error', 'success']


class TaskSpawnInfo(TypedDict):
    """
    Typed dictionary for task spawn metadata.
    """
    subagent_type: str
    description:   str
    background:    bool
    spawned_by:    str


class AgentInfo(TypedDict):
    """
    Typed dictionary for agent information.
    """
    prompt:             str
    parent_tool_use_id: str


class AgentResult(TypedDict):
    """
    Typed dictionary for agent execution results.
    """
    status: Status
    error:  str


class HierarchyChild(TypedDict):
    """
    Typed dictionary for a child agent in the hierarchy tree.
    """
    agent_id:      str
    subagent_type: str
    status:        Status
    error:         str


class HierarchySpawn(TypedDict):
    """
    Typed dictionary for a Task spawn in the hierarchy tree.
    """
    tool_id:       str
    subagent_type: str
    description:   str
    background:    bool


class HierarchyNode(TypedDict):
    """
    Typed dictionary for a node in the agent hierarchy tree.
    """
    children: list[HierarchyChild]
    spawns:   list[HierarchySpawn]


def build_agent_hierarchy(session_path: Path) -> dict[str, HierarchyNode]:
    """
    Build a hierarchy of agents showing parent-child relationships.

    :param session_path: Path to the session JSONL file.
    :return: hierarchy dictionary keyed by agent ID with ``children`` and ``spawns`` lists.
    """

    # Track: tool_use_id -> {subagent_type, agent_id, parent_tool_use_id, status, duration}
    task_spawns:   dict[str, TaskSpawnInfo] = {}  # tool_use_id -> info about the Task call
    agent_info:    dict[str, AgentInfo]     = {}  # agent_id    -> {prompt, parent_tool_use_id, subagent_type}
    agent_results: dict[str, AgentResult]   = {}  # agent_id    -> {status, error, duration}

    with session_path.open() as f:
        for line in f:
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = data.get('type')

            # Track Task tool calls from main conversation
            if msg_type == 'assistant':
                content = data.get('message', {}).get('content', [])
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and (item.get('name') == 'Task'):
                            tool_id = item.get('id', '')
                            inp     = item.get('input', {})
                            task_spawns[tool_id] = {
                                'subagent_type': inp.get('subagent_type', 'unknown'),
                                'description':   inp.get('description', ''),
                                'background':    inp.get('run_in_background', False),
                                'spawned_by':    'main'
                            }

            # Track Task tool calls from within agents (progress messages)
            if (msg_type == 'progress') and ('data' in data):
                progress_data      = data['data']
                agent_id           = progress_data.get('agentId')
                parent_tool_use_id = data.get('parentToolUseID')

                # Record agent info
                if agent_id and (agent_id not in agent_info):
                    agent_info[agent_id] = {
                        'prompt':             progress_data.get('prompt', '')[:100],
                        'parent_tool_use_id': parent_tool_use_id,
                    }

                msg = progress_data.get('message', {}).get('message', {})
                if isinstance(msg, dict):
                    content = msg.get('content', [])
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict):

                                # Track Task spawns from agents
                                if (item.get('type') == 'tool_use') and (item.get('name') == 'Task'):
                                    tool_id = item.get('id', '')
                                    inp     = item.get('input', {})
                                    task_spawns[tool_id] = {
                                        'subagent_type': inp.get('subagent_type', 'unknown'),
                                        'description':   inp.get('description', ''),
                                        'background':    inp.get('run_in_background', False),
                                        'spawned_by':    agent_id
                                    }

                                # Track errors
                                if (item.get('type') == 'tool_result') and item.get('is_error'):
                                    error_content = str(item.get('content', ''))
                                    if agent_id:
                                        agent_results[agent_id] = {
                                            'status': 'error',
                                            'error':  error_content[:100]
                                        }

    # Build hierarchy tree
    hierarchy: dict[str, HierarchyNode] = {'main': {'children': [], 'spawns': []}}
    for tool_id, spawn_info in task_spawns.items():
        spawned_by = spawn_info['spawned_by']
        if spawned_by not in hierarchy:
            hierarchy[spawned_by] = {'children': [], 'spawns': []}

        hierarchy[spawned_by]['spawns'].append({
            'tool_id': tool_id,
            'subagent_type': spawn_info['subagent_type'],
            'description':   spawn_info['description'],
            'background':    spawn_info['background']
        })

    # Match agents to their parent spawns
    for agent_id, info in agent_info.items():
        parent_tool_id = info['parent_tool_use_id']
        if parent_tool_id in task_spawns:
            spawn_info = task_spawns[parent_tool_id]
            result     = agent_results.get(agent_id)

            hierarchy_entry: HierarchyChild = {
                'agent_id':      agent_id,
                'subagent_type': spawn_info['subagent_type'],
                'status':        result['status'] if result else 'success',
                'error':         result['error'] if result else ''
            }
            spawned_by = spawn_info['spawned_by']
            if spawned_by not in hierarchy:
                hierarchy[spawned_by] = {'children': [], 'spawns': []}
            hierarchy[spawned_by]['children'].append(hierarchy_entry)

    return hierarchy


def format_hierarchy(hierarchy: dict[str, HierarchyNode], node: str = 'main', *, indent: int = 0) -> list[str]:
    """
    Format hierarchy as tree string.

    :param hierarchy: hierarchy dictionary as returned by :func:`build_agent_hierarchy`.
    :param node: node key to start formatting from.
    :param indent: current indentation level for nested tree rendering.
    :return: list of formatted tree lines.
    """
    lines: list[str] = []
    prefix = '  ' * indent

    if node == 'main':
        lines.append('Main conversation')

    node_data = hierarchy.get(node, {'children': [], 'spawns': []})
    for child in node_data['children']:
        agent_id      = child['agent_id']
        subagent_type = child['subagent_type']
        status        = child['status']
        error         = child.get('error', '')

        status_icon = '✓' if status == 'success' else '✗'
        error_str   = f' ({error})' if error else ''

        lines.append(f'{prefix}└── {subagent_type} ({agent_id}) [{status_icon}]{error_str}')

        # Recurse for nested agents
        if agent_id in hierarchy:
            lines.extend(format_hierarchy(hierarchy, agent_id, indent=indent + 2))

    # Show spawns that didn't result in tracked agents
    # Note: background tasks often don't get separate agentIds in logs
    spawned_agent_ids: set[str] = {c['subagent_type'] for c in node_data['children']}
    for spawn in node_data['spawns']:
        if spawn['subagent_type'] not in spawned_agent_ids:
            if spawn['background']:
                lines.append(f"{prefix}└── {spawn['subagent_type']} (background) [spawned, no separate logs]")
            else:
                lines.append(f"{prefix}└── {spawn['subagent_type']} [spawn attempted, no agent created]")

    return lines


# =====================
# Session summarization
# =====================


class SummaryTaskSpawn(TypedDict):
    """
    Typed dictionary for task spawn metadata in subagent summary.
    """
    subagent_type: str
    spawned_by:    str
    start_time:    str
    background:    bool


class SubagentSummary(TypedDict):
    """
    Typed dictionary for subagent summary information.
    """
    agent_id:      str
    subagent_type: str
    spawned_by:    str
    start_time:    str
    end_time:      str | None
    status:        str
    error:         str | None
    tool_count:    int
    duration:      str


def get_subagent_summary(session_path: Path) -> list[SubagentSummary]:
    """
    Get summary of all subagents with status and timing.

    :param session_path: Path to the session JSONL file.
    :return: list of dictionaries containing agent summary info (agent_id, subagent_type, status, duration, tool_count).
    """
    agents:      dict[str, SubagentSummary]  = {}
    task_spawns: dict[str, SummaryTaskSpawn] = {}

    with session_path.open() as f:
        lines = f.readlines()

    for line in lines:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_type  = data.get('type')
        timestamp = data.get('timestamp', '')

        # Track Task spawns
        if msg_type == 'assistant':
            content = data.get('message', {}).get('content', [])
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and (item.get('name') == 'Task'):
                        tool_id = item.get('id', '')
                        inp     = item.get('input', {})
                        task_spawns[tool_id] = {
                            'subagent_type': inp.get('subagent_type', 'unknown'),
                            'spawned_by':   'main',
                            'start_time':   timestamp,
                            'background':   inp.get('run_in_background', False)
                        }

        if (msg_type == 'progress') and ('data' in data):
            progress_data      = data['data']
            agent_id           = progress_data.get('agentId')
            parent_tool_use_id = data.get('parentToolUseID')

            if agent_id:
                if agent_id not in agents:
                    spawn_info: SummaryTaskSpawn = task_spawns.get(parent_tool_use_id, {})  # type: ignore[typeddict-item]
                    agents[agent_id] = {
                        'agent_id':      agent_id,
                        'subagent_type': spawn_info.get('subagent_type', 'unknown'),
                        'spawned_by':    spawn_info.get('spawned_by',    'unknown'),
                        'start_time':    timestamp,
                        'end_time':      None,
                        'status':        'running',
                        'error':         None,
                        'tool_count':    0,
                        'duration':      '?',
                    }

                # Update end time
                agents[agent_id]['end_time'] = timestamp

                # Count tool uses and check for errors
                msg = progress_data.get('message', {}).get('message', {})
                if isinstance(msg, dict):
                    content = msg.get('content', [])
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict):
                                if item.get('type') == 'tool_use':
                                    agents[agent_id]['tool_count'] += 1

                                    # Track nested Task spawns
                                    if item.get('name') == 'Task':
                                        tool_id = item.get('id', '')
                                        inp     = item.get('input', {})
                                        task_spawns[tool_id] = {
                                            'subagent_type': inp.get('subagent_type', 'unknown'),
                                            'spawned_by':    agent_id,
                                            'start_time':    timestamp,
                                            'background':    inp.get('run_in_background', False)
                                        }

                                if (item.get('type') == 'tool_result') and item.get('is_error'):
                                    error_content = str(item.get('content', ''))
                                    if 'No such tool' in error_content:
                                        agents[agent_id]['status'] = 'FAILED'
                                        agents[agent_id]['error']  = error_content[:80]

    # Calculate durations and finalize status
    for info in agents.values():
        if info['status'] == 'running':
            info['status'] = 'success'

        if info['start_time'] and info['end_time']:
            try:
                start    = datetime.fromisoformat(info['start_time'].replace('Z', '+00:00'))
                end      = datetime.fromisoformat(info['end_time'].replace('Z', '+00:00'))
                duration = (end - start).total_seconds()
            except (ValueError, TypeError):
                info['duration'] = '?'
            else:
                info['duration'] = f'{duration:.1f}s'
        else:
            info['duration'] = '?'

    return list(agents.values())


def get_timeline(session_path: Path) -> list[str]:
    """
    Get timeline of events with agent context.

    :param session_path: Path to the session JSONL file.
    :return: list of formatted timeline event strings.
    """
    events: list[str] = []
    with session_path.open() as f:
        for line in f:
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type  = data.get('type')
            timestamp = data.get('timestamp', '')

            # Parse timestamp for display
            time_str = ''
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    time_str = dt.strftime('%H:%M:%S')
                except (ValueError, TypeError):
                    time_str = timestamp[:8]

            # Main conversation tool calls
            if msg_type == 'assistant':
                content = data.get('message', {}).get('content', [])
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get('type') == 'tool_use':
                            name = item.get('name', '')
                            inp  = item.get('input', {})

                            if name == 'Task':
                                subagent = inp.get('subagent_type', '')
                                desc     = inp.get('description', '')
                                bg       = ' (bg)' if inp.get('run_in_background') else ''
                                events.append(f'[{time_str}] MAIN: Task({subagent}: {desc}){bg}')
                            else:
                                events.append(f'[{time_str}] MAIN: {name}(...)')

            # Agent activity
            if msg_type == 'progress' and 'data' in data:
                progress_data = data['data']
                agent_id      = progress_data.get('agentId', '')

                msg = progress_data.get('message', {}).get('message', {})
                if isinstance(msg, dict):
                    content = msg.get('content', [])
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict):
                                item_type = item.get('type')

                                if item_type == 'tool_use':
                                    name = item.get('name', '')
                                    inp  = item.get('input', {})

                                    if name == 'Task':
                                        subagent = inp.get('subagent_type', '')
                                        bg = ' (bg)' if inp.get('run_in_background') else ''
                                        events.append(f'[{time_str}] {agent_id}: Task({subagent}){bg}')
                                    elif name == 'Bash':
                                        cmd = inp.get('command', '')[:40]
                                        events.append(f'[{time_str}] {agent_id}: Bash({cmd}...)')
                                    elif name in ('Read', 'Write', 'Edit'):
                                        path = inp.get('file_path', '').split('/')[-1]
                                        events.append(f'[{time_str}] {agent_id}: {name}({path})')
                                    elif name in ('Grep', 'Glob'):
                                        pattern = inp.get('pattern', '')[:30]
                                        events.append(f'[{time_str}] {agent_id}: {name}({pattern})')
                                    else:
                                        events.append(f'[{time_str}] {agent_id}: {name}(...)')

                                elif (item_type == 'tool_result') and item.get('is_error'):
                                    error = str(item.get('content', ''))[:50]
                                    events.append(f'[{time_str}] {agent_id}: ❌ ERROR: {error}')

    return events


# ==================
# Session comparison
# ==================


ComparisonFocus = Literal['agents', 'errors', 'tools', 'all']
SessionKey      = Literal['session1', 'session2']


class SessionComparisonInfo(TypedDict):
    """
    Typed dictionary for a single session's comparison data.
    """
    path:        str
    agents:      list[SubagentSummary]
    errors:      list[ErrorInfo]
    tool_counts: dict[str, int]


def compare_sessions(
    session1_path: Path,
    session2_path: Path,
) -> dict[SessionKey, SessionComparisonInfo]:
    """
    Compare two sessions, highlighting differences.

    :param session1_path: Path to the first session JSONL file.
    :param session2_path: Path to the second session JSONL file.
    :return: dictionary with ``session1`` and ``session2`` keys containing agents, errors, and tool_counts.
    """
    results: dict[SessionKey, SessionComparisonInfo] = {
        'session1': {'path': str(session1_path), 'agents': [], 'errors': [], 'tool_counts': {}},
        'session2': {'path': str(session2_path), 'agents': [], 'errors': [], 'tool_counts': {}}
    }

    for session_key, session_path in [('session1', session1_path), ('session2', session2_path)]:
        session_key = cast('SessionKey', session_key)
        results[session_key]['agents'] = get_subagent_summary(session_path)
        results[session_key]['errors'] = find_errors(session_path)

        tool_counts: dict[str, int] = {}
        with session_path.open() as f:
            for line in f:
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if (data.get('type') == 'progress') and ('data' in data):
                    msg = data['data'].get('message', {}).get('message', {})
                    if isinstance(msg, dict):
                        content = msg.get('content', [])
                        if isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict) and (item.get('type') == 'tool_use'):
                                    name = item.get('name', 'unknown')
                                    tool_counts[name] = tool_counts.get(name, 0) + 1

        results[session_key]['tool_counts'] = tool_counts

    return results


# =========================
# Session transcript export
# =========================


def export_transcript(session_path: Path, *, agent_id: str | None = None, output_path: Path | None = None) -> str:
    """
    Export session as human-readable transcript (similar to /export).

    If agent_id is specified and the agent has a separate log file in subagents/, reads from that file instead of
    filtering the main session.

    :param session_path: Path to the session JSONL file.
    :param agent_id: optional agent ID to filter by, or to look up a separate subagent log.
    :param output_path: optional path to write the transcript to. If ``None``, returns the transcript string.
    :return: the transcript string, or the output file path as a string if ``output_path`` was provided.
    """
    lines: list[str] = []

    actual_path     = session_path
    filter_agent_id = agent_id

    # If agent_id specified, check if there's a separate subagent log file
    if agent_id:
        subagent_files = list_subagent_files(session_path)
        if agent_id in subagent_files:
            actual_path = subagent_files[agent_id]
            # When reading from subagent file, don't filter by agent_id
            # since the file only contains that agent's activity
            filter_agent_id = None

    with actual_path.open() as f:
        for line in f:
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = data.get('type')

            # Top-level user messages
            if msg_type == 'user':
                message = data.get('message', {})
                if isinstance(message, dict):
                    content = message.get('content', '')
                    if isinstance(content, str) and content.strip():
                        lines.append(f'\n> {content.strip()}\n')
                    elif isinstance(content, list):
                        lines.extend(
                            f"\n> {item.get('text', '').strip()}\n"
                            for item in content
                            if isinstance(item, dict) and item.get('type') == 'text'
                        )

            # Top-level assistant messages
            elif msg_type == 'assistant':
                message = data.get('message', {})
                if isinstance(message, dict):
                    content = message.get('content', [])
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict):
                                item_type = item.get('type')

                                if item_type == 'text':
                                    text = item.get('text', '').strip()
                                    if text:
                                        lines.append(f'\n* {text}\n')

                                elif item_type == 'tool_use':
                                    name = item.get('name', 'unknown')
                                    inp = item.get('input', {})

                                    # Format tool call
                                    if name == 'Bash':
                                        cmd  = inp.get('command', '')
                                        desc = inp.get('description', '')
                                        if desc:
                                            lines.append(f'\n* Bash({desc})\n')
                                        else:
                                            lines.append(f"\n* Bash({cmd[:60]}{'...' if len(cmd) > 60 else ''})\n")
                                    elif name == 'Read':
                                        path = inp.get('file_path', '')
                                        lines.append(f'\n* Read({path})\n')
                                    elif name == 'Write':
                                        path = inp.get('file_path', '')
                                        lines.append(f'\n* Write({path})\n')
                                    elif name == 'Edit':
                                        path = inp.get('file_path', '')
                                        lines.append(f'\n* Edit({path})\n')
                                    elif name == 'Grep':
                                        pattern = inp.get('pattern', '')
                                        lines.append(f'\n* Grep({pattern})\n')
                                    elif name == 'Glob':
                                        pattern = inp.get('pattern', '')
                                        lines.append(f'\n* Glob({pattern})\n')
                                    elif name == 'Task':
                                        subagent = inp.get('subagent_type', '')
                                        desc = inp.get('description', '')
                                        lines.append(f'\n* Task({subagent}: {desc})\n')
                                    else:
                                        lines.append(f'\n* {name}(...)\n')

                                elif item_type == 'tool_result':
                                    is_error       = item.get('is_error', False)
                                    result_content = str(item.get('content', ''))

                                    if is_error:
                                        lines.append(
                                            f"  |  ERROR: {result_content[:200]}"
                                            f"{'...' if len(result_content) > 200 else ''}\n"
                                        )
                                    elif result_content.strip():

                                        # Truncate long results
                                        if len(result_content) > 300:
                                            result_content = result_content[:300] + '...'

                                        # Indent multi-line results
                                        result_lines = result_content.strip().split('\n')
                                        if len(result_lines) > 5:
                                            result_lines = [*result_lines[:5], '... (truncated)']
                                        lines.extend(f'  |  {rl}\n' for rl in result_lines)

            # Progress messages (agent activity)
            elif msg_type == 'progress' and 'data' in data:
                progress_data = data['data']
                msg_agent_id  = progress_data.get('agentId')

                # Filter by agent ID if specified
                if filter_agent_id and (msg_agent_id != filter_agent_id):
                    continue

                msg = progress_data.get('message', {}).get('message', {})
                if not isinstance(msg, dict):
                    continue

                content = msg.get('content', [])
                if not isinstance(content, list):
                    continue

                for item in content:
                    if not isinstance(item, dict):
                        continue

                    item_type = item.get('type')

                    if item_type == 'text':
                        if text := item.get('text', '').strip():
                            prefix = '  ' if msg_agent_id else ''
                            lines.append(f'\n{prefix}* {text}\n')

                    elif item_type == 'tool_use':
                        name   = item.get('name', 'unknown')
                        inp    = item.get('input', {})
                        prefix = '  ' if msg_agent_id else ''

                        # Format tool call
                        if name == 'Bash':
                            cmd  = inp.get('command', '')
                            desc = inp.get('description', '')
                            if desc:
                                lines.append(f'\n{prefix}* Bash({desc})\n')
                            else:
                                lines.append(f"\n{prefix}* Bash({cmd[:60]}{'...' if len(cmd) > 60 else ''})\n")
                        elif name == 'Read':
                            path = inp.get('file_path', '')
                            lines.append(f'\n{prefix}* Read({path})\n')
                        elif name == 'Write':
                            path = inp.get('file_path', '')
                            lines.append(f'\n{prefix}* Write({path})\n')
                        elif name == 'Edit':
                            path = inp.get('file_path', '')
                            lines.append(f'\n{prefix}* Edit({path})\n')
                        elif name == 'Grep':
                            pattern = inp.get('pattern', '')
                            lines.append(f'\n{prefix}* Grep({pattern})\n')
                        elif name == 'Glob':
                            pattern = inp.get('pattern', '')
                            lines.append(f'\n{prefix}* Glob({pattern})\n')
                        elif name == 'Task':
                            subagent = inp.get('subagent_type', '')
                            desc = inp.get('description', '')
                            lines.append(f'\n{prefix}* Task({subagent}: {desc})\n')
                        else:
                            lines.append(f'\n{prefix}* {name}(...)\n')

                    elif item_type == 'tool_result':
                        is_error       = item.get('is_error', False)
                        result_content = str(item.get('content', ''))
                        prefix = '  ' if msg_agent_id else ''

                        if is_error:
                            lines.append(
                                f"{prefix}  |  ERROR: {result_content[:200]}"
                                f"{'...' if len(result_content) > 200 else ''}\n"
                            )
                        elif result_content.strip():

                            # Truncate long results
                            if len(result_content) > 300:
                                result_content = result_content[:300] + '...'

                            # Indent multi-line results
                            result_lines = result_content.strip().split('\n')
                            if len(result_lines) > 5:
                                result_lines = [*result_lines[:5], '... (truncated)']
                            lines.extend(f'{prefix}  |  {rl}\n' for rl in result_lines)

    output = ''.join(lines)
    if output_path:
        with output_path.open('w') as f:
            f.write(output)
        return str(output_path)

    return output


# ===========================
# Command abstract base class
# ===========================


REGISTERED_COMMANDS: dict[str, Command] = {}


class Command(metaclass=abc.ABCMeta):
    """
    Abstract base class for CLI subcommands.

    Subclasses define a command by setting class attributes and implementing :meth:`run`.
    Commands are auto-registered upon class definition via :meth:`__init_subclass__`.
    """
    name:        ClassVar[str] = ''
    description: ClassVar[str] = ''

    def __init_subclass__(cls, register: bool = True, **kwargs: Any) -> None:
        """
        Register the command subclass in the global command registry.

        :param register: if False, skip registration (useful for abstract intermediate base classes)
        """
        super().__init_subclass__(**kwargs)
        if not register:
            return
        if not cls.name:
            cls.name = cls.__name__.removesuffix('Command').replace('_', '-').lower()
        if not cls.description:
            cls.description = cls.__doc__.strip().split('\n')[0] if cls.__doc__ else f'Run {cls.name}'

        REGISTERED_COMMANDS[cls.name] = cls()

    def __call__(self, args: argparse.Namespace) -> None:
        return self.run(args)

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:       # noqa: B027
        """
        Add command-specific arguments to the subparser.

        Override in subclasses to define CLI arguments. Default implementation is a no-op.

        :param parser: the argparse subparser for this command.
        """
        pass

    @abc.abstractmethod
    def run(self, args: argparse.Namespace) -> None:
        """
        Execute the command logic.

        :param args: parsed command-line arguments.
        """
        raise NotImplementedError


# ========
# Commands
# ========


class ProjectsCommand(Command):
    """
    List or find projects.
    """
    name: ClassVar[str] = 'projects'

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('query', type=str, nargs='?', help='Search query')

    def run(self, args: argparse.Namespace) -> None:
        if args.query:
            matches = find_project(args.query)
            for m in matches:
                print(m)
        else:
            for p in list_projects():
                print(p)


class SessionsCommand(Command):
    """
    List recent sessions.
    """
    name: ClassVar[str] = 'sessions'

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('project',       type=str,             help='Project name or partial match')
        parser.add_argument('-n', '--limit', type=int, default=10, help='Number of sessions')

    def run(self, args: argparse.Namespace) -> None:
        matches = find_project(args.project)
        if not matches:
            print(f'No project found matching: {args.project}', file=sys.stderr)
            sys.exit(1)
        if len(matches) > 1:
            print(f'Multiple matches, using first: {matches[0]}', file=sys.stderr)

        sessions = list_sessions(matches[0], limit=args.limit)
        for s in sessions:
            print(str(s))


class ExtractCommand(Command):
    """
    Extract session content.
    """
    name: ClassVar[str] = 'extract'

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('session',         type=str,            help='Session file path')
        parser.add_argument('-a', '--agent',   type=str,            help='Filter by agent ID')
        parser.add_argument('-e', '--errors',  action='store_true', help='Show errors only')
        parser.add_argument('-v', '--verbose', action='store_true', help='Show full content')
        parser.add_argument('-r', '--range',   type=str,            help='Line range (e.g., 30-50)')

    def run(self, args: argparse.Namespace) -> None:
        session_path = require_session_path(args.session)

        line_range: tuple[int, int] | None = None
        if args.range:
            parts      = args.range.split('-')
            line_range = (int(parts[0]), int(parts[1]))

        output = extract_session(
            session_path,
            agent_id=args.agent,
            errors_only=args.errors,
            verbose=args.verbose,
            line_range=line_range
        )
        for line in output:
            print(line)


class ErrorsCommand(Command):
    """
    Find all errors in session.
    """
    name: ClassVar[str] = 'errors'

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('session',         type=str, help='Session file path')
        parser.add_argument('-p', '--pattern', type=str, help='Filter errors by pattern')

    def run(self, args: argparse.Namespace) -> None:
        session_path = require_session_path(args.session)

        errors = find_errors(session_path, pattern=args.pattern)
        if not errors:
            print('No errors found')
        else:
            for err in errors:
                agent_str = f" [{err['agent_id']}]" if err['agent_id'] != 'main' else ''
                print(f"Line {err['line']}{agent_str}: {err['content']}")


class AgentsCommand(Command):
    """
    List agent IDs in session.
    """
    name: ClassVar[str] = 'agents'

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('session', type=str, help='Session file path')

    def run(self, args: argparse.Namespace) -> None:
        session_path = require_session_path(args.session)

        agents = list_agents(session_path)
        if not agents:
            print('No agents found in session')
        else:
            for agent_id in sorted(agents.keys()):
                info = agents[agent_id]
                if info['has_separate_log'] and (info['log_path'] is not None):
                    size_kb = info['log_path'].stat().st_size / 1024
                    print(f'{agent_id}  [log: {size_kb:.1f}KB]')
                else:
                    print(agent_id)


class ExportCommand(Command):
    """
    Export session as readable transcript.
    """
    name: ClassVar[str] = 'export'

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('session',        type=str, help='Session file path')
        parser.add_argument('-a', '--agent',  type=str, help='Filter by agent ID')
        parser.add_argument('-o', '--output', type=str, help='Output file path (default: stdout)')

    def run(self, args: argparse.Namespace) -> None:
        session_path = require_session_path(args.session)

        output_path = Path(args.output) if args.output else None
        result      = export_transcript(session_path, agent_id=args.agent, output_path=output_path)

        if output_path:
            print(f'Exported to: {result}')
        else:
            print(result)


class HierarchyCommand(Command):
    """
    Show agent spawn hierarchy.
    """
    name: ClassVar[str] = 'hierarchy'

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('session', type=str, help='Session file path')

    def run(self, args: argparse.Namespace) -> None:
        session_path = require_session_path(args.session)

        hierarchy = build_agent_hierarchy(session_path)
        lines     = format_hierarchy(hierarchy)
        for line in lines:
            print(line)


class SubagentsCommand(Command):
    """
    Show subagent summary with status.
    """
    name: ClassVar[str] = 'subagents'

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('session', type=str, help='Session file path')

    def run(self, args: argparse.Namespace) -> None:
        session_path = require_session_path(args.session)

        agent_summaries = get_subagent_summary(session_path)
        if not agent_summaries:
            print('No subagents found in session')
        else:
            print(f"{'Agent':<20} {'Spawned By':<12} {'Status':<10} {'Duration':<10} {'Tools':<6}")
            print('-' * 70)
            for agent in agent_summaries:
                status_icon = '✓' if agent['status'] == 'success' else '✗'
                error_hint  = f" ({cast('str', agent['error'])[:20]}...)" if agent.get('error') else ''
                print(
                    f"{agent['subagent_type']:<20} {agent['spawned_by']:<12} {status_icon} {agent['status']:<7} "
                    f"{agent['duration']:<10} {agent['tool_count']:<6}{error_hint}"
                )


class SubagentFilesCommand(Command):
    """
    List subagent log files for a session.
    """
    name: ClassVar[str] = 'subagent-files'

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('session', type=str, help='Session file path')

    def run(self, args: argparse.Namespace) -> None:
        session_path = require_session_path(args.session)

        subagent_files = list_subagent_files(session_path)
        if not subagent_files:
            print('No subagent log files found for this session')
        else:
            print(f"{'Agent ID':<12} {'Size':<12} {'Path'}")
            print('-' * 80)
            for agent_id, log_path in sorted(subagent_files.items()):
                size_bytes = log_path.stat().st_size
                if size_bytes >= (1024 * 1024):
                    size_str = f'{size_bytes / (1024 * 1024):.1f}MB'
                elif size_bytes >= 1024:
                    size_str = f'{size_bytes / 1024:.1f}KB'
                else:
                    size_str = f'{size_bytes}B'
                print(f'{agent_id:<12} {size_str:<12} {log_path}')


class TimelineCommand(Command):
    """
    Show timeline of events with agent context.
    """
    name: ClassVar[str] = 'timeline'

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('session',       type=str,              help='Session file path')
        parser.add_argument('-n', '--limit', type=int, default=100, help='Max events to show')

    def run(self, args: argparse.Namespace) -> None:
        session_path = require_session_path(args.session)

        events = get_timeline(session_path)
        for event in events[:args.limit]:
            print(event)

        if len(events) > args.limit:
            print(f'... ({len(events) - args.limit} more events, use -n to see more)')


class CompareCommand(Command):
    """
    Compare two sessions.
    """
    name: ClassVar[str] = 'compare'

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('session1', type=str, help='First session file path')
        parser.add_argument('session2', type=str, help='Second session file path')
        parser.add_argument(
            '-f',
            '--focus',
            choices=get_args(ComparisonFocus),
            default='all',
            help='What to focus comparison on',
        )

    def run(self, args: argparse.Namespace) -> None:
        session1_path = require_session_path(args.session1)
        session2_path = require_session_path(args.session2)

        results = compare_sessions(session1_path, session2_path)

        print('=' * 70)
        print('SESSION COMPARISON')
        print('=' * 70)
        print()
        print(f'Session 1: {session1_path.name}')
        print(f'Session 2: {session2_path.name}')

        if args.focus in ('agents', 'all'):
            print('\n--- AGENTS ---')

            print(f"\nSession 1 agents ({len(results['session1']['agents'])}):")
            for a in results['session1']['agents']:
                status_icon = '✓' if a['status'] == 'success' else '✗'
                print(f"  {status_icon} {a['subagent_type']} ({a['agent_id']})")

            print(f"\nSession 2 agents ({len(results['session2']['agents'])}):")
            for a in results['session2']['agents']:
                status_icon = '✓' if a['status'] == 'success' else '✗'
                print(f"  {status_icon} {a['subagent_type']} ({a['agent_id']})")

        if args.focus in ('errors', 'all'):
            print('\n--- ERRORS ---')

            print(f"\nSession 1 errors ({len(results['session1']['errors'])}):")
            for e in results['session1']['errors'][:5]:
                print(f"  Line {e['line']}: {e['content'][:60]}...")

            print(f"\nSession 2 errors ({len(results['session2']['errors'])}):")
            for e in results['session2']['errors'][:5]:
                print(f"  Line {e['line']}: {e['content'][:60]}...")

        if args.focus in ('tools', 'all'):
            print('\n--- TOOL USAGE ---')
            all_tools = set(results['session1']['tool_counts'].keys()) | set(results['session2']['tool_counts'].keys())

            print(f"\n{'Tool':<20} {'Session 1':<12} {'Session 2':<12} {'Diff':<10}")
            print('-' * 54)
            for tool in sorted(all_tools):
                c1 = results['session1']['tool_counts'].get(tool, 0)
                c2 = results['session2']['tool_counts'].get(tool, 0)

                diff     = c2 - c1
                diff_str = f'+{diff}' if diff > 0 else str(diff)
                print(f'{tool:<20} {c1:<12} {c2:<12} {diff_str:<10}')


# ==================================================
# Script entry point + command-line argument parsing
# ==================================================


def build_parser() -> argparse.ArgumentParser:
    """
    Build argument parser with subcommands from the command registry.

    :return: configured :class:`argparse.ArgumentParser`.
    """
    parser     = argparse.ArgumentParser(description='Extract and analyze Claude Code session logs')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    for cmd in REGISTERED_COMMANDS.values():
        subparser = subparsers.add_parser(
            cmd.name,
            help=cmd.description,
            description=cmd.description,
        )
        cmd.add_arguments(subparser)

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """
    Parse CLI arguments and dispatch to the appropriate command handler.

    :param argv: argument list of parse. Defaults to ``sys.argv[1:]``
    """
    parser = build_parser()
    args   = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if cmd := REGISTERED_COMMANDS.get(args.command):
        cmd(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
