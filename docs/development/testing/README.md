# Testing

The test strategy and test plans: what is tested at which level, fixtures, measurements and known gaps. How tests are
written (names, layout, fakes) is in [`../conventions.md`](../conventions.md) (Tests), and the gates they must pass are in
[`../constraints.md`](../constraints.md).

| File | What it is |
|---|---|
| [calibration.md](calibration.md) | How the default confidence threshold was measured: the labelled corpus and harness in `tests/calibration/`, the results, what they mean, and how to repeat them on your own documents. |

Test layout: `tests/core/` and `tests/cli/` mirror the packages 1:1, `tests/scripts/` tests `scripts/`,
`tests/mock_library/` and `tests/mock_flat_library/` are hand-built library fixtures, and `tests/calibration/` holds
the calibration corpus.
