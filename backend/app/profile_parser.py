"""The master profile markdown -> Profile.

The file is markdown headings wrapping YAML bodies, so the parser is a heading
split plus yaml.safe_load. No hand-rolled tokenizer.

  # Section        -> top-level section
  ## Company       -> an Experience entry
  ### Project      -> a Project inside that company
"""

import re
from pathlib import Path

import yaml

from .models import Profile

# ponytail: headings must start at column 0. A "# " line inside a YAML body
# would be read as a section heading. Indent YAML comments, which is normal anyway.
_H1 = re.compile(r"^# (.+)$", re.M)
_H2 = re.compile(r"^## (.+)$", re.M)
_H3 = re.compile(r"^### (.+)$", re.M)


def parse(path: Path) -> Profile:
    """Convenience for tests and fixtures. The app parses a database row."""
    return parse_text(path.read_text(encoding="utf-8"))


def parse_text(text: str) -> Profile:
    sections = {name.strip().lower(): body for name, body in _split(text, _H1)}
    return Profile.model_validate(
        {
            "identity": _yaml(sections.get("identity", "")),
            "titles": _yaml(sections.get("titles", "")),
            "summaries": _yaml(sections.get("summaries", "")),
            "skills": _yaml(sections.get("skills", "")),
            "experience": [
                _company(name, body)
                for name, body in _split(sections.get("experience", ""), _H2)
            ],
        }
    )


def _company(name: str, body: str) -> dict:
    parts = _H3.split(body)
    return {
        **_yaml(parts[0]),
        "name": name.strip(),
        "projects": [
            _project(parts[i], parts[i + 1]) for i in range(1, len(parts), 2)
        ],
    }


def _project(name: str, body: str) -> dict:
    name = name.strip()
    # An explicit `id:` in the body wins over the slugged heading.
    return {"id": _slug(name), "name": name, **_yaml(body)}


def _split(text: str, heading: re.Pattern) -> list[tuple[str, str]]:
    """[(heading, body), ...]. re.split with one group yields [pre, h, b, h, b...]."""
    parts = heading.split(text)
    return [(parts[i], parts[i + 1]) for i in range(1, len(parts), 2)]


def _yaml(text: str):
    return yaml.safe_load(text) or {}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
