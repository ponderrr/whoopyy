"""
Tests for strapkit.export._validate_export_path.

The guard only inspects (never writes to) paths, so system locations are checked
by name. Everything user-side lives under tmp_path with HOME pointed at it.
"""

import csv
import io
import os
import sys
from pathlib import Path

import pytest

from strapkit.export import (
    _open_export_file,
    _validate_export_path,
    export_cycle_csv,
    export_recovery_csv,
    export_sleep_csv,
    export_workout_csv,
    generate_summary_report,
)
from strapkit.models import Cycle, Recovery, Sleep, Workout

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
            "/usr/local/share/strapkit/x.csv",
            "/tmp/x.csv",
            "/tmp/strapkit/x.csv",
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
            "Library/Application Support/strapkit/x.csv",
            ".config/x.csv",
            ".config/strapkit/x.csv",
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
            _validate_export_path("~no-such-user-strapkit-test/x.csv")

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


class TestReturnValue:
    def test_returns_resolved_path(self, cwd, home):
        assert _validate_export_path("a.csv") == cwd.resolve() / "a.csv"

    def test_expands_tilde(self, cwd, home):
        result = _validate_export_path("~/a.csv")
        assert isinstance(result, Path)
        assert result == home.resolve() / "a.csv"

    def test_resolves_symlinks_and_dotdot(self, cwd, home):
        (cwd / "real").mkdir()
        (cwd / "alias").symlink_to(cwd / "real")
        assert _validate_export_path("alias/../alias/a.csv") == cwd.resolve() / "real" / "a.csv"


@pytest.fixture(params=["recovery", "sleep", "cycle", "workout"])
def export(
    request, sample_recovery_dict, sample_sleep_dict, sample_cycle_dict, sample_workout_dict
):
    """Each exporter bound to one record: export(path) -> number of rows written."""
    func, records = {
        "recovery": (export_recovery_csv, [Recovery.model_validate(sample_recovery_dict)]),
        "sleep": (export_sleep_csv, [Sleep.model_validate(sample_sleep_dict)]),
        "cycle": (export_cycle_csv, [Cycle.model_validate(sample_cycle_dict)]),
        "workout": (export_workout_csv, [Workout.model_validate(sample_workout_dict)]),
    }[request.param]
    return lambda path: func(records, path, include_unscored=True)


def _rows(path: Path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


class TestExportersWriteTheValidatedPath:
    def test_tilde_is_written_under_home(self, export, cwd, home):
        assert export("~/x.csv") == 1
        assert len(_rows(home / "x.csv")) == 2  # header + record
        assert not (cwd / "~").exists()

    def test_tilde_subdirectory(self, export, cwd, home):
        (home / "exports").mkdir()
        assert export("~/exports/x.csv") == 1
        assert (home / "exports" / "x.csv").is_file()

    def test_relative_path_is_written_relative_to_cwd(self, export, cwd, home):
        assert export("x.csv") == 1
        assert (cwd / "x.csv").is_file()
        assert not (home / "x.csv").exists()

    def test_absolute_path_and_path_objects(self, export, tmp_path, home):
        assert export(tmp_path / "abs.csv") == 1
        assert export(str(tmp_path / "abs-str.csv")) == 1
        assert (tmp_path / "abs.csv").is_file() and (tmp_path / "abs-str.csv").is_file()

    def test_existing_file_is_overwritten(self, export, cwd, home):
        (cwd / "x.csv").write_text("stale\n" * 50)
        export("x.csv")
        assert _rows(cwd / "x.csv")[0] != ["stale"]

    def test_symlink_to_regular_file_writes_through(self, export, cwd, home):
        (cwd / "real.csv").write_text("")
        (cwd / "link.csv").symlink_to(cwd / "real.csv")
        assert export("link.csv") == 1
        assert (cwd / "link.csv").is_symlink()
        assert len(_rows(cwd / "real.csv")) == 2

    @pytest.mark.parametrize(
        "path", ["/etc/x.csv", "/private/etc/x.csv", "/Library/x.csv", "~/.ssh/authorized_keys",
                 "~/.zshrc", "/usr/x.csv"],
    )
    def test_protected_destinations_still_raise_before_writing(self, export, path, cwd, home):
        with pytest.raises(ValueError, match="protected"):
            export(path)
        assert not (home / ".ssh").exists()
        assert not (home / ".zshrc").exists()

    def test_directory_destination_still_raises(self, export, cwd, home):
        (home / "out").mkdir()
        with pytest.raises(ValueError, match="non-regular"):
            export("~/out")


class TestOpenExportFile:
    def test_writes_utf8_without_newline_translation(self, tmp_path):
        with _open_export_file(tmp_path / "a.csv") as f:
            f.write("caf\u00e9\r\n")
        assert (tmp_path / "a.csv").read_bytes() == "caf\u00e9\r\n".encode("utf-8")

    def test_truncates_existing_file(self, tmp_path):
        (tmp_path / "a.csv").write_text("x" * 100)
        with _open_export_file(tmp_path / "a.csv") as f:
            f.write("y")
        assert (tmp_path / "a.csv").read_text() == "y"

    def test_new_file_mode_follows_umask_like_open(self, tmp_path):
        old = os.umask(0o022)
        try:
            with _open_export_file(tmp_path / "a.csv"):
                pass
        finally:
            os.umask(old)
        assert (tmp_path / "a.csv").stat().st_mode & 0o777 == 0o644

    def test_missing_parent_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            _open_export_file(tmp_path / "missing" / "a.csv")

    @pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="needs O_NOFOLLOW")
    def test_refuses_symlink_swapped_in_after_validation(self, tmp_path):
        target = tmp_path / "victim.txt"
        target.write_text("keep me")
        link = tmp_path / "a.csv"
        link.symlink_to(target)
        with pytest.raises(OSError):
            _open_export_file(link)
        assert target.read_text() == "keep me"

    def test_newline_argument_is_honoured(self, tmp_path):
        with _open_export_file(tmp_path / "crlf.txt", newline="\r\n") as f:
            f.write("a\nb")
        assert (tmp_path / "crlf.txt").read_bytes() == b"a\r\nb"
        with _open_export_file(tmp_path / "native.txt", newline=None) as f:
            f.write("a\nb")
        assert (tmp_path / "native.txt").read_bytes() == "a\nb".replace("\n", os.linesep).encode()


class TestSummaryReportOutput:
    """generate_summary_report(output=...) is subject to the same checks as the CSV exporters."""

    @staticmethod
    def report(output=None):
        return generate_summary_report([], [], [], output=output)

    def test_tilde_is_written_under_home(self, cwd, home):
        text = self.report("~/report.txt")
        assert (home / "report.txt").read_text(encoding="utf-8") == text
        assert not (cwd / "~").exists()

    def test_relative_path_is_written_relative_to_cwd(self, cwd, home):
        text = self.report("report.txt")
        assert (cwd / "report.txt").read_text(encoding="utf-8") == text
        assert not (home / "report.txt").exists()

    def test_path_object_and_overwrite(self, tmp_path, home):
        (tmp_path / "report.txt").write_text("stale\n" * 500)
        text = self.report(tmp_path / "report.txt")
        assert (tmp_path / "report.txt").read_text(encoding="utf-8") == text

    def test_symlink_to_regular_file_writes_through(self, cwd, home):
        (cwd / "real.txt").write_text("")
        (cwd / "link.txt").symlink_to(cwd / "real.txt")
        text = self.report("link.txt")
        assert (cwd / "link.txt").is_symlink()
        assert (cwd / "real.txt").read_text(encoding="utf-8") == text

    @pytest.mark.parametrize(
        "path", ["/etc/report.txt", "/private/etc/report.txt", "/Library/report.txt",
                 "~/.ssh/authorized_keys", "~/.zshrc", "/usr/report.txt"],
    )
    def test_protected_destinations_raise_before_writing(self, path, cwd, home):
        with pytest.raises(ValueError, match="protected"):
            self.report(path)
        assert not (home / ".ssh").exists()
        assert not (home / ".zshrc").exists()
        assert list(cwd.iterdir()) == []

    def test_directory_destination_raises(self, cwd, home):
        (home / "out").mkdir()
        with pytest.raises(ValueError, match="non-regular"):
            self.report("~/out")

    def test_file_like_object_still_works(self, cwd, home):
        buf = io.StringIO()
        text = self.report(buf)
        assert buf.getvalue() == text
        assert list(cwd.iterdir()) == []

    def test_open_file_handle_still_works(self, tmp_path, cwd, home):
        with open(tmp_path / "handle.txt", "w", encoding="utf-8") as f:
            text = self.report(f)
        assert (tmp_path / "handle.txt").read_text(encoding="utf-8") == text

    def test_none_returns_string_and_writes_nothing(self, cwd, home):
        text = self.report()
        assert isinstance(text, str) and "WHOOP DATA SUMMARY REPORT" in text
        assert list(cwd.iterdir()) == []
        assert list(home.iterdir()) == []
