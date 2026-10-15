# Roadmap and limits

This page records gaps supported by the implementation and [historical validation record](https://github.com/willtheorangeguy/ucac-ocr/blob/HEAD/VALIDATION.md). It is not a schedule or a promise of future features. Actionable defects discovered during documentation are tracked separately in [known issues](https://github.com/willtheorangeguy/ucac-ocr/blob/HEAD/docs/internal/known-issues.md).

## Accuracy and operational validation

Whole-sheet and whole-month OCR accuracy remain unmeasured. The real reference-photo check covers a manually checked subset; geometry success on 18 photos establishes cropping, not recognized counts. New-format handwritten photos still need live OCR validation beyond synthetic crop mapping.

The existing validation plan calls for 10–20 diverse manually checked sheets, comparisons across context sizes and thinking profiles, exact numeric/blank/row/date metrics, review workload, missed automatic errors, and a representative real month on the operator's hardware. The synthetic 62-source endurance run does not substitute for those measurements. See [testing](./testing.md).

## Spreadsheet engine validation

OOXML fidelity, formula text, input placement, blank/zero semantics, and independent expected averages have regression coverage. Actual Excel/LibreOffice rendering, print comparison, cached summary results, and successful optional recalculation still require independent validation. Python does not implement Excel's LET/FILTER formula engine.

## Operational constraints

- One worker owns one local data directory. There is no distributed queue or network-filesystem SQLite deployment.
- There are no application accounts or per-user authorization controls; LAN deployment requires a protected reverse proxy.
- Supported images are JPEG/MPO, PNG, and WebP. HEIC and video extraction are not implemented; MOV files are skipped.
- The browser picker manually defines one table at a time. Two-table source configuration is available through the API.
- The CLI import/add commands use automatic photo layout and expose no layout flag.
- Backups retain absolute artifact paths. Restoring to another absolute path needs manual metadata migration; there is no rebasing command.
- Artifacts and original evidence are retained without an automatic pruning policy.
- A local disconnect cannot prove remote inference stopped; cooldown reduces repeated overlapping requests but cannot control unrelated Ollama clients.

The default rough-count profile, simplified four-step report, and monthly export layout are deliberate current choices, replacing parts of the original [implementation plan](https://github.com/willtheorangeguy/ucac-ocr/blob/HEAD/IMPLEMENTATION_PLAN.md). Optional strict verification remains configurable.
