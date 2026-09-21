# Changelog — moltrust-mcp-server

## 1.2.3

Every tool that takes a DID checks its form before the call.

The package forwarded whatever it was given straight into the URL. The MolTrust
server log for September carries the result: `did:moltrust:` with nothing after
it, and `admin` — a model copying the placeholder out of this package's own
docstrings, and a model guessing. Both cost a round trip and came back as a 400
the model then had to interpret.

Fourteen tools, one check, and a test that fails if a fifteenth forgets it.
Well-formed foreign DIDs — `did:web`, `did:key`, `did:base`, `did:pkh` — pass
through: the grammar is W3C DID Core §3.1, the same one the API and the
MoltGuard gate use, so a DID this package accepts is one they accept too.

