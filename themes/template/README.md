# External theme template

Copy this folder, set your own `id` in `metadata.json`, edit the CSS, then import it
from the settings page. An exported copy already imports cleanly, so the loop is:

export -> edit -> import.

The exported folder's modification time reflects the time of export; individual files keep
their template modification times.

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

## Preview metadata (optional)

`preview` is what the GUI shows on its theme preview stage before any document exists. It
is six colour tokens -- `background`, `surface`, `text`, `muted`, `accent`, `border` -- and
nothing else; `#rgb` and `#rrggbb` are the only accepted forms. The schema is canonical on
purpose: a missing key, an extra key or a value that is not a colour makes the preview
unavailable, and the GUI then says so.

A preview is a convenience, never a verdict: a theme without a `preview` block, or with a
broken one, still imports, still carries into documents, and still converts. Only the
static preview is unavailable.

## Decorations (optional)

`decorations.css` is where local assets go. It is an ordinary CSS file in `files`; the
template ships it with a commented example, because the only rule that matters is that the
`url()` target must be a real file inside the theme directory.
