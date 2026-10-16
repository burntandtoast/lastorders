# Copyright (c) 2026 Burnt and Toast Studios Ltd. Proprietary; see LICENSE-COMMERCIAL.
"""Language-neutral description of an API call site, shared by the language adapters."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class _Unresolved:
    def __repr__(self):
        return "UNRESOLVED"

    def __bool__(self):
        return False


UNRES: Any = _Unresolved()


@dataclass
class Arg:
    name: str
    value: Any = UNRES                 # literal value when statically known, else UNRES
    src: str = ""                      # source text of the value
    nested: dict[str, "Arg"] | None = None   # keys of a dict/object literal value (one level)
    via_env: str | None = None         # env var name when the value is an env lookup with a literal default


@dataclass
class CallSite:
    file: str
    line: int
    lang: str
    callee: str                         # dotted callee, e.g. "client.chat.completions.create"
    args: dict[str, Arg] = field(default_factory=dict)
    opaque: bool = False                # **kwargs / ...spread / non-literal options object: args incomplete
    key: Any = None                     # adapter handle (position) used to apply edits

    def has(self, path: str) -> bool:
        return self.get(path) is not None

    def get(self, path: str) -> Arg | None:
        head, _, rest = path.partition(".")
        a = self.args.get(head)
        if a is None or not rest:
            return a
        return (a.nested or {}).get(rest)

    def literal_params(self, skip: set[str]) -> dict:
        """Statically known argument values (dotted children become nested dicts)."""
        out: dict = {}
        for n, a in self.args.items():
            if n in skip:
                continue
            if a.value is not UNRES:
                out[n] = a.value
        return out


@dataclass
class Edit:
    """One change to one call: rename / remove / set (dotted path) / replace (a value)."""
    op: str                 # rename | remove | set | replace
    path: str
    new_name: str | None = None
    value: Any = None
