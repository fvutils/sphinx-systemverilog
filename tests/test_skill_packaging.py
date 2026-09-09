"""The bundled agent skill: entry point, frontmatter, links and packaging.

The skill is only useful if it actually reaches an installed environment, and
every way it can fail to is silent: a package-data glob that matches nothing, a
frontmatter field IVPM rejects, a reference file renamed out from under the map
in SKILL.md.  So each of those is asserted here rather than discovered as a
warning during somebody's ``ivpm update``.
"""

from __future__ import annotations

import importlib.metadata
import os
import re

import pytest

from sphinx_systemverilog import skills

pytestmark = pytest.mark.unit

ENTRY_POINT_GROUP = "agent.skills"
ENTRY_POINT_NAME = "sphinx-systemverilog"

#: Same shape IVPM's agents handler parses: a leading '---' fenced block.
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_FIELD_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)$", re.MULTILINE)


def _skill_dir() -> str:
    dirs = skills.get_skill_dirs()
    assert dirs, "get_skill_dirs() returned nothing"
    return dirs[0]


def _frontmatter(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        content = fh.read()
    match = _FRONTMATTER_RE.match(content)
    assert match, f"{path} has no frontmatter block"
    return {m.group(1): m.group(2).strip() for m in _FIELD_RE.finditer(match.group(1))}


def _pyproject() -> dict:
    # tomllib is 3.11+; the support floor is 3.10, where tomli (a test-extra
    # dependency) provides the same API.  Imported here rather than at module
    # scope so the rest of the file still collects if neither is present.
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover - depends on interpreter
        import tomli as tomllib

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "pyproject.toml")
    if not os.path.isfile(path):
        pytest.skip("pyproject.toml is not available (installed, not a checkout)")
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def test_entrypoint_declared():
    """pyproject declares the entry point IVPM's agents handler reads.

    Asserted against the declaration rather than against installed metadata,
    because entry points are frozen at install time: a correct declaration in a
    checkout whose venv predates it would otherwise read as a failure.
    """
    data = _pyproject()
    group = data["project"]["entry-points"][ENTRY_POINT_GROUP]
    assert group[ENTRY_POINT_NAME] == "sphinx_systemverilog.skills:get_skill_dirs"


def test_package_data_covers_the_skill():
    """The package-data patterns reach every file the skill ships.

    setuptools globs do not recurse, so a file one level deeper than any
    declared pattern is dropped from the wheel in silence.  Matching the
    patterns against the real tree is what makes that loud.
    """
    import fnmatch

    data = _pyproject()
    patterns = data["tool"]["setuptools"]["package-data"]["sphinx_systemverilog"]

    pkg_root = os.path.dirname(os.path.abspath(skills.__file__))
    for path in _skill_files():
        rel = os.path.relpath(path, pkg_root).replace(os.sep, "/")
        assert any(fnmatch.fnmatchcase(rel, p) for p in patterns), (
            f"{rel} matches no package-data pattern; it would not ship"
        )


def test_entrypoint_resolves_when_installed():
    """When the installed metadata carries the entry point, it must load."""
    eps = [
        ep for ep in importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)
        if ep.name == ENTRY_POINT_NAME
    ]
    if not eps:
        pytest.skip(
            "the installed distribution predates the entry point; "
            "reinstall to exercise this"
        )
    assert eps[0].load() is skills.get_skill_dirs


def test_skill_dir_exists():
    skill_dir = _skill_dir()
    assert os.path.isdir(skill_dir), f"{skill_dir} is not a directory"
    assert os.path.isfile(os.path.join(skill_dir, "SKILL.md"))


def test_frontmatter_valid():
    """IVPM drops a skill whose frontmatter lacks 'name' or 'description'."""
    fields = _frontmatter(os.path.join(_skill_dir(), "SKILL.md"))
    assert fields.get("name"), "frontmatter has no 'name'"
    assert fields.get("description"), "frontmatter has no 'description'"
    # The entry-point name becomes the installed directory name; a frontmatter
    # name that disagrees means the host and the skill call it different things.
    assert fields["name"] == ENTRY_POINT_NAME
    assert fields["name"] == skills.SKILL_NAME
    assert os.path.basename(_skill_dir()) == skills.SKILL_NAME


def test_reference_files_resolve():
    """Every references/*.md named in SKILL.md exists, and vice versa."""
    skill_dir = _skill_dir()
    with open(os.path.join(skill_dir, "SKILL.md"), encoding="utf-8") as fh:
        text = fh.read()

    linked = set(re.findall(r"references/([A-Za-z0-9_.-]+\.md)", text))
    assert linked, "SKILL.md links no reference files"

    ref_dir = os.path.join(skill_dir, "references")
    for name in sorted(linked):
        assert os.path.isfile(os.path.join(ref_dir, name)), f"missing {name}"

    on_disk = {f for f in os.listdir(ref_dir) if f.endswith(".md")}
    assert on_disk == linked, (
        "SKILL.md's reference map and references/ disagree: "
        f"only on disk {sorted(on_disk - linked)}, only linked {sorted(linked - on_disk)}"
    )


def test_documented_config_values_exist():
    """Every sv_* value named in the skill is one the extension registers.

    Catches the drift that misleads -- a renamed or removed config value the
    skill still describes.  It deliberately does not assert the converse: a new
    value the skill has not caught up with leaves the skill incomplete, which is
    a lesser problem than confidently wrong.
    """
    import sphinx_systemverilog.config as config_mod

    source = open(config_mod.__file__, encoding="utf-8").read()
    registered = set(re.findall(r'add_config_value\(\s*"(sv_[a-z_]+)"', source))
    assert registered, "no config values found in config.py"

    for path in _skill_files():
        text = open(path, encoding="utf-8").read()
        for name in set(re.findall(r"\bsv_[a-z_]+\b", text)):
            assert name in registered, f"{os.path.basename(path)} names unknown {name}"


def test_documented_directives_exist():
    """Every autosv*/sv: directive named in the skill is really registered."""
    from sphinx_systemverilog.autodoc.directives import AUTODOC_DIRECTIVES
    from sphinx_systemverilog.autodoc.structure import STRUCTURE_DIRECTIVES
    from sphinx_systemverilog.autodoc.uvm import UVM_DIRECTIVES
    from sphinx_systemverilog.domain import OBJECT_TYPES

    known = set(AUTODOC_DIRECTIVES)
    known |= {"sv:" + n for n in STRUCTURE_DIRECTIVES}
    known |= {"sv:" + n for n in UVM_DIRECTIVES}
    known |= {"sv:" + n for n in OBJECT_TYPES}
    known |= {"sv:inheritance-diagram", "sv:instance-diagram"}

    for path in _skill_files():
        text = open(path, encoding="utf-8").read()
        used = set(re.findall(r"\b(autosv[a-z]+)\b", text))
        used |= set(re.findall(r"\b(sv:[a-z][a-z-]*)\b", text))
        # ``sv:`` also prefixes the cross-reference roles, which are not
        # directives; they are checked separately below.
        used -= _role_names(OBJECT_TYPES)
        for name in sorted(used):
            assert name in known, f"{os.path.basename(path)} names unknown {name}"


def test_documented_roles_exist():
    """Every :sv:<role>: named in the skill is really a domain role."""
    from sphinx_systemverilog.domain import OBJECT_TYPES

    roles = _role_names(OBJECT_TYPES)
    for path in _skill_files():
        text = open(path, encoding="utf-8").read()
        for used in set(re.findall(r":(sv:[a-z]+):", text)):
            assert used in roles, f"{os.path.basename(path)} names unknown role :{used}:"


def _role_names(object_types) -> set:
    names = set()
    for _label, role_names in object_types.values():
        names.update("sv:" + r for r in role_names)
    return names


def _skill_files():
    skill_dir = _skill_dir()
    paths = [os.path.join(skill_dir, "SKILL.md")]
    ref_dir = os.path.join(skill_dir, "references")
    paths += [
        os.path.join(ref_dir, f) for f in sorted(os.listdir(ref_dir))
        if f.endswith(".md")
    ]
    return paths


@pytest.mark.packaging
def test_skill_is_in_the_wheel(tmp_path):
    """Build a real wheel and assert the skill files are inside it.

    The only test here that proves the distribution is right; the others pass
    against the source tree whether or not the packaging is.

    Built through ``pip wheel`` in a scratch directory rather than in-process:
    the repository root holds a ``build/`` directory, which shadows the
    ``build`` module for anything running with the root on sys.path.
    """
    import subprocess
    import sys
    import zipfile

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps",
         "--no-build-isolation", "--wheel-dir", str(tmp_path), root],
        cwd=str(tmp_path), capture_output=True, text=True,
    )
    if result.returncode != 0:
        # An IVPM-managed venv has no pip, so fall back to driving the declared
        # build backend directly.  Same artifact, one less tool required.
        result = subprocess.run(
            [sys.executable, "-c",
             "import setuptools.build_meta as b, sys; "
             "print(b.build_wheel(sys.argv[1]))", str(tmp_path)],
            cwd=root, capture_output=True, text=True,
        )
        if result.returncode != 0:
            pytest.skip(f"wheel build unavailable:\n{result.stdout}\n{result.stderr}")

    wheels = [p for p in os.listdir(tmp_path) if p.endswith(".whl")]
    assert wheels, "the wheel build produced no wheel"

    with zipfile.ZipFile(os.path.join(tmp_path, wheels[0])) as zf:
        names = set(zf.namelist())

    prefix = f"sphinx_systemverilog/share/skills/{skills.SKILL_NAME}/"
    assert prefix + "SKILL.md" in names
    assert any(
        n.startswith(prefix + "references/") and n.endswith(".md") for n in names
    ), "no reference files in the wheel"
