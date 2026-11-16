"""Wine registry export, merge and writes (slice 11): round trips and fault injection on synthetic files."""

import os

import pytest

from keepsake import registry
from keepsake.registry import RegistryError

USER_REG = """WINE REGISTRY Version 2
;; All keys relative to \\\\User\\\\S-1-5-21-0-0-0-1000

#arch=win64

[Control Panel\\\\Desktop] 1700000000
#time=1d9c6e1f2a3b4c5
"FontSmoothing"="2"

[Software\\\\Example Studio\\\\Example Quest] 1700000001
#time=1d9c6e1f2a3b4c6
"Volume"=dword:00000050
"Slot"="C:\\\\users\\\\Public\\\\save.dat"
"Blob"=hex:01,02,03,04,05,06,07,08,09,0a,0b,0c,0d,0e,0f,10,11,12,13,14,15,16,17,\\
  18,19,1a

[Software\\\\Example Studio\\\\Example Quest\\\\Keys] 1700000002
@="default"

[Software\\\\Example Studio\\\\Other Game] 1700000003
"Level"=dword:00000003

[Software\\\\Wine\\\\Fonts] 1700000004
"Codepages"="1252,437"
"""
MANAGED = ["Software\\Example Studio\\Example Quest"]


def test_parse_keeps_every_section_and_rejects_garbage():
    reg = registry.parse(USER_REG)
    assert [s.key for s in reg.sections] == [
        "control panel\\desktop",
        "software\\example studio\\example quest",
        "software\\example studio\\example quest\\keys",
        "software\\example studio\\other game",
        "software\\wine\\fonts",
    ]
    with pytest.raises(RegistryError):
        registry.parse("not a registry\n")
    with pytest.raises(RegistryError, match="unexpected line"):
        registry.parse(registry.HEADER + "\n\n[A] 1\nbroken line\n")
    with pytest.raises(RegistryError, match="twice"):
        registry.parse(registry.HEADER + "\n\n[A] 1\n\n[a] 2\n")
    with pytest.raises(RegistryError, match="cut off"):
        registry.parse(registry.HEADER + '\n\n[A] 1\n"b"=hex:01,\\\n')
    with pytest.raises(RegistryError, match="ends inside"):
        registry.parse(registry.HEADER + '\n\n[A] 1\n"b"=hex:01,\\')


def test_export_holds_only_managed_keys_without_timestamps():
    fragment = registry.export(USER_REG, MANAGED)
    assert fragment.startswith(registry.HEADER)
    assert "[Software\\\\Example Studio\\\\Example Quest]\n" in fragment
    assert "Keys]" in fragment and "Other Game" not in fragment and "Fonts" not in fragment
    assert "#time=" not in fragment and "1700000001" not in fragment
    assert registry.export(USER_REG, ["Software\\Nobody"]) is None


def test_export_merge_export_round_trip_is_stable():
    fragment = registry.export(USER_REG, MANAGED)
    merged = registry.merge(USER_REG, fragment, MANAGED, now=1800000000)
    registry.verify_merge(USER_REG, merged, fragment, MANAGED)
    assert registry.export(merged, MANAGED) == fragment  # no spurious change after a restore


def test_merge_replaces_managed_keys_and_keeps_everything_else_byte_for_byte():
    other_device = USER_REG.replace('"Volume"=dword:00000050', '"Volume"=dword:00000010').replace('@="default"\n', "")
    fragment = registry.export(other_device, MANAGED)
    merged = registry.merge(USER_REG, fragment, MANAGED, now=1800000000)
    registry.verify_merge(USER_REG, merged, fragment, MANAGED)
    assert '"Volume"=dword:00000010' in merged
    assert '[Control Panel\\\\Desktop] 1700000000\n#time=1d9c6e1f2a3b4c5\n"FontSmoothing"="2"' in merged
    assert '[Software\\\\Example Studio\\\\Other Game] 1700000003\n"Level"=dword:00000003' in merged
    assert merged.count("[Software\\\\Example Studio\\\\Example Quest]") == 1


def test_merging_a_missing_fragment_removes_only_managed_keys():
    merged = registry.merge(USER_REG, None, MANAGED, now=1)
    assert "Example Quest" not in merged and "Other Game" in merged and "Fonts" in merged


def test_a_fragment_with_foreign_keys_is_refused():
    hostile = registry.HEADER + '\n\n[Software\\\\Wine\\\\Fonts]\n"Codepages"="x"\n'
    with pytest.raises(RegistryError, match="does not manage"):
        registry.merge(USER_REG, hostile, MANAGED, now=1)


def test_verify_merge_catches_a_damaged_merge():
    fragment = registry.export(USER_REG, MANAGED)
    merged = registry.merge(USER_REG, fragment, MANAGED, now=1)
    with pytest.raises(RegistryError, match="does not manage"):
        registry.verify_merge(USER_REG, merged.replace('"FontSmoothing"="2"', '"FontSmoothing"="0"'), fragment, MANAGED)
    with pytest.raises(RegistryError, match="do not match"):
        registry.verify_merge(USER_REG, merged.replace("dword:00000050", "dword:00000051"), fragment, MANAGED)


def test_manifest_paths_map_to_hives():
    assert registry.hive_and_key("HKEY_CURRENT_USER/Software/Studio/Game") == ("user.reg", "software\\studio\\game")
    assert registry.hive_and_key("HKEY_LOCAL_MACHINE/Software/Studio") == ("system.reg", "software\\studio")
    assert registry.hive_and_key("HKEY_CLASSES_ROOT/x/y") is None
    assert registry.hive_and_key("HKEY_CURRENT_USER") is None


# Writing the file, with fault injection


@pytest.fixture
def reg_file(tmp_path):
    path = tmp_path / "pfx" / "user.reg"
    path.parent.mkdir()
    path.write_text(USER_REG, encoding="utf-8")
    return path


def changed_fragment():
    return registry.export(USER_REG.replace("dword:00000050", "dword:00000020"), MANAGED)


def test_merge_file_writes_keeps_a_backup_and_reads_back(reg_file, tmp_path):
    result = registry.merge_file(str(reg_file), changed_fragment(), MANAGED, str(tmp_path / "backups"), now=1800000000)
    assert result["status"] == "written"
    assert (tmp_path / "backups" / "1800000000-user.reg").read_text(encoding="utf-8") == USER_REG
    assert "dword:00000020" in reg_file.read_text(encoding="utf-8")
    assert not os.path.exists(str(reg_file) + ".keepsake-tmp")
    again = registry.merge_file(str(reg_file), changed_fragment(), MANAGED, str(tmp_path / "backups"), now=1800000001)
    assert again["status"] == "unchanged"


@pytest.mark.parametrize("fail_at", ["backup", "temp-write", "replace", "read-back"])
def test_a_failure_at_any_step_leaves_the_original_or_the_complete_merge(reg_file, tmp_path, monkeypatch, fail_at):
    fragment = changed_fragment()
    expected = registry.merge(USER_REG, fragment, MANAGED, now=1800000000)
    real_write, real_replace, real_read = registry._write_synced, os.replace, registry._read
    reads = {"n": 0}

    def write(path, text):
        if fail_at == "backup" and "backups" in path:
            raise OSError("disk full")
        if fail_at == "temp-write" and path.endswith(".keepsake-tmp"):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text[: len(text) // 2])  # a torn write of the temporary file
            raise OSError("power lost")
        real_write(path, text)

    def replace(src, dst):
        if fail_at == "replace":
            raise OSError("rename failed")
        real_replace(src, dst)

    def read(path):
        reads["n"] += 1
        if fail_at == "read-back" and reads["n"] == 3:  # the read-back after the rename
            return "garbled"
        return real_read(path)

    monkeypatch.setattr(registry, "_write_synced", write)
    monkeypatch.setattr(registry.os, "replace", replace)
    monkeypatch.setattr(registry, "_read", read)
    with pytest.raises((OSError, RegistryError)):
        registry.merge_file(str(reg_file), fragment, MANAGED, str(tmp_path / "backups"), now=1800000000)
    content = reg_file.read_text(encoding="utf-8")
    assert content in (USER_REG, expected)
    registry.parse(content)  # always a valid registry file
    if fail_at in ("backup", "temp-write", "replace", "read-back"):
        assert content == USER_REG  # every failure before success leaves the original
    assert not os.path.exists(str(reg_file) + ".keepsake-tmp")


def test_a_registry_file_changed_during_the_merge_is_not_overwritten(reg_file, tmp_path):
    original = reg_file.read_text(encoding="utf-8")
    merged = registry.merge(original, changed_fragment(), MANAGED, now=1)
    reg_file.write_text(original + "\n[Software\\\\New] 5\n", encoding="utf-8")  # Wine wrote meanwhile
    with pytest.raises(RegistryError, match="changed while"):
        registry.apply_text(str(reg_file), merged, original, str(tmp_path / "b"))


def test_an_unreadable_registry_file_is_left_alone(reg_file, tmp_path):
    reg_file.write_text("garbage\n", encoding="utf-8")
    with pytest.raises(RegistryError):
        registry.merge_file(str(reg_file), changed_fragment(), MANAGED, str(tmp_path / "b"))
    assert reg_file.read_text(encoding="utf-8") == "garbage\n"


def test_backups_are_pruned_to_the_last_five(reg_file, tmp_path):
    for n in range(8):
        value = f"dword:000000{n:02d}"
        fragment = registry.export(USER_REG.replace("dword:00000050", value), MANAGED)
        registry.merge_file(str(reg_file), fragment, MANAGED, str(tmp_path / "b"), now=1800000000 + n)
    assert len(os.listdir(tmp_path / "b")) == 5


def test_set_values_core_service_sets_a_wine_drive_type(tmp_path):
    system = tmp_path / "system.reg"
    system.write_text(registry.HEADER + '\n\n[Software\\\\Wine\\\\Drives] 1\n"c:"="hd"\n\n[Other] 2\n"x"="y"\n')
    registry.set_values(str(system), "Software\\Wine\\Drives", {"d:": '"cdrom"'}, str(tmp_path / "b"), now=9)
    text = system.read_text()
    assert '"c:"="hd"' in text and '"d:"="cdrom"' in text and '[Other] 2\n"x"="y"' in text
    registry.set_values(str(system), "Software\\Wine\\Drives", {"d:": '"hd"'}, str(tmp_path / "b"), now=10)
    assert system.read_text().count('"d:"=') == 1 and '"d:"="hd"' in system.read_text()
    registry.set_values(str(system), "Software\\New Key", {"v": "dword:00000001"}, str(tmp_path / "b"), now=11)
    assert '[Software\\\\New Key] 11\n"v"=dword:00000001' in system.read_text()
    with pytest.raises(RegistryError):
        registry.set_values(str(system), "Software\\Wine\\Drives", {"d:": "a\nb"}, str(tmp_path / "b"))
