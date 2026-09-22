# Changelog — moltrust-mcp-server

## 1.2.4

Withheld is not "not found", and the tools now say so.

`verified: false` covers two findings that mean opposite things to whoever
reads the answer. One is that we looked and there is nothing — a did:moltrust
we never registered. The other is that we hold no opinion: the DID belongs to a
method we do not issue, or the score has too few endorsers behind it. The API
has always separated them with `withheld`, `withheld_reason` and a note that
says in so many words that withheld is not a negative finding.

This package threw that away. A well-formed `did:web:example.com` came back as
"Agent not found in MolTrust registry" — a checked negative, reported for an
answer that was never checked. `moltrust_verify`, `mt_get_badge` and
`moltrust_erc8004` rendered no withheld at all; `mt_get_trust_score` rendered
it but asserted one fixed reason for every case, so a foreign DID was reported
as short of endorsers.

Four tools, three states apart, and the reason and note carried verbatim rather
than paraphrased. The vectors the tests run on are recorded from the live API,
because the claim under test is that the package renders what the API sends.

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

