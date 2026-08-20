# Vendored LAZY compatibility subset

This directory contains `src/lazy/core/encrypt/LoginRSA.py` from LAZY
v0.2.6, commit `bc403fabd8bde0163fc75aa299ac3e1b24d0c3f3`. It is imported dynamically by the
MIT-licensed runtime and can be replaced with an interface-compatible modified version.

Only line endings were normalized; the source logic is unchanged. Only the CAS RSA compatibility implementation is distributed. LAZY's CLI, GUI, generic API
dispatcher, credential manager, and AGPL-licensed server are not included. See `UPSTREAM.json`
and `THIRD_PARTY_NOTICES.md` at the plugin root.
