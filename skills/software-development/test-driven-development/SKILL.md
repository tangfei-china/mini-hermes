---
name: test-driven-development
description: Write a failing test before changing production behavior.
---

# Test-Driven Development

Use this skill when adding a feature, fixing a bug, or changing behavior.

## Process

1. Write one focused test for the new behavior.
2. Run it and confirm it fails for the expected reason.
3. Implement the smallest change that makes the test pass.
4. Run the focused test again.
5. Run the full test suite if the change affects shared behavior.

Do not treat a test that only passes after the implementation as proof that the
test would have caught the missing behavior.
