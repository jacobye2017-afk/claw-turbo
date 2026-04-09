"""Bash command executor for matched routes."""

import logging
import subprocess
from dataclasses import dataclass

from .router import MatchResult

logger = logging.getLogger("claw-turbo")


@dataclass
class ExecResult:
    success: bool
    return_code: int
    stdout: str
    stderr: str
    command: str


def execute(match: MatchResult, timeout: int = 300) -> ExecResult:
    """Execute the matched route's command via bash."""
    command = match.rendered_command
    logger.info("Executing: %s", command)

    try:
        proc = subprocess.run(
            ["bash", "-c", command],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        result = ExecResult(
            success=proc.returncode == 0,
            return_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            command=command,
        )
        if result.success:
            logger.info("Command succeeded (exit 0)")
        else:
            logger.warning(
                "Command failed (exit %d): %s",
                proc.returncode, proc.stderr[:200],
            )
        return result

    except subprocess.TimeoutExpired:
        logger.error("Command timed out after %ds: %s", timeout, command)
        return ExecResult(
            success=False,
            return_code=-1,
            stdout="",
            stderr=f"Command timed out after {timeout}s",
            command=command,
        )
    except Exception as e:
        logger.error("Command execution error: %s", e)
        return ExecResult(
            success=False,
            return_code=-1,
            stdout="",
            stderr=str(e),
            command=command,
        )
