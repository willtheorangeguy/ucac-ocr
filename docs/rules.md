# Count and workbook rules

These rules describe the current implementation. The original [implementation plan](https://github.com/willtheorangeguy/ucac-ocr/blob/HEAD/IMPLEMENTATION_PLAN.md) required stricter acceptance and daily-sheet output; later operator choices superseded those policies.

## Count semantics

- Numeric zero is a measured `0`; blank is an empty cell. They remain distinct through review and export.
- Only nonnegative integers and integer addition are supported. Addition is calculated locally from validated terms; each numeric term and each manual count is bounded at 1,000,000,000.
- The rough profile substitutes OCR letters only within complete numeric/addition expressions: O/Q/D → 0, I/L/l/| → 1, Z → 2, S → 5, G → 6, B → 8, including configured lowercase variants. Raw ink text is retained.
- Readable corrections and likely blank readings can be automatically accepted in rough mode. Unreadable numeric ink stays unresolved.
- Arrows and quotation/ditto marks copy the immediately preceding schedule slot in the same date and column. A preceding accepted blank copies as blank; numeric zero copies as zero.
- Copy-down works across bands and photos in chronological order. A missing or conflicting predecessor requires review. Edits above propagate to unreviewed dependents, while reviewed overrides are protected.
- Multiple photos of one time slot are observations of the same count, not quantities to add. Conflicting observations require a decision.

`ROUGH_COUNTS=false` and `VERIFICATION=always` request detailed readings and independent A/B comparison. Strict comparisons distinguish incompatible terms even when their totals match. `THINK` is configured separately. See [configuration](./configuration.md).

## Schedule and columns

[layout.py](https://github.com/willtheorangeguy/ucac-ocr/blob/HEAD/app/layout.py) defines 67 quarter-hour slots: 31 morning slots from 05:15 through 12:45, followed by 36 afternoon slots from 13:00 through 21:45. OCR results must match expected time order, with no duplicate, missing, or shifted rows.

| Display column | Stored/API key | Monthly Excel column |
| --- | --- | --- |
| Public | `public` | D |
| External | `external` | E |
| Internal | `group` | F |
| Dry | `dry` | G |

The internal key `group` remains for compatibility with saved jobs; it now means Internal. Legacy **User Group + Coaches** counts become Internal, and External stays blank for legacy photos. New printed and monthly layouts read External separately.

## Workbook behavior

The validator accepts the legacy daily-sheet workbook, including `MASTER` formulas referring only to Boundary B, and the Fall 2026 monthly workbook containing `BLANK`. Exports always use a `DATA ENTRY - MON YYYY` monthly sheet, with 70 rows per day and time in column C. Dates and times are written explicitly, including only real calendar days, rather than relying on uncached formulas for placement.

The first time slot's row is `4 + (day - 1) * 70`; later schedule slots add their zero-based index. For example, October 9 at 05:15 maps to row 564 and Public/External/Internal/Dry occupy D564:G564. The date for that day is at G562.

When a monthly workbook is uploaded, unrelated months, summaries, charts, styles, merges, protection, and printer parts are preserved. New-month replaces just the selected month's entry sheet from `BLANK`; continuation retains that month's counts, notes, and names. Legacy inputs use the bundled [sanitized monthly template](https://github.com/willtheorangeguy/ucac-ocr/blob/HEAD/app/assets/README.md), which contains no sample attendance data.

Original uploads and previous exports are kept. A restart queues a one-time monthly export for settled legacy exports without repeating successful OCR; paused/cancelled jobs remain paused/cancelled.

## Formula calculation

Exports request recalculation on open and clear stale summary caches. Python does not evaluate Excel's LET/FILTER summaries. `IMPORT REPORT` contains independently calculated per-time averages. Optional `LIBREOFFICE` creates a separate recalculated file, verifies expected inputs/averages, and retains the original if conversion or verification fails. Native Excel/LibreOffice visual rendering and the successful recalculation path remain unverified in the historical record.

See [usage](./usage.md) for review and [testing](./testing.md) for validation scope.
