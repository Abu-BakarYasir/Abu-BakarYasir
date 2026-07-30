# Vendored brand marks

Source: [Simple Icons](https://github.com/simple-icons/simple-icons),
released under **CC0 1.0** (public domain dedication — no attribution
required; this note is courtesy, not obligation).

Each file is the unmodified 24×24 upstream SVG. `scripts/build_stack.py`
reads the single `<path>` out of each one and inlines it into `stack.svg`,
so the rendered page makes no request for them.

They are vendored rather than fetched from a CDN at build time so the build
is reproducible offline, and rendered in the page's own ink rather than
brand colours — see the note at the top of `build_stack.py`.

Trademarks belong to their respective owners; the marks are used here only
to identify the technologies in use.
