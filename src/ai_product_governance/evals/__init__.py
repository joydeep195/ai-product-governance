"""Model-agnostic evaluation harness.

Runs the same scenarios against any supported model twice (with the skill loaded
through a generic skill-host emulator, and with a strong expert-persona baseline),
grades each response with a blind rubric judge plus deterministic checks, and gates
CI on quality, critical failures, skill uplift and regressions against a baseline.
"""
