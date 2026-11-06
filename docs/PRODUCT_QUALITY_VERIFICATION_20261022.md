# Verification results — October 22, 2026

The effective results across 120 test modules, including the explicitly recorded latest reruns, are **1011 passed, 18 failed, and 1 skipped**. All 18 outstanding failures are execution-environment denials, not passing checks.

- One candidate-provider test cannot access Windows Credential Manager: error 5 / access denied.
- Seventeen phone-studio HTTP tests cannot bind a local socket: Windows error 10013.
- One desktop availability test was skipped by its existing fixture.
- The initial combined test run encountered a native Windows Tk handle exception. Running modules in separate processes completed every module without a native crash.

The isolated run originally reported 1007 passed / 19 failed / 1 skipped, before the final three text-answer tests were added and before the cover validation-order correction. The one Signature-cover regression was fixed and all three Signature-cover tests passed on rerun. The latest final affected-module run passed **89/89**, including all 22 new puzzle-integrity tests. The JSON report preserves both the original run and the module-level effective results; the totals above do not double-count repeated tests.

Additional checks passed: syntax compilation of all touched Python modules, the pinned CPython 3.13.15 64-bit runtime check, all-theme validation, and Git whitespace checks for the edited tracked implementation files.

Production validation: 50 mathematical puzzle checks, 100 independent PDF grid readbacks, 84 Poppler-rendered pages, embedded text fonts, and local interior/wrap preflight. Final package: zero local blockers and one editorial coverage warning. Human teacher/editorial review, aesthetic signoff, physical proof, and marketplace preview remain pending.

Detailed machine-readable results: `PRODUCT_QUALITY_VERIFICATION_20261022.json`.
