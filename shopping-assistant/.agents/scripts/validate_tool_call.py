#!/usr/bin/env python3
"""
.agents/scripts/validate_tool_call.py

PreToolUse hook script for the shopping-assistant project.

The agent runtime pipes the tool call details as JSON on stdin before
every `run_command` execution. This script inspects the command and:
  - Blocks known destructive or dangerous commands (exit code 1)
  - Allows everything else (exit code 0)

Exit codes:
  0 → allow the command to proceed
  1 → block the command; stdout is shown to the agent as the reason
"""

import json
import sys

# ---------------------------------------------------------------------------
# Destructive / dangerous command patterns to block.
# Each entry is a plain substring that, if found in the command, causes
# an immediate block. Case-insensitive matching is applied.
# ---------------------------------------------------------------------------
BLOCKED_COMMANDS = [
    "rm -rf /",  # Wipe entire filesystem root
    "rm -rf *",  # Wipe everything in current directory
    "rm -rf .",  # Wipe current directory
    "del /f /s /q",  # Windows: force-delete files recursively
    "format c:",  # Windows: format the system drive
    ":(){:|:&};:",  # Fork bomb
    "shutdown",  # System shutdown
    "| bash",  # Pipe anything into bash (e.g. curl url | bash)
    "| sh",  # Pipe anything into sh
    "> /dev/sda",  # Write directly to disk device
    "dd if=/dev/zero",  # Overwrite disk with zeros
    "mkfs",  # Format a filesystem
]


def read_tool_call() -> dict:
    """Read and parse the JSON tool call payload from stdin."""
    try:
        raw = sys.stdin.read().strip()
        if not raw:
            # Nothing piped in — allow (not running in hook context)
            sys.exit(0)
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        # Malformed payload — print warning but allow (fail open)
        print(f"[validate] WARNING: Could not parse payload: {exc}", file=sys.stderr)
        sys.exit(0)


def extract_command(payload: dict) -> str:
    """Pull the command string out of the tool call payload."""
    # The agent runtime may use different key names depending on version
    tool_input = payload.get("tool_input") or payload.get("input") or payload
    return str(tool_input.get("command") or tool_input.get("CommandLine") or "").strip()


def main() -> None:
    payload = read_tool_call()
    command = extract_command(payload)

    if not command:
        print("[validate] No command found in payload — allowing.", file=sys.stderr)
        sys.exit(0)

    print(f"[validate] Inspecting command: {command!r}", file=sys.stderr)

    # Check command against every blocked pattern
    command_lower = command.lower()
    for pattern in BLOCKED_COMMANDS:
        if pattern.lower() in command_lower:
            # Exit 1 — stdout message is shown to the agent as the block reason
            print(
                f"[validate] BLOCKED: Destructive command detected.\n"
                f"  Command : {command!r}\n"
                f"  Matched : {pattern!r}\n"
                f"  Reason  : This command pattern is unsafe and has been blocked\n"
                f"            by the PreToolUse security hook. If this was\n"
                f"            intentional, get explicit approval and update\n"
                f"            hooks.json accordingly."
            )
            sys.exit(1)

    # No blocked pattern matched — allow the command
    print("[validate] ALLOWED: Command passed security checks.", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
