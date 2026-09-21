"""The tag, the package and the registry record must name one version.

`publish.yml` already compares the three, but it does so in the `mcp-registry`
job — which runs after PyPI has the wheel. A mismatch caught there leaves the
package published and the registry a version behind, which is the exact split
the registry job was added to close.

At 1.2.3 the repo had that mismatch: `pyproject.toml` said 1.2.3 and
`server.json` still said 1.2.2. Here it is a red test on the pull request
instead, and `publish.yml` runs the same suite before it builds anything, so a
tag with a stale `server.json` stops before it reaches PyPI.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _pyproject_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "pyproject.toml has no top-level version"
    return match.group(1)


def _server_json_version() -> str:
    return json.loads((ROOT / "server.json").read_text(encoding="utf-8"))["version"]


def test_the_package_and_the_registry_record_agree():
    assert _server_json_version() == _pyproject_version()


def test_the_version_is_a_release_number():
    """`mcp-publisher` and PyPI both reject what they cannot order."""
    assert re.fullmatch(r"\d+\.\d+\.\d+", _pyproject_version())


def test_the_changelog_has_an_entry_for_this_version():
    """A version that ships without a line saying what changed is one nobody
    can tell apart from the one before it."""
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"\n## {_pyproject_version()}\n" in changelog
