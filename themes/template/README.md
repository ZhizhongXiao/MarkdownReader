# External theme template

Copy this folder, set your own `id` in `metadata.json`, edit the CSS, then import it
from the settings page. An exported copy already imports cleanly, so the loop is:

export -> edit -> import.

## Rules

- `id` is a lowercase slug matching `^[a-z][a-z0-9-]{1,31}$`. It becomes the installed
  directory name and the value the reader stores, and it may not be `base`, `modern`,
  `office`, `vscode` or `default`.
- `files` lists the CSS files you provide, in load order. Only `.css` is allowed.
- A theme is **visual only**: no JavaScript, no custom viewer DOM, no `@import`, and no
  remote `url()`. Local assets go in `assets/` and are referenced with a relative
  `url(assets/...)`; they are embedded into every generated document, which is why a
  document keeps working after the theme is deleted.
- Scope every rule to `html[data-theme-id="<your id>"]`, and add
  `body.theme-<your id>` when the rule targets descendants of `body`.
- `extends` names a theme whose tokens you inherit (`base` is the packaged fallback, so
  almost every theme only overrides the variables it cares about).
