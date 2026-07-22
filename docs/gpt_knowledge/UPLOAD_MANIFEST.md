# GPT knowledge upload manifest

## GPT Builder profile

- **Name:** CrystEngKit User Manual & Workflow Assistant
- **Description:** Practical guidance for CrystEngKit-ORCA setup, workflows, files, troubleshooting, and scientifically responsible interpretation.
- **Code Interpreter & Data Analysis:** Enable for uploaded logs, CSV/JSON settings, and directory listings.
- **Web search:** Optional; use only for current official external-program or repository information and distinguish it from bundled CrystEngKit behavior.
- **Image generation:** Not required.
- **Actions:** Not required for the first version.

Suggested conversation starters:

- `Guide me from a CIF to a checked ORCA input.`
- `Which files do I need for an NTO, NCI, ESP, or QTAIM analysis?`
- `Why is this CrystEngKit control disabled?`
- `Help me troubleshoot this ORCA or Multiwfn error.`
- `Show me the absorption-to-emission TD-DFT workflow.`
- `Turn my problem into a concise CrystEngKit bug report.`

Upload these nine files as GPT Knowledge:

1. `01_USER_MANUAL.md`
2. `02_WORKFLOW_RECIPES.md`
3. `03_TROUBLESHOOTING.md`
4. `04_GLOSSARY_AND_INTERPRETATION.md`
5. `05_GUI_CONTROL_REFERENCE.md`
6. `06_FILES_AND_FOLDERS.md`
7. `07_SETTINGS_AND_DEFAULTS.json`
8. `08_FEATURE_CAPABILITY_MATRIX.csv`
9. `09_VERSION_AND_FEATURES.json`

Do not upload `GPT_BUILDER_INSTRUCTIONS.md` as Knowledge. Paste its content into the GPT Builder Instructions field. `UPLOAD_MANIFEST.md` is an owner-facing checklist and does not need to be uploaded.

Enable Code Interpreter & Data Analysis if the assistant should inspect uploaded CSV, JSON, logs, settings, or directory listings. Web search is optional for current official ORCA, Multiwfn, Python-package, and CrystEngKit repository information; instruct the GPT to distinguish external current documentation from bundled CrystEngKit behavior.

Rebuild after documentation changes:

```text
python docs/build_gpt_knowledge.py
```
