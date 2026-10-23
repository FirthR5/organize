from __future__ import annotations

import os
import textwrap
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

import yaml
from pydantic import ConfigDict, ValidationError
from pydantic.dataclasses import dataclass

from .errors import ConfigError, ConfigNotFound, IncludeError
from .find_config import find_config_by_name
from .output import Default, Output
from .rule import Rule
from .template import render
from .utils import ReportSummary, expandvars, normalize_unicode

Tags = Iterable[str]

_YAML_SUFFIXES = ("", ".yaml", ".yml")


def default_yaml_cnst(loader, tag_suffix, node):
    # disable yaml constructors for strings starting with exclamation marks
    # https://stackoverflow.com/a/13281292/300783
    return str(node.tag)


yaml.add_multi_constructor("", default_yaml_cnst, Loader=yaml.SafeLoader)


def resolve_include(name: str, relative_to: Optional[Path] = None) -> Path:
    """
    Resolve an `include` reference to an existing config file.

    Resolution order:
      1. The path as given (with `~` and environment variables expanded).
      2. Relative to the directory of the including config file.
      3. The default config search locations (see `find_config_by_name`).
    """
    as_path = expandvars(name)
    candidate = as_path if as_path.is_absolute() else None

    if candidate is not None and candidate.is_file():
        return candidate

    if relative_to is not None:
        base_dir = relative_to.resolve().parent
        for suffix in _YAML_SUFFIXES:
            candidate = (base_dir / f"{name}{suffix}").resolve()
            if candidate.is_file():
                return candidate

    try:
        return find_config_by_name(name=name)
    except ConfigNotFound as e:
        suffix = f' (included from "{relative_to}")' if relative_to else ""
        raise IncludeError(f'Cannot resolve included config "{name}".{suffix}') from e


def _strip_include_line(text: str) -> str:
    """
    Remove a top-level `include:` entry (scalar or list form) and any leading YAML
    document-start marker from a YAML document, preserving everything else verbatim.
    """
    lines = text.splitlines(keepends=True)
    out: List[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.strip() == "---":
            i += 1
            continue
        if line[:1].isspace() or not line.strip().startswith("include:"):
            out.append(line)
            i += 1
            continue

        rest = line.split(":", 1)[1].strip()
        i += 1
        if rest:
            continue
        # list form: skip following `- item` lines and blank/comment lines
        while i < n:
            stripped = lines[i].strip()
            if stripped.startswith("- "):
                i += 1
            elif not stripped or stripped.startswith("#"):
                i += 1
            else:
                break
    return "".join(out)


def _extract_includes(text: str) -> List[str]:
    """
    Textually extract top-level `include:` values (scalar or list form) without
    parsing the whole document, so files using YAML aliases from their includes
    can still be processed.
    """
    lines = text.splitlines()
    includes: List[str] = []
    n = len(lines)
    i = 0
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if not line[:1].isspace() and stripped.startswith("include:"):
            rest = stripped.split(":", 1)[1].strip()
            if rest:
                includes.append(rest)
                i += 1
                continue
            # list form
            i += 1
            while i < n:
                nxt = lines[i]
                s = nxt.strip()
                if s.startswith("- "):
                    includes.append(s[2:].strip())
                    i += 1
                    continue
                if not s or s.startswith("#"):
                    i += 1
                    continue
                break
            continue
        i += 1
    return includes


def _inline(path: Path, seen: List[Path]) -> str:
    """
    Return the text of `path` with all `include` files inlined as a single
    YAML document, so YAML anchors defined in included files are visible to the
    including document.
    """
    resolved = path.resolve()
    if resolved in seen:
        chain = " -> ".join(str(p) for p in (*seen, resolved))
        raise IncludeError(f"Cyclic config include detected: {chain}")

    text = normalize_unicode(path.read_text(encoding="utf-8"))
    includes = _extract_includes(text)
    if not includes:
        return text

    parts: List[str] = []
    for name in includes:
        include_path = resolve_include(name, relative_to=resolved)
        parts.append(_inline(include_path, seen=[*seen, resolved]))

    child = _strip_include_line(text)
    return "\n".join(parts) + "\n" + child


def _load_yaml_dict(
    config: str,
    config_path: Optional[Path],
    seen: Sequence[Path],
) -> Dict[str, Any]:
    """
    Parse a YAML config, resolving `include` directives into a single document so
    that YAML anchors from included files can be referenced by the including file.
    """
    if config_path is not None:
        text = _inline(config_path.resolve(), seen=list(seen))
    else:
        text = config

    normalized = normalize_unicode(text)
    dedented = textwrap.dedent(normalized)
    as_dict = yaml.load(dedented, Loader=yaml.SafeLoader)
    if not as_dict:
        where = f" in {config_path}" if config_path else ""
        raise ValueError(f"Config is empty{where}")
    return as_dict


def should_execute(rule_tags: Tags, tags: Tags, skip_tags: Tags) -> bool:
    """
    returns whether the rule with `rule_tags` should be executed,
    given `tags` and `skip_tags`
    """
    if not rule_tags:
        rule_tags = set()
    if not tags:
        tags = set()
    if not skip_tags:
        skip_tags = set()

    if "always" in rule_tags and "always" not in skip_tags:
        return True
    if "never" in rule_tags and "never" not in tags:
        return False
    if not tags and not skip_tags:
        return True
    if not rule_tags and tags:
        return False
    should_run = any(tag in tags for tag in rule_tags) or not tags or not rule_tags
    should_skip = any(tag in skip_tags for tag in rule_tags)
    return should_run and not should_skip


@dataclass(config=ConfigDict(extra="ignore"))
class Config:
    rules: List[Rule]

    _config_path: Optional[Path] = None

    @classmethod
    def from_string(cls, config: str, config_path: Optional[Path] = None) -> Config:
        try:
            as_dict = _load_yaml_dict(config, config_path=config_path, seen=())
            inst = cls(**as_dict)
            inst._config_path = config_path
            return inst
        except ValidationError as e:
            # add a config_path property to the ValidationError
            raise ConfigError(e=e, config_path=config_path) from e

    @classmethod
    def from_path(cls, config_path: Path) -> Config:
        text = config_path.read_text(encoding="utf-8")
        inst = cls.from_string(text, config_path=config_path)
        return inst

    def execute(
        self,
        simulate: bool = True,
        output: Output = Default(),
        tags: Tags = set(),
        skip_tags: Tags = set(),
        working_dir: Union[str, Path] = ".",
    ) -> None:
        working_path = Path(render(str(working_dir)))
        os.chdir(working_path)
        output.start(
            simulate=simulate,
            config_path=self._config_path,
            working_dir=working_path,
        )
        summary = ReportSummary()
        try:
            for rule_nr, rule in enumerate(self.rules):
                if should_execute(
                    rule_tags=rule.tags,
                    tags=tags,
                    skip_tags=skip_tags,
                ):
                    rule_summary = rule.execute(
                        simulate=simulate,
                        output=output,
                        rule_nr=rule_nr,
                    )
                    summary += rule_summary
        finally:
            output.end(summary.success, summary.errors)
