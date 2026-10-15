"""Automatic fixer: a generic engine driven entirely by migration-pack rules.

  callsite.py   language-neutral call-site model + value resolution results
  pyfix.py      Python adapter (libcst: lossless, keeps formatting and comments)
  jsfix.py      JavaScript/TypeScript adapter (lexer-based, dependency-free)
  engine.py     evaluates pack rules per call site and turns `fix` specs into edits
  verify.py     applies the patch to a scratch copy, checks syntax/idempotence and runs eval

No provider names, endpoints or parameter names are hard-coded here: they all come
from the packs' `signals[].call` and `rules[].fix` entries.
"""
from .engine import FixItem, FixResult, plan_fixes, write  # noqa: F401
