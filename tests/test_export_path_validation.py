"""
Tests for whoopyy.export._validate_export_path.

The guard only inspects (never writes to) paths, so system locations are checked
by name. Everything user-side lives under tmp_path with HOME pointed at it.
"""

import os
import sys
from pathlib import Path

import pytest

from whoopyy.export import _validate_export_path

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX path rules")


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    """A fake home directory, so the real one is never consulted."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture
def cwd(tmp_path, monkeypatch) -> Path:
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    return work


class TestSystemLocations:
    @pytest.mark.parametrize(
        "path",
        [
            "/etc/x.csv",
            "/etc/ssh/sshd_config",
            "/private/etc/x.csv",
            "/private/var/db/x.csv",
            "/private/var/log/x.csv",
            "/var/log/x.csv",
            "/System/x.csv",
            "/System/Volumes/Data/private/etc/x.csv",
            "/Library/x.csv",
            "/Library/LaunchDaemons/x.csv",
            "/bin/x.csv",
            "/sbin/x.csv",
            "/usr/x.csv",
            "/usr/bin/x.csv",
            "/usr/lib/x.csv",
            "/usr/share/x.csv",
            "/boot/x.csv",
            "/proc/x.csv",
            "/sys/x.csv",
            "/dev/x.csv",
            "/lib/x.csv",
            "/lib64/x.csv",
        ],
    )
    def test_blocked(self, path, home):
        with pytest.raises(ValueError, match="protected"):
            _validate_export_path(path)

    @pytest.mark.parametrize(
        "path",
        ["/ETC/x.csv", "/LIBRARY/x.csv", "/Private/Etc/x.csv", "/SYSTEM/x.csv", "/Usr/Bin/x.csv"],
    )
    def test_blocked_regardless_of_case(self, path, home):
        # macOS volumes are case-insensitive, so these name the same directories.
        with pytest.raises(ValueError, match="protected"):
            _validate_export_path(path)

    def test_blocked_via_dotdot(self, home):
        with pytest.raises(ValueError, match="protected"):
            _validate_export_path("/tmp/../etc/x.csv")

    def test_blocked_via_relative_path_from_protected_cwd(self, home, monkeypatch):
        monkeypatch.chdir("/")
        with pytest.raises(ValueError, match="protected"):
            _validate_export_path("etc/x.csv")

    def test_blocked_via_symlinked_directory(self, tmp_path, home):
        link = tmp_path / "sysetc"
        link.symlink_to("/etc")
        with pytest.raises(ValueError, match="protected"):
            _validate_export_path(link / "x.csv")

    def test_blocked_via_symlinked_file(self, tmp_path, home):
        link = tmp_path / "out.csv"
        link.symlink_to("/etc/not-yet-there.csv")  # dangling
        with pytest.raises(ValueError, match="protected"):
            _validate_export_path(link)

    def test_error_names_resolved_location(self, home):
        with pytest.raises(ValueError, match=r"/etc"):
            _validate_export_path("/etc/x.csv")

    @pytest.mark.parametrize(
        "path",
        [
            "/usr/local/x.csv",
            "/usr/local/share/whoopyy/x.csv",
            "/tmp/x.csv",
            "/tmp/whoopyy/x.csv",
            "/private/tmp/x.csv",
            # Only whole path components count, not string prefixes.
            "/bootcamp/x.csv",
            "/syslog-exports/x.csv",
        ],
    )
    def test_allowed(self, path, home):
        _validate_export_path(path)

    def test_usr_local_prefix_lookalike_still_blocked(self, home):
        with pytest.raises(ValueError, match="protected"):
            _validate_export_path("/usr/localfoo/x.csv")

    def test_tmp_path_allowed(self, tmp_path, home):
        # pytest's tmp_path is under /private/var/folders on macOS.
        _validate_export_path(tmp_path / "out.csv")


class TestSensitiveHomeLocations:
    SENSITIVE = [
        ".ssh/authorized_keys",
        ".ssh/id_ed25519",
        ".ssh",
        ".gnupg/pubring.kbx",
        ".aws/credentials",
        ".config/gcloud/credentials.db",
        ".config/fish/config.fish",
        ".bashrc",
        ".bash_profile",
        ".profile",
        ".zshrc",
        ".zshenv",
        ".zprofile",
    ]

    @pytest.mark.parametrize("rel", SENSITIVE)
    def test_blocked_via_tilde(self, rel, home):
        with pytest.raises(ValueError, match="protected"):
            _validate_export_path(f"~/{rel}")

    @pytest.mark.parametrize("rel", SENSITIVE)
    def test_blocked_via_absolute_path(self, rel, home):
        with pytest.raises(ValueError, match="protected"):
            _validate_export_path(home / rel)

    def test_blocked_via_dotdot(self, home):
        with pytest.raises(ValueError, match="protected"):
            _validate_export_path(home / "exports" / ".." / ".ssh" / "authorized_keys")

    def test_blocked_when_home_is_a_symlink(self, tmp_path, monkeypatch):
        real = tmp_path / "real-home"
        real.mkdir()
        alias = tmp_path / "alias-home"
        alias.symlink_to(real)
        monkeypatch.setenv("HOME", str(alias))
        for path in ("~/.ssh/authorized_keys", alias / ".aws" / "credentials",
                     real / ".gnupg" / "x"):
            with pytest.raises(ValueError, match="protected"):
                _validate_export_path(path)

    def test_blocked_through_symlink_into_sensitive_dir(self, tmp_path, home):
        (home / ".ssh").mkdir()
        (home / "notes").symlink_to(home / ".ssh")
        with pytest.raises(ValueError, match="protected"):
            _validate_export_path(home / "notes" / "authorized_keys")

    def test_blocked_when_sensitive_dir_is_itself_a_symlink(self, tmp_path, home):
        vault = tmp_path / "vault"
        vault.mkdir()
        (home / ".ssh").symlink_to(vault)
        for path in ("~/.ssh/authorized_keys", vault / "authorized_keys"):
            with pytest.raises(ValueError, match="protected"):
                _validate_export_path(path)

    def test_blocked_when_rc_file_is_a_dotfile_manager_symlink(self, tmp_path, home):
        dotfiles = tmp_path / "dotfiles"
        dotfiles.mkdir()
        (dotfiles / "zshrc").write_text("# rc\n")
        (home / ".zshrc").symlink_to(dotfiles / "zshrc")
        for path in ("~/.zshrc", dotfiles / "zshrc"):
            with pytest.raises(ValueError, match="protected"):
                _validate_export_path(path)

    @pytest.mark.parametrize(
        "rel",
        [
            "x.csv",
            "exports/x.csv",
            "Documents/whoop/x.csv",
            "Library/Application Support/whoopyy/x.csv",
            ".config/x.csv",
            ".config/whoopyy/x.csv",
            # Look-alikes: only whole path components count.
            ".ssh-notes/x.csv",
            ".config/gcloud-notes/x.csv",
            ".bashrc-backup/x.csv",
        ],
    )
    def test_ordinary_home_destinations_allowed(self, rel, home):
        _validate_export_path(f"~/{rel}")
        _validate_export_path(home / rel)

    def test_ssh_named_dir_outside_home_is_not_protected(self, tmp_path, home):
        # The sensitive list is anchored at the current home; a .ssh elsewhere is just a directory.
        _validate_export_path(tmp_path / "project" / ".ssh" / "x.csv")

    def test_unknown_user_tilde_is_a_value_error(self, home):
        with pytest.raises(ValueError, match="Cannot resolve export path"):
            _validate_export_path("~no-such-user-whoopyy-test/x.csv")

    def test_missing_home_skips_home_rules(self, tmp_path, monkeypatch):
        def no_home(cls):
            raise RuntimeError("Could not determine home directory")

        monkeypatch.setattr(Path, "home", classmethod(no_home))
        _validate_export_path(tmp_path / "x.csv")
        with pytest.raises(ValueError, match="protected"):
            _validate_export_path("/etc/x.csv")


class TestDestinationFileType:
    def test_new_file_allowed(self, cwd, home):
        _validate_export_path("out.csv")
        _validate_export_path(cwd / "new-subdir" / "out.csv")

    def test_existing_regular_file_allowed(self, cwd, home):
        (cwd / "out.csv").write_text("old\n")
        _validate_export_path("out.csv")

    def test_symlink_to_regular_file_allowed(self, cwd, home):
        (cwd / "real.csv").write_text("old\n")
        (cwd / "link.csv").symlink_to(cwd / "real.csv")
        _validate_export_path(cwd / "link.csv")

    def test_directory_refused(self, cwd, home):
        (cwd / "out.csv").mkdir()
        with pytest.raises(ValueError, match="non-regular"):
            _validate_export_path("out.csv")

    def test_symlink_to_directory_refused(self, cwd, home):
        (cwd / "target").mkdir()
        (cwd / "out.csv").symlink_to(cwd / "target")
        with pytest.raises(ValueError, match="non-regular"):
            _validate_export_path("out.csv")

    @pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs os.mkfifo")
    def test_fifo_refused(self, cwd, home):
        os.mkfifo(cwd / "out.csv")
        with pytest.raises(ValueError, match="non-regular"):
            _validate_export_path("out.csv")

    @pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs os.mkfifo")
    def test_symlink_to_fifo_refused(self, cwd, home):
        os.mkfifo(cwd / "pipe")
        (cwd / "out.csv").symlink_to(cwd / "pipe")
        with pytest.raises(ValueError, match="non-regular"):
            _validate_export_path("out.csv")


class TestInputTypes:
    def test_accepts_str_and_path(self, cwd, home):
        _validate_export_path(str(cwd / "a.csv"))
        _validate_export_path(cwd / "a.csv")

    def test_returns_none(self, cwd, home):
        assert _validate_export_path("a.csv") is None
