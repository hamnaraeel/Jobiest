"""Step 8: AI job search agent / orchestrator.

This package connects Steps 1-7 into one controllable agent -- it does
not reimplement any of their functionality. Every tool in
tool_registry.py is a thin, permission- and schema-checked wrapper
around an existing service or API router function. See ../../README.md
("Step 8: AI job search agent") for the architecture, safety model, and
usage examples.
"""
