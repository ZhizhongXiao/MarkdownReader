"""Phase 12A-2: validating a release must not mutate what is about to be released.

`validate_release.check_onedir` launches the candidate executable that sits in
`dist/MarkdownReader/`, and for an onedir build the user-data root is
`<application_dir>/data` (`core/paths.py`). A validation run therefore creates
`dist/MarkdownReader/data/runtime/...` inside the candidate tree, and
`release_freeze.package_artifacts` then archives that whole tree: a release could ship the
build machine's log and WebView2 profile.

Filtering `data/` out of the archive is not enough, because the candidate tree would still
have been changed by its own validation. The rule is that validation is side-effect
isolated, and packaging refuses a dirty candidate instead of quietly filtering it:

* V1  onedir validation runs against a sandbox copy; the candidate tree gains nothing;
* V2  onefile validation runs with a temporary LOCALAPPDATA / APPDATA, never the real one;
* V3  packaging refuses a candidate that already carries user data.

The positive controls matter as much as the negatives: a pristine candidate must still
package its runtime payload, so the refusal cannot be satisfied by a broken fixture.
"""

import importlib.util
import os
import pathlib
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name: str):
    """Import a packaging script by path: `packaging` is also a PyPI name."""
    source = ROOT / "packaging" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name + "_under_test", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release_freeze = _load("release_freeze")
validate_release = _load("validate_release")


def make_onedir_candidate(root: pathlib.Path, *, dirty: bool) -> pathlib.Path:
    """Build a dist/ with a complete onedir tree, optionally already carrying user data.

    Every `RUNTIME_FILES` entry is created, so the only thing a test observes is the
    behaviour under test: an incomplete fixture would print its own failures and make the
    result harder to attribute.
    """
    dist = root / "dist"
    candidate = dist / "MarkdownReader"
    for parts in validate_release.RUNTIME_FILES:
        target = candidate / "_internal" / pathlib.Path(*parts)
        if pathlib.Path(*parts).suffix:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"payload")
        else:
            target.mkdir(parents=True, exist_ok=True)
    (candidate / "MarkdownReader.exe").write_bytes(b"exe")
    (dist / "MarkdownReader.exe").write_bytes(b"exe")
    if dirty:
        runtime = candidate / "data" / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        (runtime / "MarkdownReader.log").write_text("log\n", encoding="utf-8")
    return dist


def simulate_onedir_run(exe: pathlib.Path) -> None:
    """Mimic a frozen onedir run: runtime data is written beside the executable it runs from."""
    runtime = pathlib.Path(exe).parent / "data" / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "MarkdownReader.log").write_text("log\n", encoding="utf-8")


def tree_snapshot(directory: pathlib.Path) -> set:
    """Return every file under `directory`, relative to it, so drift is visible."""
    return {str(path.relative_to(directory)) for path in directory.rglob("*") if path.is_file()}


def test_onedir_validation_launches_a_copy_not_the_candidate_tree(tmp_path, monkeypatch) -> None:
    """V1: the tree that gets archived must not be the tree that was executed."""
    dist = make_onedir_candidate(tmp_path, dirty=False)
    candidate_exe = dist / "MarkdownReader" / "MarkdownReader.exe"
    monkeypatch.setattr(validate_release, "DIST", dist)
    launched: list = []

    def stub(exe, wait, *, env=None):
        launched.append(pathlib.Path(exe))
        simulate_onedir_run(exe)
        return True

    monkeypatch.setattr(validate_release, "launch_and_survive", stub)

    validate_release.check_onedir(wait=0)

    assert launched, "onedir validation has to launch the candidate it validates"
    assert candidate_exe not in launched, (
        "onedir validation launched the candidate tree itself; it has to run on a sandbox copy "
        "so the tree that gets archived stays pristine"
    )
    assert all(dist not in exe.parents for exe in launched), launched


def test_the_candidate_tree_gains_nothing_during_validation(tmp_path, monkeypatch) -> None:
    """V1: the stronger form -- no file may appear inside the candidate tree."""
    dist = make_onedir_candidate(tmp_path, dirty=False)
    candidate = dist / "MarkdownReader"
    before = tree_snapshot(candidate)
    monkeypatch.setattr(validate_release, "DIST", dist)

    def stub(exe, wait, *, env=None):
        simulate_onedir_run(exe)
        return True

    monkeypatch.setattr(validate_release, "launch_and_survive", stub)

    validate_release.check_onedir(wait=0)

    gained = sorted(tree_snapshot(candidate) - before)
    assert not gained, "validation wrote into the candidate tree: " + ", ".join(gained)
    assert not (candidate / "data").exists()


def test_onefile_validation_receives_a_temporary_user_profile(tmp_path, monkeypatch) -> None:
    """V2: a onefile build keeps its user data in %LOCALAPPDATA%, so validation must redirect it."""
    dist = tmp_path / "dist"
    dist.mkdir()
    exe = dist / "MarkdownReader.exe"
    with exe.open("wb") as stream:
        stream.truncate(21 * 1024 * 1024)
    monkeypatch.setattr(validate_release, "DIST", dist)
    seen: list = []

    def stub(exe, wait, *, env=None):
        seen.append({"exe": pathlib.Path(exe), "env": None if env is None else dict(env)})
        return True

    monkeypatch.setattr(validate_release, "launch_and_survive", stub)

    validate_release.check_onefile(wait=0)

    assert seen, "onefile validation has to launch the candidate it validates"
    environment = seen[0]["env"]
    assert environment is not None, (
        "onefile validation launched the candidate without an environment override: a onefile "
        "build keeps its user data in %LOCALAPPDATA%\\MarkdownReader, so inheriting the developer "
        "environment writes into the machine that builds the release"
    )
    for key in ("LOCALAPPDATA", "APPDATA"):
        assert key in environment, key + " must be redirected for an isolated validation run"
        assert environment[key] != os.environ.get(key), (
            key + " still points at the real developer profile"
        )


def test_portable_packaging_refuses_a_dirty_candidate(tmp_path, monkeypatch) -> None:
    """V3: a dirty candidate is refused; it is not filtered and shipped anyway."""
    dist = make_onedir_candidate(tmp_path, dirty=True)
    monkeypatch.setattr(release_freeze, "DIST", dist)
    refusal = None
    try:
        release_freeze.package_artifacts("1.0.0-rc1")
    except Exception as error:  # recorded here, asserted below: the step must refuse
        refusal = error
    archives = sorted(path.name for path in dist.glob("*.zip"))

    assert refusal is not None, (
        "the package step accepted a candidate that already contains user data and produced "
        + str(archives)
    )
    error_type = getattr(release_freeze, "PackagingError", None)
    assert error_type is not None, (
        "release_freeze must expose PackagingError for a refused package step (Phase 12A-2)"
    )
    assert isinstance(refusal, error_type), "expected PackagingError, got " + type(refusal).__name__
    assert getattr(refusal, "reason", "") == "candidate_contains_user_data"
    assert not archives, "a refused candidate must not leave a portable archive behind"


def test_a_pristine_candidate_keeps_its_runtime_payload(tmp_path, monkeypatch) -> None:
    """V3 positive control: refusing dirty trees must not turn into refusing to package."""
    dist = make_onedir_candidate(tmp_path, dirty=False)
    monkeypatch.setattr(release_freeze, "DIST", dist)

    artifacts = release_freeze.package_artifacts("1.0.0-rc1")

    archives = [pathlib.Path(item) for item in artifacts if pathlib.Path(item).suffix == ".zip"]
    assert archives, "a pristine candidate must still produce the portable archive"
    with zipfile.ZipFile(archives[0]) as bundle:
        names = bundle.namelist()
    assert any(name.endswith("_internal/node/node.exe") for name in names), names
    assert not [name for name in names if name.startswith("MarkdownReader/data/")], names


def test_validator_accepts_an_explicit_candidate_directory(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["validate_release.py", "--mode", "onefile", "--wait", "0", "--dist-dir", str(tmp_path)],
    )
    monkeypatch.setattr(validate_release, "check_onefile", lambda wait: True)

    assert validate_release.main() == 0
    assert tmp_path.resolve() == validate_release.DIST
