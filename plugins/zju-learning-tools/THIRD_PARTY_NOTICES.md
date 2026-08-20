# Third-party notices

ZJU Learning Tools includes one unmodified source file from
[LAZY v0.2.6](https://github.com/YangShu233-Snow/Learning_at_ZJU_third_client/tree/bc403fabd8bde0163fc75aa299ac3e1b24d0c3f3),
copyright its contributors and licensed under LGPL-3.0-only:

- `vendor/lazy-core/lazy_core/LoginRSA.py`

The complete corresponding source of the included component is present in this distribution.
The component is loaded from an isolated path at runtime and may be replaced with a compatible
modified version. The full GNU Lesser General Public License v3.0 text is in
`vendor/lazy-core/LICENSE`.

The optional MCP-unavailable fallback installs the exact PyPI package
[tronclass-cli 0.2.8](https://pypi.org/project/tronclass-cli/0.2.8/) in an isolated, locked Python
3.9 environment. tronclass-cli is copyright Howyoung Zhou and contributors and licensed under the
MIT License. No tronclass-cli source is copied into this repository; the plugin invokes its CLI
command machinery only through a restricted wrapper.

No code was copied from the design-reference repositories listed in `UPSTREAM.json`.
