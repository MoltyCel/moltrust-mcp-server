"""The package forwarded whatever it was given straight into the URL.

The MolTrust server log for September carries the result: `did:moltrust:` with
nothing after it, and `admin` — a model copying the placeholder out of this
package's own docstrings, and a model guessing. Both cost a round trip and came
back as a 400 the model then had to interpret.

Caught here, the answer names the mistake while the model still has the context
to fix it.
"""
import ast
import re
from pathlib import Path

import pytest

from moltrust_mcp_server.server import _check_did

SERVER = Path(__file__).resolve().parents[1] / "src" / "moltrust_mcp_server" / "server.py"


@pytest.mark.parametrize("did", [
    "did:moltrust:157224190be24072",
    "did:web:moltrust.ch",
    "did:web:moltrust.ch:agents:42",
    "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
    "did:base:8453:0x3802cE7B2Ff8500D9dBFDE4dF69fE2C0F86238F5",
    "did:pkh:eip155:1:0xb9c5714089478a327f09197987f16f9e5d936e8a",
])
def test_a_well_formed_did_passes(did):
    assert _check_did(did) is None


def test_the_truncated_did_from_the_log():
    """13 of these in 30 days. The message says what is missing rather than
    that something is invalid."""
    msg = _check_did("did:moltrust:")
    assert msg is not None
    assert "no identifier after the method" in msg
    assert "not a placeholder" in msg


def test_the_bare_word_from_the_log():
    msg = _check_did("admin")
    assert msg is not None
    assert "is not a DID" in msg
    assert "did:moltrust:admin" in msg, "the suggestion should be constructive"


def test_an_agent_name_instead_of_a_did():
    """What the Ownify agent sends."""
    msg = _check_did("ownify-e72e7337ea")
    assert msg is not None and "agent name is not a DID" in msg


def test_a_wallet_address_instead_of_a_did():
    msg = _check_did("0x3802cE7B2Ff8500D9dBFDE4dF69fE2C0F86238F5")
    assert msg is not None and "wallet" in msg


@pytest.mark.parametrize("did", ["", "   ", None, "did:", "did", "did:WEB:x",
                                 "did:moltrust:abc:", "did:x:a/b", "<script>"])
def test_malformed_input_is_refused(did):
    assert _check_did(did) is not None


def test_the_field_name_appears_so_a_model_knows_which_argument():
    assert "to_did=" in (_check_did("nope", field="to_did") or "")


def test_every_tool_taking_a_did_validates_it():
    """The guard against the next tool that forgets.

    Fourteen tools take a DID today. A fifteenth that skips the check
    reintroduces exactly the behaviour this release removes, and nothing else
    would catch it — the endpoint answers 400 and the tool reports it as a
    server error.
    """
    source = SERVER.read_text()
    tree = ast.parse(source)
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decorated = any(
            isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "tool"
            for d in node.decorator_list
        )
        if not decorated:
            continue
        args = [a.arg for a in node.args.args + node.args.kwonlyargs]
        if "did" not in args:
            continue
        body = ast.get_source_segment(source, node) or ""
        if "_check_did(did" not in body:
            offenders.append(node.name)
    assert not offenders, (
        "these tools take a did and never check it: " + ", ".join(offenders)
    )


def test_the_docstring_examples_are_themselves_valid():
    """A placeholder in a docstring is what a model sends. `<your-did>` or
    `did:moltrust:...` in an example produces the exact traffic in the log."""
    source = SERVER.read_text()
    examples = re.findall(r'e\.g\.\s*"([^"]+)"', source)
    bad = [e for e in examples if e.startswith("did:") and _check_did(e) is not None]
    assert not bad, f"docstring examples that are not valid DIDs: {bad}"
