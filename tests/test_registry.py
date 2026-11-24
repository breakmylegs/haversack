"""Wine registry export, merge and writes (slice 11): round trips and fault injection on synthetic files."""

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


def test_merging_a_missing_fragment_removes_only_managed_keys():
    merged = registry.merge(USER_REG, None, MANAGED, now=1)
    assert "Example Quest" not in merged and "Other Game" in merged and "Fonts" in merged


def test_a_fragment_with_foreign_keys_is_refused():
    hostile = registry.HEADER + '\n\n[Software\\\\Wine\\\\Fonts]\n"Codepages"="x"\n'
    with pytest.raises(RegistryError, match="does not manage"):
        registry.merge(USER_REG, hostile, MANAGED, now=1)


# Writing the file, with fault injection


@pytest.fixture
def reg_file(tmp_path):
    path = tmp_path / "pfx" / "user.reg"
    path.parent.mkdir()
    path.write_text(USER_REG, encoding="utf-8")
    return path


def changed_fragment():
    return registry.export(USER_REG.replace("dword:00000050", "dword:00000020"), MANAGED)


def test_a_registry_file_changed_during_the_merge_is_not_overwritten(reg_file, tmp_path):
    original = reg_file.read_text(encoding="utf-8")
    merged = registry.merge(original, changed_fragment(), MANAGED, now=1)
    reg_file.write_text(original + "\n[Software\\\\New] 5\n", encoding="utf-8")  # Wine wrote meanwhile
    with pytest.raises(RegistryError, match="changed while"):
        registry.apply_text(str(reg_file), merged, original, str(tmp_path / "b"))


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
