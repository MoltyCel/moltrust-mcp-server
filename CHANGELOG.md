# Changelog — moltrust-mcp-server

## 1.2.6

Registry description and README only; the package code is unchanged.

The hosted remote at `https://api.moltrust.ch/mcp` serves the MolCheck verifier
tools `molcheck_verdict`, `molcheck_mandate`, `molcheck_evidence`,
`molcheck_verify` and `molcheck_registry` since moltrust-api #843; the former
`moltproof_*` names still answer as deprecated aliases. With the three Amazon Ads
tools that makes 61 tools at the remote, 48 in this package. The registry
description names the MolCheck verdicts, and the README counts both numbers.

Smithery no longer accepts new servers (its API answers "Updating servers has
been removed" since 2026-10-19); the existing listing can be re-published until
2026-10-31 and is frozen after that. The README now installs against the hosted
endpoint first. The server card at
https://api.moltrust.ch/.well-known/mcp/server-card.json lists all 61 tools.

## 1.2.5

Registry description only; the package code is unchanged.

The hosted remote at `https://api.moltrust.ch/mcp` now also serves three MolTrust
Ads tools — `ads_onboard`, `ads_mandate_template` and `ads_check` — which give an
agent that uses the Amazon Ads MCP Server an allow, hold or forbid verdict on an
intended tool call before it runs. They live in the server repository
(`services/ads_mcp_tools.py`) and are not part of this package, the same way the
`moltproof_*` tools are not. The MCP Registry entry lists that remote, so its
description now says what the remote does.

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

