## What this changes

<!-- One or two sentences. Link the issue if there is one. -->

## Why

<!-- The problem being solved, not just the mechanics of the change. -->

## Checklist

- [ ] `pytest` passes
- [ ] `ruff check .` and `ruff format --check .` pass
- [ ] New behaviour has a test — especially anything touching subtitle text,
      timing, or the segment/translation contract, where a mistake produces
      silently shifted output rather than a visible error
- [ ] Docs updated if a command, flag or file format changed
