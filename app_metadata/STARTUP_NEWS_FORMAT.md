# Startup news manifest

All CrystEngKit-ORCA releases read the same version-independent manifest:

`https://raw.githubusercontent.com/torubaev/crystengkit-orca-v1.0/main/app_metadata/startup_news.json`

Publishing news requires changing this manifest on `main`; rebuilding installers is not required.

The `content` object supports four types:

- `text` — a plain-text announcement.
- `markdown` — a Markdown page opened in the browser.
- `html` — a web page opened in the browser.
- `image` — an image opened in the browser.

The splash always renders `content.summary` as safe plain text. `content.url` is opened by the action button, whose caption comes from `content.action_label`.

Example:

```json
{
  "schema": 2,
  "title": "CrystEngKit-ORCA news",
  "content": {
    "type": "markdown",
    "summary": "A short message shown in the startup window.",
    "url": "https://github.com/example/news/blob/main/news.md",
    "action_label": "Read news"
  },
  "message_id": "unique-message-id",
  "severity": "info",
  "force_show": false
}
```

Legacy `message` and `details_url` fields remain supported for older manifests.
