"""Cached accessors for global project URL mapping JSON files."""

from __future__ import annotations

import json
from functools import cache
from importlib.resources import files


@cache
def _load(filename: str) -> dict:
    resource = files(__package__).joinpath(filename)
    with resource.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_moved_urls() -> dict[str, str]:
    return _load("moved_project_urls.json")


def get_unreachable_urls() -> frozenset[str]:
    return frozenset(_load("unreachable_project_urls.json").keys())
