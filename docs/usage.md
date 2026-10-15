# Pool Headcount — Usage

Use the web app at <http://localhost:8000> after [installation](./installation.md). The main page creates batches; each batch page shows table boxes, progress, flagged images, and the latest download. Batch management and detailed evidence remain available through the [CLI](./commands.md) and [API](./api.md).

## Create a batch

Choose the year/month, add a supported workbook, and choose the workbook mode explicitly:

- **new-month** resets the selected month's inputs in the exported workbook. Other months and workbook parts are retained when using a monthly input workbook.
- **continuation** retains the selected month's existing counts, notes, and names. Existing dated inputs must belong to that month; counts that conflict with new photos become review items.

The original workbook is saved unchanged. Upload photos together or in ZIPs. JPEG/MPO, PNG, and WebP are supported. iPhone MPO uses the primary photo with EXIF orientation applied; Live Photo MOV clips are skipped. Unsupported/corrupt images become source issues, while unsafe ZIP paths are rejected. Identical photo hashes are deduplicated within the batch.

Choose the photo layout before starting the import:

| UI choice | API value | Use |
| --- | --- | --- |
| Automatic | `auto` | Legacy printed default for morning/afternoon; monthly default for full-day. |
| Old printed | `legacy` | Original form with User Group + Coaches. |
| New printed | `new-paper` | Revised printed form with External and Internal. |
| New monthly | `monthly` | Monthly workbook form, including a photographed partial section. |

The legacy and revised paper forms have the same column count, so selecting **New printed** explicitly matters. Start the import. The upload persists files and records before redirecting; processing continues if you close the browser.

## Check table boxes

The worker validates seven columns and the expected count rows before scheduling OCR. Morning, afternoon, and full-day sections are determined from 31, 36, or 67 count rows. Mild slant, bowed paper, uneven spacing, and a few faint separators can be tolerated; substantial missing grid evidence still needs review.

Use **Review table boxes** to inspect saved outlines. The photo selector includes individual members from ZIP uploads. For an uncertain or incorrect box:

1. Select the intended photo. **Find box automatically** retries detection.
2. Use **Start corners again** to clear your selection.
3. Click top-left, top-right, bottom-right, bottom-left around **all seven columns, count rows only**, excluding the column header. On the monthly form, include DATE through NOTES for one day's rows.
4. The fourth click saves automatically. If the row count cannot decide the section, select it explicitly; the underlying grid must still validate.
5. Use **Save box / layout** to change layout without repeating clicks.

Polling retains your selected photo and incomplete clicks. The original remains stored alongside the rectified table and transform. Automatic detection can retain two separate sections in one photo; manual corner selection in the picker replaces the current selection with one table. To define two tables manually, use the [source configuration API](./api.md).

For the bundled 1080 × 1440 October 9 reference photo only, the normalized morning-table corners are `[[154,262],[918,252],[968,1185],[138,1200]]`. These coordinates are not a general preset for other images.

## Review counts and source issues

The default single pass accepts readable rough counts, numeric letter substitutions, likely blanks, and supported copy-down marks. Unreadable cells and conflicting sources need review. See [count rules](./rules.md) for exact semantics.

Image corrections are grouped under each photo. Enter a count, including explicit `0`, or choose blank. Reviewer names are required for review decisions. Source-level issues can be acknowledged as unusable evidence, with an audit record. Acknowledging a source does not create counts for it.

For date repair, source reprocessing, coverage acknowledgement, or edits to already accepted cells, use the API/CLI. Date-only assignment reuses successful readings; overriding contradictory recognized dates requires `confirm:true`. Reprocessing creates a new source version. Automatic processing protects reviewed cells and flags new evidence that could conflict.

Adding a replacement photo retains the old photo. Observations of the same time/cell are reconciled, not summed. Resolve conflicts explicitly. Resume a cancelled batch before adding photos.

## Download and interpret the report

When processing settles, the worker generates a monthly workbook. Review edits generate another immutable revision without rerunning OCR. Step 4 displays only the latest download as `YYYY-MM-headcounts.xlsx`; older revisions and their checksums remain available through status and file APIs.

Unresolved cells export as blank and are listed in `IMPORT REPORT`. Missing dates/sections keep the workbook provisional until acknowledged as no source/not applicable; use `coverage JOB_ID` only after checking that missing coverage is intentional. The report distinguishes unresolved evidence from accepted blank cells. Inspect both the workbook and its report before relying on results.

All exports use the new monthly layout, even when the uploaded workbook was legacy. Excel/LibreOffice rendering and whole-month OCR accuracy remain validation gaps; see [roadmap](./roadmap.md).
