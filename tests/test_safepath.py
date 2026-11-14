import os

import pytest

from keepsake.safepath import PathEscapeError, ensure_within, is_within, join_within, validate_relative


def test_inside_and_outside(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    assert is_within(str(root), str(root / "a" / "b"))
    assert is_within(str(root), str(root))
    assert not is_within(str(root), str(tmp_path / "other"))
    assert not is_within(str(root), str(root / ".." / "other"))


def test_prefix_sibling_is_not_inside(tmp_path):
    root = tmp_path / "save"
    sibling = tmp_path / "saved"
    root.mkdir()
    sibling.mkdir()
    assert not is_within(str(root), str(sibling / "x"))


@pytest.mark.parametrize(
    "rel",
    ["", "/etc/passwd", "../x", "a/../../b", "a/./b", "a//b", "C:/x", "a\\b", "a\x00b", "a/"],
)
def test_validate_relative_rejects(rel):
    with pytest.raises(PathEscapeError):
        validate_relative(rel)


def test_validate_relative_accepts():
    assert validate_relative("Goat2/Saved/slot0.sav") == "Goat2/Saved/slot0.sav"


def test_join_within_rejects_traversal(tmp_path):
    with pytest.raises(PathEscapeError):
        join_within(str(tmp_path), "../escape")


@pytest.mark.posix
@pytest.mark.skipif(not hasattr(os, "symlink") or os.name == "nt", reason="symlinks need POSIX")
def test_symlink_escape_rejected(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    os.symlink(outside, root / "link")
    with pytest.raises(PathEscapeError):
        ensure_within(str(root), str(root / "link" / "file"))
