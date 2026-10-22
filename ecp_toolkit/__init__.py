"""ecp: the AI Engineering Control Plane CLI.

The kit package name is ``ecp_toolkit`` and the console script is ``ecp``.

The package mounts the family's kit repos rather than wrapping them: each kit
repo ships an ``ecp-commands.toml`` declaring the commands ``ecp <kit>``
offers, and ``ecp`` mounts one subcommand per declared command at parser-build
time. Discovery is repo presence. A fresh clone that ships no kit checkout
mounts nothing, and adding a kit to the workspace mounts its commands with no
code change here.
"""

from __future__ import annotations

__version__ = "0.1.0"
