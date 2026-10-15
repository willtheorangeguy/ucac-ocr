# Pool Headcount — Documentation

These guides cover running `ucac-ocr`, importing and reviewing pool counts, maintaining its durable data, and developing the application. They describe the source in this checkout; a previously published container can have an earlier feature set. Use a source build when you need the behavior of the current checkout.

```text
docs/
├── README.md
├── quickstart.md
├── installation.md
├── configuration.md
├── usage.md
├── rules.md
├── commands.md
├── api.md
├── architecture.md
├── deployment.md
├── development.md
├── testing.md
├── faq.md
├── troubleshooting.md
├── roadmap.md
└── internal/
    └── known-issues.md
```

| Guide | Read it for |
| --- | --- |
| [Quickstart](./quickstart.md) | First installation and first workbook |
| [Installation](./installation.md) | Published containers, local builds, Windows, and Linux |
| [Configuration](./configuration.md) | Every application setting and Compose variable |
| [Usage](./usage.md) | Upload, table selection, review, and download |
| [Count and workbook rules](./rules.md) | Blanks, addition, copy-down, layouts, and cell mapping |
| [Commands](./commands.md) | Complete CLI reference |
| [API](./api.md) | Routes, request bodies, responses, and Ollama integration |
| [Architecture](./architecture.md) | Components, schema, storage, and recovery |
| [Deployment](./deployment.md) | Health, upgrades, backup, restore, and LAN access |
| [Development](./development.md) | Source setup, release pipeline, and contribution checks |
| [Testing](./testing.md) | Regression coverage, browser checks, and calibration |
| [FAQ](./faq.md) | Accuracy, privacy, performance, and workbook behavior |
| [Troubleshooting](./troubleshooting.md) | Concrete diagnostics and recovery actions |
| [Roadmap and limits](./roadmap.md) | Remaining validation and deliberate constraints |
| [Known issues](./internal/known-issues.md) | Defects recorded during documentation |

The root [validation record](../VALIDATION.md) contains historical measurements and links to saved evidence. The [implementation plan](../IMPLEMENTATION_PLAN.md) is historical design context; later changes supersede its original strict OCR and daily-sheet export policies. Return to the [project README](../README.md).
