---
name: systematic-debugging
description: Investigate root cause before fixing technical issues.
---

# Systematic Debugging

Use this skill when the user reports a bug, test failure, build failure, or
unexpected behavior.

## Process

1. Reproduce the issue with the smallest reliable command.
2. Read the exact error text and relevant source code.
3. Trace where the bad state enters the system.
4. State the root cause before changing code.
5. Add or update a focused test when behavior changes.
6. Verify the original command succeeds after the fix.

Do not jump straight to a patch before you understand why the failure happens.
