import shutil
import subprocess

import pytest
from conftest import ROOT
from migration_kit import swapper

SAMPLE = ROOT / "examples" / "sample-app"
MAPPING = ROOT / "mappings" / "gpt4-series-to-gpt-6-luna.yaml"


@pytest.fixture
def repo(tmp_path):
    dst = tmp_path / "repo"
    shutil.copytree(SAMPLE, dst)
    return dst


def _snapshot(p):
    return {f: f.read_bytes() for f in p.rglob("*") if f.is_file()}


def test_swap_writes_diff_and_never_touches_repo(repo, tmp_path):
    before = _snapshot(repo)
    res = swapper.plan(repo, swapper.load_mapping(MAPPING))
    patch, summary = swapper.write(res, tmp_path / "out")
    assert _snapshot(repo) == before
    diff = patch.read_text()
    assert '+        model="gpt-6-luna",' in diff
    assert "ft:gpt-4o-mini" not in "".join(l for l in diff.splitlines(True) if l.startswith(("+", "-")) and not l.startswith(("+++", "---")))
    assert "gpt-4o-transcribe" not in [c.old for c in res.changes]
    assert "gpt-4.1-nano" not in [c.old for c in res.changes]
    assert len(res.skipped_fine_tunes) == 2
    assert "claude-sonnet-4-5-20250929" not in [c.old for c in res.changes]   # not in this mapping file
    assert "README.md" not in res.new_contents           # docs off by default


def test_patch_applies_with_git(repo, tmp_path):
    res = swapper.plan(repo, swapper.load_mapping(MAPPING))
    patch, _ = swapper.write(res, tmp_path / "out")
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "apply", str(patch)], cwd=repo, check=True)
    assert 'model="gpt-6-luna"' in (repo / "app" / "summarise.py").read_text()
    assert "ft:gpt-4o-mini-2024-07-18" in (repo / "config" / "models.yaml").read_text()


def test_apply_in_place_and_explicit_fine_tune(repo, tmp_path):
    m = tmp_path / "m.yaml"
    m.write_text('mappings: {gpt-4o: gpt-6-luna}\n'
                 'fine_tuned: {"ft:gpt-4o-mini-2024-07-18:acme-widgets:intent-v3:9xYzAbC1": gpt-6-luna}\n')
    res = swapper.plan(repo, swapper.load_mapping(m))
    assert not res.skipped_fine_tunes
    swapper.apply_in_place(repo, res)
    y = (repo / "config" / "models.yaml").read_text()
    assert "default: gpt-6-luna" in y and "intent_classifier: gpt-6-luna" in y
    assert "fallback: gpt-4o-mini-2024-07-18" in y      # not in this mapping


def test_no_trailing_newline(tmp_path):
    (tmp_path / "x.py").write_text('m = "gpt-4o"')
    m = tmp_path / "m.yaml"
    m.write_text("mappings: {gpt-4o: gpt-6-luna}\n")
    res = swapper.plan(tmp_path, swapper.load_mapping(m))
    assert "\\ No newline at end of file" in res.diff


def test_ft_in_mappings_section_rejected(tmp_path):
    m = tmp_path / "m.yaml"
    m.write_text('mappings: {"ft:gpt-4o:x::y": gpt-6-luna}\n')
    with pytest.raises(ValueError):
        swapper.load_mapping(m)


def test_default_mapping_from_packs(repo, tmp_path):
    from migration_kit.packs import load_packs
    m = swapper.mapping_from_packs(load_packs())
    assert m.replacements["gpt-4o-2024-08-06"] == "gpt-6-luna"
    assert m.replacements["claude-sonnet-4-5-20250929"] == "claude-sonnet-5-5"
    assert m.replacements["gpt-4.1-nano"] == "gpt-5.6-luna"
    assert "gpt-4o-transcribe" not in m.replacements and "o1-pro" not in m.replacements
    res = swapper.plan(repo, m)
    assert "claude-sonnet-4-5-20250929" in [c.old for c in res.changes]
    assert ("config/models.yaml", "gpt-4.1-nano", "gpt-5.6-luna") in {(c.file, c.old, c.new) for c in res.changes}
