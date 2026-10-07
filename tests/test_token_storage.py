"""
Tests for crash-safe and concurrency-safe token storage in whoopyy.utils.

Covers claim C11 and the JWT redaction in _sanitize_error_response:
- save_tokens is atomic: concurrent readers never see a missing or partial
  file, and a write that fails at any step leaves the previous file intact
  without closing a file descriptor twice;
- the token file always ends up 0600, even if it existed with looser bits;
- a symbolic link at the token path is refused;
- load_tokens retries a read that raced with a writer;
- token_file_lock / async_token_file_lock exclude other processes, threads
  and tasks, and degrade to a no-op where locking is unavailable;
- _sanitize_error_response really redacts JWTs (and other tokens) before
  truncating.

No test sleeps for real: waits are driven by events, fake clocks or
``asyncio.sleep(0)``.
"""

import asyncio
import errno
import json
import logging
import os
import stat
import subprocess
import sys
import textwrap
import threading
import time
import types

import pytest

from whoopyy import utils

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None


posix_only = pytest.mark.skipif(os.name == "nt", reason="POSIX file mode and symlink semantics")
needs_fcntl = pytest.mark.skipif(fcntl is None, reason="needs fcntl.flock")


def _tokens(i: int = 0) -> dict:
    """Build a realistic, distinguishable token payload."""
    return {
        "access_token": f"access-{i:06d}-" + "a" * 64,
        "refresh_token": f"refresh-{i:06d}-" + "r" * 64,
        "expires_in": 3600,
        "expires_at": 1_900_000_000.0 + i,
        "token_type": "Bearer",
        "scope": "offline read:profile read:recovery",
    }


@pytest.fixture
def token_path(tmp_path) -> str:
    return str(tmp_path / "tokens.json")


@pytest.fixture
def previous(token_path) -> bytes:
    """A good token file already on disk; returns its exact bytes."""
    utils.save_tokens(_tokens(1), token_path)
    with open(token_path, "rb") as f:
        return f.read()


@pytest.fixture
def closed_fds(monkeypatch) -> list:
    """Record every os.close() call so double closes can be detected."""
    closed: list = []
    real_close = os.close

    def tracking_close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    monkeypatch.setattr(os, "close", tracking_close)
    return closed


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _dir_entries(path: str) -> list:
    return sorted(os.listdir(os.path.dirname(path)))


def _mode(path: str) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def _run_child(code: str) -> str:
    """Run a short Python snippet in a separate process and return its stdout."""
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _child_flock_probe(lock_path: str) -> str:
    """Ask another process whether it can take an exclusive flock right now."""
    return _run_child(
        f"""
        import fcntl, os
        fd = os.open({lock_path!r}, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("busy")
        else:
            print("acquired")
        """
    )


def _child_token_file_lock_probe(token_path: str) -> str:
    """Ask another process to take token_file_lock without waiting."""
    return _run_child(
        f"""
        from whoopyy.utils import token_file_lock
        try:
            with token_file_lock({token_path!r}, timeout=0):
                print("acquired")
        except TimeoutError:
            print("timeout")
        """
    )


class _FakeClock:
    """Monotonic clock that only advances when the code under test sleeps."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


# =============================================================================
# Concurrent readers and writers
# =============================================================================


class TestConcurrentAccess:
    """Readers racing writers must always see a complete token file."""

    def test_readers_never_see_missing_or_partial_tokens(self, token_path, monkeypatch):
        """Threads hammering load_tokens during repeated saves never get None or junk."""
        monkeypatch.setattr(utils.logger, "disabled", True)
        writes = 300
        expected = {_tokens(i)["access_token"]: _tokens(i) for i in range(writes)}
        utils.save_tokens(_tokens(0), token_path)

        stop = threading.Event()
        reads = [0] * 4
        bad: list = []

        def reader(slot: int) -> None:
            while not stop.is_set():
                got = utils.load_tokens(token_path)
                reads[slot] += 1
                if got is None or expected.get(got.get("access_token")) != got:
                    bad.append(got)

        threads = [threading.Thread(target=reader, args=(n,)) for n in range(len(reads))]
        for t in threads:
            t.start()
        try:
            for i in range(1, writes):
                utils.save_tokens(_tokens(i), token_path)
        finally:
            stop.set()
            for t in threads:
                t.join()

        assert sum(reads) > 0
        assert bad == [], f"{len(bad)} of {sum(reads)} reads were missing or partial"
        assert utils.load_tokens(token_path) == _tokens(writes - 1)
        assert _dir_entries(token_path) == ["tokens.json"]

    def test_concurrent_writers_leave_one_complete_file(self, token_path, monkeypatch):
        """Racing writers never interleave: the result is exactly one writer's tokens."""
        monkeypatch.setattr(utils.logger, "disabled", True)
        barrier = threading.Barrier(4)

        def writer(n: int) -> None:
            barrier.wait()
            for i in range(50):
                utils.save_tokens(_tokens(n * 1000 + i), token_path)

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        final = utils.load_tokens(token_path)
        assert final in [_tokens(n * 1000 + 49) for n in range(4)]
        assert _dir_entries(token_path) == ["tokens.json"]
        if os.name != "nt":
            assert _mode(token_path) == 0o600


# =============================================================================
# Failed writes keep the previous file
# =============================================================================


class TestFailedWriteKeepsPreviousFile:
    """Any failure while saving must leave the old token file byte-for-byte intact."""

    def test_unserializable_tokens_raise_type_error_not_ebadf(
        self, token_path, previous, closed_fds
    ):
        """The original TypeError surfaces (no EBADF from a double close)."""
        with pytest.raises(TypeError):
            utils.save_tokens({**_tokens(2), "bad": object()}, token_path)
        assert closed_fds == []  # serialization fails before any file is opened
        assert _read_bytes(token_path) == previous
        assert utils.load_tokens(token_path) == _tokens(1)
        assert _dir_entries(token_path) == ["tokens.json"]

    def test_serializer_failure_never_touches_disk(self, token_path, previous, monkeypatch):
        """If JSON encoding fails, no file is created, truncated or replaced."""

        def broken_dumps(*args, **kwargs):
            raise ValueError("Circular reference detected")

        monkeypatch.setattr(utils.json, "dumps", broken_dumps)
        with pytest.raises(ValueError, match="Circular"):
            utils.save_tokens(_tokens(2), token_path)
        assert _read_bytes(token_path) == previous
        assert _dir_entries(token_path) == ["tokens.json"]

    def test_write_failure_midway(self, token_path, previous, monkeypatch, closed_fds):
        """os.write failing after a partial write (disk full) keeps the old file."""
        real_write = os.write
        calls = {"n": 0}

        def failing_write(fd, data):
            calls["n"] += 1
            if calls["n"] == 1:
                return real_write(fd, bytes(data[:10]))
            raise OSError(errno.ENOSPC, "No space left on device")

        monkeypatch.setattr(os, "write", failing_write)
        with pytest.raises(OSError) as excinfo:
            utils.save_tokens(_tokens(2), token_path)

        assert excinfo.value.errno == errno.ENOSPC
        assert calls["n"] == 2
        assert len(closed_fds) == len(set(closed_fds)) == 1
        assert _read_bytes(token_path) == previous
        assert _dir_entries(token_path) == ["tokens.json"]

    def test_fsync_failure(self, token_path, previous, monkeypatch, closed_fds):
        """An fsync error (EIO) is reported as-is and keeps the old file."""

        def failing_fsync(fd):
            raise OSError(errno.EIO, "Input/output error")

        monkeypatch.setattr(os, "fsync", failing_fsync)
        with pytest.raises(OSError) as excinfo:
            utils.save_tokens(_tokens(2), token_path)

        assert excinfo.value.errno == errno.EIO
        assert len(closed_fds) == len(set(closed_fds)) == 1
        assert _read_bytes(token_path) == previous
        assert _dir_entries(token_path) == ["tokens.json"]

    def test_replace_failure(self, token_path, previous, monkeypatch):
        """If the final rename fails, the temp file is removed and the old file stays."""

        def failing_replace(src, dst):
            raise OSError(errno.EXDEV, "Invalid cross-device link")

        monkeypatch.setattr(os, "replace", failing_replace)
        with pytest.raises(OSError) as excinfo:
            utils.save_tokens(_tokens(2), token_path)

        assert excinfo.value.errno == errno.EXDEV
        assert _read_bytes(token_path) == previous
        assert _dir_entries(token_path) == ["tokens.json"]

    def test_cleanup_failure_does_not_mask_original_error(self, token_path, previous, monkeypatch):
        """If the temp file cannot be removed either, the original error still surfaces."""

        def failing_replace(src, dst):
            raise OSError(errno.EIO, "replace failed")

        def failing_unlink(path):
            raise OSError(errno.EACCES, "unlink failed")

        monkeypatch.setattr(os, "replace", failing_replace)
        monkeypatch.setattr(os, "unlink", failing_unlink)
        with pytest.raises(OSError, match="replace failed"):
            utils.save_tokens(_tokens(2), token_path)
        assert _read_bytes(token_path) == previous

    def test_interrupt_during_write_cleans_up(self, token_path, previous, monkeypatch):
        """Even KeyboardInterrupt mid-write removes the temp file and keeps the old file."""

        def interrupted_write(fd, data):
            raise KeyboardInterrupt

        monkeypatch.setattr(os, "write", interrupted_write)
        with pytest.raises(KeyboardInterrupt):
            utils.save_tokens(_tokens(2), token_path)
        assert _read_bytes(token_path) == previous
        assert _dir_entries(token_path) == ["tokens.json"]

    def test_zero_byte_write_is_an_error(self, token_path, previous, monkeypatch):
        """A write that makes no progress raises instead of looping forever."""
        monkeypatch.setattr(os, "write", lambda fd, data: 0)
        with pytest.raises(OSError) as excinfo:
            utils.save_tokens(_tokens(2), token_path)
        assert excinfo.value.errno == errno.EIO
        assert _read_bytes(token_path) == previous

    def test_short_writes_are_completed(self, token_path, monkeypatch):
        """Partial os.write results are continued until the whole payload is written."""
        real_write = os.write
        monkeypatch.setattr(os, "write", lambda fd, data: real_write(fd, bytes(data[:7])))
        utils.save_tokens(_tokens(3), token_path)
        assert utils.load_tokens(token_path) == _tokens(3)

    def test_temp_name_collisions_exhausted(self, token_path, previous, monkeypatch):
        """If every temp name is taken, save fails cleanly without touching the target."""
        monkeypatch.setattr(utils.secrets, "token_hex", lambda n: "0" * (2 * n))
        squatter = os.path.join(os.path.dirname(token_path), ".tokens.json.0000000000000000.tmp")
        with open(squatter, "w") as f:
            f.write("not ours")

        with pytest.raises(FileExistsError):
            utils.save_tokens(_tokens(2), token_path)
        assert _read_bytes(token_path) == previous
        assert _read_bytes(squatter) == b"not ours"

    def test_missing_directory_raises(self, tmp_path):
        """Saving into a directory that does not exist raises OSError."""
        with pytest.raises(OSError):
            utils.save_tokens(_tokens(), str(tmp_path / "missing" / "tokens.json"))

    def test_directory_fsync_is_best_effort(self, tmp_path, monkeypatch, closed_fds):
        """A directory that cannot be fsynced is logged, not raised, and its fd is closed."""

        def failing_fsync(fd):
            raise OSError(errno.EINVAL, "fsync not supported")

        monkeypatch.setattr(os, "fsync", failing_fsync)
        utils._fsync_directory(str(tmp_path))
        assert len(closed_fds) == 1

        utils._fsync_directory(str(tmp_path / "does-not-exist"))

    def test_directory_fsync_skipped_on_windows(self, tmp_path, monkeypatch):
        """Directories cannot be opened for fsync on Windows, so it is skipped."""
        monkeypatch.setattr(utils, "_IS_WINDOWS", True)

        def unexpected_open(*args, **kwargs):
            raise AssertionError("directory must not be opened on Windows")

        monkeypatch.setattr(os, "open", unexpected_open)
        utils._fsync_directory(str(tmp_path))

    def test_accepts_pathlike(self, tmp_path):
        """pathlib.Path works for save, load, delete and lock."""
        path = tmp_path / "tokens.json"
        utils.save_tokens(_tokens(4), path)
        assert utils.load_tokens(path) == _tokens(4)
        with utils.token_file_lock(path):
            pass
        assert utils.delete_tokens(path) is True


# =============================================================================
# Windows sharing-violation retries
# =============================================================================


class TestWindowsRetries:
    """os.replace and open can fail transiently on Windows while another handle is open."""

    def test_replace_retried_on_windows(self, token_path, previous, monkeypatch):
        clock = _FakeClock()
        monkeypatch.setattr(time, "sleep", clock.sleep)
        monkeypatch.setattr(utils, "_IS_WINDOWS", True)
        real_replace = os.replace
        failures = {"left": 2}

        def flaky_replace(src, dst):
            if failures["left"]:
                failures["left"] -= 1
                raise PermissionError(errno.EACCES, "sharing violation")
            real_replace(src, dst)

        monkeypatch.setattr(os, "replace", flaky_replace)
        utils.save_tokens(_tokens(2), token_path)

        assert utils.load_tokens(token_path) == _tokens(2)
        assert len(clock.sleeps) == 2

    def test_replace_gives_up_on_windows(self, token_path, previous, monkeypatch):
        clock = _FakeClock()
        monkeypatch.setattr(time, "sleep", clock.sleep)
        monkeypatch.setattr(utils, "_IS_WINDOWS", True)

        def always_denied(src, dst):
            raise PermissionError(errno.EACCES, "sharing violation")

        monkeypatch.setattr(os, "replace", always_denied)
        with pytest.raises(PermissionError):
            utils.save_tokens(_tokens(2), token_path)
        assert len(clock.sleeps) == utils._REPLACE_ATTEMPTS - 1
        assert _read_bytes(token_path) == previous
        assert _dir_entries(token_path) == ["tokens.json"]

    def test_replace_permission_error_not_retried_on_posix(self, token_path, previous, monkeypatch):
        monkeypatch.setattr(utils, "_IS_WINDOWS", False)
        calls = {"n": 0}

        def denied(src, dst):
            calls["n"] += 1
            raise PermissionError(errno.EACCES, "denied")

        monkeypatch.setattr(os, "replace", denied)
        with pytest.raises(PermissionError):
            utils.save_tokens(_tokens(2), token_path)
        assert calls["n"] == 1

    def test_load_retries_permission_error_on_windows(self, token_path, previous, monkeypatch):
        clock = _FakeClock()
        monkeypatch.setattr(time, "sleep", clock.sleep)
        monkeypatch.setattr(utils, "_IS_WINDOWS", True)
        failures = {"left": 1}

        def flaky_open(*args, **kwargs):
            if failures["left"]:
                failures["left"] -= 1
                raise PermissionError(errno.EACCES, "sharing violation")
            return open(*args, **kwargs)

        monkeypatch.setattr(utils, "open", flaky_open, raising=False)
        assert utils.load_tokens(token_path) == _tokens(1)
        assert len(clock.sleeps) == 1

    def test_load_permission_error_on_posix_returns_none(self, token_path, previous, monkeypatch):
        monkeypatch.setattr(utils, "_IS_WINDOWS", False)
        calls = {"n": 0}

        def denied_open(*args, **kwargs):
            calls["n"] += 1
            raise PermissionError(errno.EACCES, "denied")

        monkeypatch.setattr(utils, "open", denied_open, raising=False)
        assert utils.load_tokens(token_path) is None
        assert calls["n"] == 1


# =============================================================================
# Permissions and symlinks
# =============================================================================


@posix_only
class TestPermissions:
    """The token file must always end up owner read/write only."""

    def test_existing_0644_file_becomes_0600(self, token_path):
        with open(token_path, "w") as f:
            json.dump(_tokens(0), f)
        os.chmod(token_path, 0o644)

        utils.save_tokens(_tokens(1), token_path)

        assert _mode(token_path) == 0o600
        assert utils.load_tokens(token_path) == _tokens(1)

    def test_existing_world_writable_file_becomes_0600_with_open_umask(self, token_path):
        with open(token_path, "w") as f:
            f.write("{}")
        os.chmod(token_path, 0o666)
        old_umask = os.umask(0)
        try:
            utils.save_tokens(_tokens(1), token_path)
        finally:
            os.umask(old_umask)
        assert _mode(token_path) == 0o600

    def test_new_file_is_0600_even_with_strict_umask(self, token_path):
        old_umask = os.umask(0o277)
        try:
            utils.save_tokens(_tokens(1), token_path)
        finally:
            os.umask(old_umask)
        assert _mode(token_path) == 0o600

    def test_chmod_failure_is_tolerated(self, token_path, monkeypatch):
        """File systems without permission support may reject fchmod; save still works."""

        def failing_fchmod(fd, mode):
            raise OSError(errno.EPERM, "Operation not permitted")

        monkeypatch.setattr(os, "fchmod", failing_fchmod)
        utils.save_tokens(_tokens(1), token_path)
        assert utils.load_tokens(token_path) == _tokens(1)
        assert _mode(token_path) & 0o077 == 0

    def test_platform_without_fchmod(self, token_path, monkeypatch):
        """Where os.fchmod does not exist (older Windows Pythons) save still works."""
        monkeypatch.delattr(os, "fchmod")
        utils.save_tokens(_tokens(1), token_path)
        assert utils.load_tokens(token_path) == _tokens(1)
        assert _mode(token_path) & 0o077 == 0


@posix_only
class TestSymlinkRefused:
    """A symbolic link at the token path must never be written through."""

    def test_symlink_to_existing_file_is_refused(self, tmp_path):
        victim = tmp_path / "victim.txt"
        victim.write_text("do not overwrite")
        link = tmp_path / "tokens.json"
        os.symlink(victim, link)

        with pytest.raises(OSError, match="symbolic link") as excinfo:
            utils.save_tokens(_tokens(1), str(link))

        assert excinfo.value.errno == errno.ELOOP
        assert victim.read_text() == "do not overwrite"
        assert os.path.islink(link)
        assert sorted(os.listdir(tmp_path)) == ["tokens.json", "victim.txt"]

    def test_dangling_symlink_is_refused(self, tmp_path):
        target = tmp_path / "elsewhere.json"
        link = tmp_path / "tokens.json"
        os.symlink(target, link)

        with pytest.raises(OSError, match="symbolic link"):
            utils.save_tokens(_tokens(1), str(link))

        assert not target.exists()
        assert os.path.islink(link)


# =============================================================================
# load_tokens robustness
# =============================================================================


class TestLoadTokensRobustness:
    """load_tokens tolerates races but still reports genuinely bad files."""

    def test_read_racing_a_replace_is_retried(self, token_path, monkeypatch):
        """Content read just as the file was replaced is re-read, not reported as None."""
        with open(token_path, "w") as f:
            f.write('{"access_token": "half-writ')  # what an in-place writer leaves mid-write
        real_loads = json.loads
        calls = {"n": 0}

        def loads_while_writer_finishes(raw, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                # A writer completes between our read and our parse.
                utils.save_tokens(_tokens(5), token_path)
            return real_loads(raw, *args, **kwargs)

        monkeypatch.setattr(utils.json, "loads", loads_while_writer_finishes)
        assert utils.load_tokens(token_path) == _tokens(5)
        assert calls["n"] == 2

    def test_in_place_rewrite_detected_by_size_change(self, token_path, monkeypatch):
        """A short read (file grew after open) is retried."""
        with open(token_path, "w") as f:
            json.dump(_tokens(6), f)
        real_fstat = os.fstat
        calls = {"n": 0}

        def stale_fstat(fd):
            calls["n"] += 1
            st = real_fstat(fd)
            if calls["n"] == 1:
                # Pretend the size changed between open and read.
                fields = list(st)
                fields[stat.ST_SIZE] = st.st_size + 1
                return os.stat_result(fields)
            return st

        monkeypatch.setattr(os, "fstat", stale_fstat)
        original_loads = json.loads
        first = {"done": False}

        def corrupt_first_parse(raw, *args, **kwargs):
            if not first["done"]:
                first["done"] = True
                raise json.JSONDecodeError("Expecting value", "", 0)
            return original_loads(raw, *args, **kwargs)

        monkeypatch.setattr(utils.json, "loads", corrupt_first_parse)
        assert utils.load_tokens(token_path) == _tokens(6)

    def test_file_vanishing_after_bad_read_returns_none(self, token_path, monkeypatch):
        with open(token_path, "w") as f:
            f.write("{")
        real_loads = json.loads

        def loads_then_delete(raw, *args, **kwargs):
            os.unlink(token_path)
            return real_loads(raw, *args, **kwargs)

        monkeypatch.setattr(utils.json, "loads", loads_then_delete)
        assert utils.load_tokens(token_path) is None

    def test_stable_corrupt_file_is_not_retried(self, token_path, monkeypatch):
        """A corrupt file that is not changing returns None after a single parse."""
        with open(token_path, "w") as f:
            f.write("{invalid json}")
        real_loads = json.loads
        calls = {"n": 0}

        def counting_loads(raw, *args, **kwargs):
            calls["n"] += 1
            return real_loads(raw, *args, **kwargs)

        monkeypatch.setattr(utils.json, "loads", counting_loads)
        assert utils.load_tokens(token_path) is None
        assert calls["n"] == 1

    def test_constantly_changing_file_gives_up(self, token_path, monkeypatch):
        """Retries are bounded even if the file keeps changing."""
        with open(token_path, "w") as f:
            f.write("{")
        monkeypatch.setattr(utils, "_changed_since", lambda *args: True)
        real_loads = json.loads
        calls = {"n": 0}

        def counting_loads(raw, *args, **kwargs):
            calls["n"] += 1
            return real_loads(raw, *args, **kwargs)

        monkeypatch.setattr(utils.json, "loads", counting_loads)
        assert utils.load_tokens(token_path) is None
        assert calls["n"] == utils._LOAD_ATTEMPTS

    @pytest.mark.parametrize("content", [b"[]", b'"token"', b"42", b"null"])
    def test_non_object_json_returns_none(self, token_path, content):
        with open(token_path, "wb") as f:
            f.write(content)
        assert utils.load_tokens(token_path) is None

    def test_invalid_utf8_returns_none(self, token_path):
        with open(token_path, "wb") as f:
            f.write(b'{"access_token": "\xff\xfe"}')
        assert utils.load_tokens(token_path) is None

    def test_directory_instead_of_file_returns_none(self, tmp_path):
        assert utils.load_tokens(str(tmp_path)) is None

    def test_changed_since_detects_replacement(self, token_path):
        utils.save_tokens(_tokens(1), token_path)
        with open(token_path, "rb") as f:
            opened = os.fstat(f.fileno())
            size = len(f.read())
        assert utils._changed_since(token_path, opened, size) is False
        utils.save_tokens(_tokens(2), token_path)
        assert utils._changed_since(token_path, opened, size) is True
        os.unlink(token_path)
        assert utils._changed_since(token_path, opened, size) is True


class TestDeleteTokens:
    def test_delete_leaves_lock_file(self, token_path):
        """delete_tokens removes the tokens but keeps the sidecar lock file."""
        utils.save_tokens(_tokens(), token_path)
        with utils.token_file_lock(token_path):
            pass
        assert utils.delete_tokens(token_path) is True
        assert not os.path.exists(token_path)
        if utils._fcntl is not None or utils._msvcrt is not None:
            assert os.path.exists(token_path + ".lock")

    def test_delete_directory_returns_false(self, tmp_path):
        assert utils.delete_tokens(str(tmp_path)) is False


# =============================================================================
# token_file_lock
# =============================================================================


@needs_fcntl
class TestTokenFileLockCrossProcess:
    """The lock must exclude other processes, not just other threads."""

    def test_second_process_is_excluded_while_held(self, token_path):
        lock_path = token_path + ".lock"
        with utils.token_file_lock(token_path):
            assert _child_flock_probe(lock_path) == "busy"
            assert _child_token_file_lock_probe(token_path) == "timeout"
        assert _child_flock_probe(lock_path) == "acquired"
        assert _child_token_file_lock_probe(token_path) == "acquired"

    def test_lock_released_when_body_raises(self, token_path):
        with pytest.raises(ValueError):
            with utils.token_file_lock(token_path):
                raise ValueError("boom")
        assert _child_flock_probe(token_path + ".lock") == "acquired"

    async def test_async_lock_excludes_second_process(self, token_path):
        async with utils.async_token_file_lock(token_path):
            assert _child_flock_probe(token_path + ".lock") == "busy"
        assert _child_flock_probe(token_path + ".lock") == "acquired"

    def test_failed_unlock_still_releases_by_closing(self, token_path, monkeypatch):
        """If LOCK_UN fails, closing the descriptor still releases the lock."""
        real = fcntl

        def flock(fd, op):
            if op == real.LOCK_UN:
                raise OSError(errno.EBADF, "unlock failed")
            return real.flock(fd, op)

        fake = types.SimpleNamespace(
            LOCK_EX=real.LOCK_EX, LOCK_NB=real.LOCK_NB, LOCK_UN=real.LOCK_UN, flock=flock
        )
        monkeypatch.setattr(utils, "_fcntl", fake)
        with utils.token_file_lock(token_path):
            pass
        assert _child_flock_probe(token_path + ".lock") == "acquired"


@needs_fcntl
class TestTokenFileLockInProcess:
    """Threads and nested use within one process."""

    def test_lock_file_is_private_sidecar(self, token_path):
        with utils.token_file_lock(token_path):
            assert os.path.exists(token_path + ".lock")
            assert _mode(token_path + ".lock") == 0o600
        assert os.path.exists(token_path + ".lock")  # never deleted
        assert not os.path.exists(token_path)  # the token file itself is untouched

    def test_other_thread_is_excluded_then_admitted(self, token_path):
        results: list = []

        def try_now() -> None:
            try:
                with utils.token_file_lock(token_path, timeout=0):
                    results.append("acquired")
            except TimeoutError as e:
                results.append(f"timeout: {e}")

        with utils.token_file_lock(token_path):
            t = threading.Thread(target=try_now)
            t.start()
            t.join()
        t = threading.Thread(target=try_now)
        t.start()
        t.join()

        assert results[0].startswith("timeout:") and token_path in results[0]
        assert results[1] == "acquired"

    def test_blocking_waiter_gets_lock_after_release(self, token_path, caplog):
        """A waiter with no timeout blocks in flock and wakes up when the holder releases."""
        waiting = threading.Event()
        acquired = threading.Event()

        class WaitingSignal(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                if record.getMessage() == "Waiting for token file lock":
                    waiting.set()

        def waiter() -> None:
            with utils.token_file_lock(token_path):
                acquired.set()

        caplog.set_level(logging.DEBUG, logger="whoopyy.utils")
        signal = WaitingSignal()
        utils.logger.addHandler(signal)
        try:
            with utils.token_file_lock(token_path):
                t = threading.Thread(target=waiter)
                t.start()
                # The waiter has failed its non-blocking attempt and is about to block.
                assert waiting.wait(10)
                assert not acquired.is_set()
            t.join(10)
        finally:
            utils.logger.removeHandler(signal)
        assert acquired.is_set()

    def test_nested_use_in_same_thread_raises_instead_of_deadlocking(self, token_path):
        with utils.token_file_lock(token_path):
            with pytest.raises(RuntimeError, match="not re-entrant"):
                with utils.token_file_lock(token_path):
                    pass  # pragma: no cover
            # The outer lock is still held.
            assert _child_flock_probe(token_path + ".lock") == "busy"
        assert _child_flock_probe(token_path + ".lock") == "acquired"
        with utils.token_file_lock(token_path):  # usable again afterwards
            pass

    def test_timeout_polls_until_deadline_without_real_sleep(self, token_path, monkeypatch):
        clock = _FakeClock()
        monkeypatch.setattr(utils, "_LOCK_POLL_INTERVAL_SECONDS", 0.25)
        monkeypatch.setattr(time, "monotonic", clock.monotonic)
        monkeypatch.setattr(time, "sleep", clock.sleep)

        holder = os.open(token_path + ".lock", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(holder, fcntl.LOCK_EX)
            with pytest.raises(TimeoutError, match="0.625s"):
                with utils.token_file_lock(token_path, timeout=0.625):
                    pass  # pragma: no cover
        finally:
            os.close(holder)

        assert clock.sleeps == [0.25, 0.25, 0.125]

    def test_timeout_acquires_when_released_while_polling(self, token_path, monkeypatch):
        clock = _FakeClock()
        holder = os.open(token_path + ".lock", os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(holder, fcntl.LOCK_EX)

        def sleep_then_release(seconds: float) -> None:
            clock.sleep(seconds)
            os.close(holder)  # the other holder finishes

        monkeypatch.setattr(time, "monotonic", clock.monotonic)
        monkeypatch.setattr(time, "sleep", sleep_then_release)
        with utils.token_file_lock(token_path, timeout=5):
            assert clock.sleeps == [0.05]

    def test_symlinked_lock_file_is_refused(self, tmp_path):
        target = tmp_path / "elsewhere"
        token_path = str(tmp_path / "tokens.json")
        os.symlink(target, token_path + ".lock")
        with pytest.raises(OSError, match="symbolic link"):
            with utils.token_file_lock(token_path):
                pass  # pragma: no cover
        assert not target.exists()

    def test_unexpected_open_error_propagates(self, tmp_path):
        """Errors other than missing/read-only directories are raised."""
        token_path = str(tmp_path / "tokens.json")
        os.mkdir(token_path + ".lock")  # a directory where the lock file should be
        with pytest.raises(OSError):
            with utils.token_file_lock(token_path):
                pass  # pragma: no cover

    def test_failure_while_waiting_closes_descriptor(self, token_path, monkeypatch, closed_fds):
        def broken_flock(fd, op):
            raise OSError(errno.ENOLCK, "No locks available")

        fake = types.SimpleNamespace(
            LOCK_EX=fcntl.LOCK_EX, LOCK_NB=fcntl.LOCK_NB, LOCK_UN=fcntl.LOCK_UN, flock=broken_flock
        )
        monkeypatch.setattr(utils, "_fcntl", fake)
        with pytest.raises(OSError, match="No locks"):
            with utils.token_file_lock(token_path):
                pass  # pragma: no cover
        assert len(closed_fds) == 1
        assert utils._held_locks == {}


class TestTokenFileLockFallbacks:
    """Where locking is impossible the lock is a logged no-op, never an error."""

    def test_no_locking_primitive_is_a_noop(self, token_path, monkeypatch, caplog):
        monkeypatch.setattr(utils, "_fcntl", None)
        monkeypatch.setattr(utils, "_msvcrt", None)
        caplog.set_level(logging.DEBUG, logger="whoopyy.utils")

        with utils.token_file_lock(token_path):
            with utils.token_file_lock(token_path):  # no registry, so nesting is harmless
                utils.save_tokens(_tokens(1), token_path)

        assert utils.load_tokens(token_path) == _tokens(1)
        assert not os.path.exists(token_path + ".lock")
        assert "No file locking available" in caplog.text

    async def test_async_no_locking_primitive_is_a_noop(self, token_path, monkeypatch):
        monkeypatch.setattr(utils, "_fcntl", None)
        monkeypatch.setattr(utils, "_msvcrt", None)
        async with utils.async_token_file_lock(token_path):
            utils.save_tokens(_tokens(1), token_path)
        assert not os.path.exists(token_path + ".lock")

    def test_missing_directory_degrades_with_warning(self, tmp_path, caplog):
        token_path = str(tmp_path / "missing" / "tokens.json")
        with utils.token_file_lock(token_path):
            pass
        assert "continuing without cross-process locking" in caplog.text

    @posix_only
    @pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores modes")
    def test_read_only_directory_degrades_with_warning(self, tmp_path, caplog):
        token_path = str(tmp_path / "tokens.json")
        with open(token_path, "w") as f:
            json.dump(_tokens(1), f)
        os.chmod(tmp_path, 0o500)
        try:
            with utils.token_file_lock(token_path):
                assert utils.load_tokens(token_path) == _tokens(1)
        finally:
            os.chmod(tmp_path, 0o700)
        assert "continuing without cross-process locking" in caplog.text

    async def test_async_missing_directory_degrades(self, tmp_path, caplog):
        token_path = str(tmp_path / "missing" / "tokens.json")
        async with utils.async_token_file_lock(token_path):
            pass
        assert "continuing without cross-process locking" in caplog.text


class _FakeMsvcrt:
    """Stand-in for msvcrt that simulates another handle holding the lock."""

    LK_NBLCK = 2
    LK_UNLCK = 0

    def __init__(self, busy_attempts: int = 0, error_errno: int = errno.EACCES) -> None:
        self.busy_attempts = busy_attempts
        self.error_errno = error_errno
        self.calls: list = []

    def locking(self, fd: int, mode: int, nbytes: int) -> None:
        assert os.lseek(fd, 0, os.SEEK_CUR) == 0
        self.calls.append((mode, nbytes))
        if mode == self.LK_NBLCK and self.busy_attempts:
            self.busy_attempts -= 1
            raise OSError(self.error_errno, "locked by another handle")


class TestTokenFileLockWindowsBackend:
    """The msvcrt code path, exercised with a fake module on any platform."""

    @pytest.fixture(autouse=True)
    def no_fcntl(self, monkeypatch):
        monkeypatch.setattr(utils, "_fcntl", None)

    def test_polls_until_free_then_unlocks(self, token_path, monkeypatch):
        clock = _FakeClock()
        monkeypatch.setattr(time, "sleep", clock.sleep)
        fake = _FakeMsvcrt(busy_attempts=3)
        monkeypatch.setattr(utils, "_msvcrt", fake)

        with utils.token_file_lock(token_path):
            assert fake.calls == [(fake.LK_NBLCK, 1)] * 4
        assert fake.calls[-1] == (fake.LK_UNLCK, 1)
        assert clock.sleeps == [utils._LOCK_POLL_INTERVAL_SECONDS] * 3

    def test_timeout_zero_when_busy(self, token_path, monkeypatch):
        fake = _FakeMsvcrt(busy_attempts=100)
        monkeypatch.setattr(utils, "_msvcrt", fake)
        with pytest.raises(TimeoutError):
            with utils.token_file_lock(token_path, timeout=0):
                pass  # pragma: no cover

    def test_unexpected_error_is_raised(self, token_path, monkeypatch, closed_fds):
        fake = _FakeMsvcrt(busy_attempts=1, error_errno=errno.EBADF)
        monkeypatch.setattr(utils, "_msvcrt", fake)
        with pytest.raises(OSError) as excinfo:
            with utils.token_file_lock(token_path):
                pass  # pragma: no cover
        assert excinfo.value.errno == errno.EBADF
        assert len(closed_fds) == 1

    def test_failed_unlock_is_logged_not_raised(self, token_path, monkeypatch):
        fake = _FakeMsvcrt()

        def locking(fd, mode, nbytes):
            if mode == fake.LK_UNLCK:
                raise OSError(errno.EACCES, "unlock failed")

        fake.locking = locking
        monkeypatch.setattr(utils, "_msvcrt", fake)
        with utils.token_file_lock(token_path):
            pass


# =============================================================================
# async_token_file_lock
# =============================================================================


@needs_fcntl
class TestAsyncTokenFileLock:
    """The async lock waits by yielding to the event loop."""

    @pytest.fixture(autouse=True)
    def fast_poll(self, monkeypatch):
        monkeypatch.setattr(utils, "_LOCK_POLL_INTERVAL_SECONDS", 0)

    async def test_tasks_in_one_loop_take_turns_without_deadlock(self, token_path):
        order: list = []
        a_holds = asyncio.Event()
        release_a = asyncio.Event()

        async def task_a() -> None:
            async with utils.async_token_file_lock(token_path):
                order.append("a in")
                a_holds.set()
                await release_a.wait()  # e.g. awaiting the HTTP refresh
                order.append("a out")

        async def task_b() -> None:
            await a_holds.wait()
            async with utils.async_token_file_lock(token_path):
                order.append("b in")

        a = asyncio.ensure_future(task_a())
        b = asyncio.ensure_future(task_b())
        await a_holds.wait()
        for _ in range(20):  # b polls (yielding) while a holds the lock
            await asyncio.sleep(0)
        assert order == ["a in"]
        release_a.set()
        await asyncio.wait_for(asyncio.gather(a, b), timeout=10)
        assert order == ["a in", "a out", "b in"]

    async def test_timeout_zero_when_held_by_other_task(self, token_path):
        held = asyncio.Event()
        done = asyncio.Event()

        async def holder() -> None:
            async with utils.async_token_file_lock(token_path):
                held.set()
                await done.wait()

        h = asyncio.ensure_future(holder())
        await held.wait()
        try:
            with pytest.raises(TimeoutError):
                async with utils.async_token_file_lock(token_path, timeout=0):
                    pass  # pragma: no cover
        finally:
            done.set()
            await h

    async def test_timeout_uses_monotonic_deadline(self, token_path, monkeypatch):
        clock = _FakeClock()
        real_sleep = asyncio.sleep

        async def fake_sleep(seconds: float) -> None:
            clock.sleep(seconds)
            await real_sleep(0)

        monkeypatch.setattr(utils, "_LOCK_POLL_INTERVAL_SECONDS", 0.25)
        monkeypatch.setattr(time, "monotonic", clock.monotonic)
        monkeypatch.setattr(asyncio, "sleep", fake_sleep)
        holder = os.open(token_path + ".lock", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(holder, fcntl.LOCK_EX)
            with pytest.raises(TimeoutError):
                async with utils.async_token_file_lock(token_path, timeout=0.625):
                    pass  # pragma: no cover
        finally:
            os.close(holder)
        assert clock.sleeps == [0.25, 0.25, 0.125]

    async def test_nested_in_same_task_raises(self, token_path):
        async with utils.async_token_file_lock(token_path):
            with pytest.raises(RuntimeError, match="not re-entrant"):
                async with utils.async_token_file_lock(token_path):
                    pass  # pragma: no cover

    async def test_blocking_lock_inside_async_holder_raises(self, token_path):
        """The sync lock would block the loop forever here, so it refuses instead."""
        async with utils.async_token_file_lock(token_path):
            with pytest.raises(RuntimeError, match="not re-entrant"):
                with utils.token_file_lock(token_path):
                    pass  # pragma: no cover

    def test_async_lock_under_sync_holder_on_same_thread_raises(self, token_path):
        async def take_async() -> None:
            async with utils.async_token_file_lock(token_path):
                pass  # pragma: no cover

        with utils.token_file_lock(token_path):
            with pytest.raises(RuntimeError, match="not re-entrant"):
                asyncio.run(take_async())

    async def test_failure_while_waiting_closes_descriptor(
        self, token_path, monkeypatch, closed_fds
    ):
        def broken_flock(fd, op):
            raise OSError(errno.ENOLCK, "No locks available")

        fake = types.SimpleNamespace(
            LOCK_EX=fcntl.LOCK_EX, LOCK_NB=fcntl.LOCK_NB, LOCK_UN=fcntl.LOCK_UN, flock=broken_flock
        )
        monkeypatch.setattr(utils, "_fcntl", fake)
        with pytest.raises(OSError, match="No locks"):
            async with utils.async_token_file_lock(token_path):
                pass  # pragma: no cover
        assert len(closed_fds) == 1


# =============================================================================
# _sanitize_error_response
# =============================================================================

# An RS256-shaped JWT: base64url header.payload.signature with a 2048-bit signature.
REAL_JWT = (
    "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTUxNjIzOTAyMn0"
    ".NHVaYe26MbtOYhSKkoKYdFVomg4i8ZJd8_-RU8VNbftc4TSMb4bXP3l3YlNWACwyXPGffz5aXHc6lty1Y2t4SWRqGt"
    "eragsVdZufDn5BlnJl9pdR_kdVFUsra2rWKEofkZeIC4yWytE58sMIihvo9H1ScmmVwBcQP6XETqYd0aSHp1gOa9Rd"
    "UPDvoXQ5oqygTqVtxaDr6wUFKrKItgBMzWIdNZ6y7O9E0DhEPTbE9rfBo6KTFsHAZnMg4k68CDp2woYIaXbmYTWcvbz"
    "IuHO7_37GT79XdIwkm95QJ7hYC9RiwrV7mesbY4PAahERJawntho0my942XheVLmGwLMBkQ"
)


class TestSanitizeErrorResponse:
    """Credentials are redacted before the 200-character truncation."""

    def test_realistic_jwt_is_redacted(self):
        body = json.dumps({"error": "invalid_token", "token": REAL_JWT})
        out = utils._sanitize_error_response(body, max_length=10_000)

        assert out == json.dumps({"error": "invalid_token", "token": "[REDACTED]"})
        for segment in REAL_JWT.split("."):
            assert segment[:12] not in out

    def test_jwt_redacted_and_long_text_still_truncated(self):
        body = f"Bearer {REAL_JWT} rejected: " + "x" * 500
        out = utils._sanitize_error_response(body)

        assert out.endswith("...[truncated]")
        assert len(out) == 200 + len("...[truncated]")
        assert out.startswith("Bearer [REDACTED] rejected: ")
        assert "eyJ" not in out

    def test_jwt_straddling_the_cut_leaks_nothing(self):
        body = "e" * 190 + " " + REAL_JWT
        out = utils._sanitize_error_response(body)
        assert "eyJ" not in out
        assert "NHVaYe26" not in out
        assert len(out) <= 200 + len("...[truncated]")

    def test_jwe_and_unsigned_jwt_are_redacted(self):
        jwe = (
            "eyJhbGciOiJSU0EtT0FFUCJ9.OKOawDo13gRp2ojaHV7LFpZcgV7T6DVZ"
            ".48V1_ALb6US04U3b.5eym8Tw.XFBoMYUZodetZdvTiFvSkQ"
        )
        unsigned = "eyJhbGciOiJub25lIn0.eyJzdWIiOiJ1c2VyIn0."
        out = utils._sanitize_error_response(f"a {jwe} b {unsigned} c", max_length=10_000)
        assert out == "a [REDACTED] b [REDACTED] c"

    def test_lone_jwt_segment_is_redacted(self):
        out = utils._sanitize_error_response("header eyJhbGciOiJSUzI1NiJ9 only")
        assert out == "header [REDACTED] only"

    def test_opaque_ory_tokens_are_redacted(self):
        body = "refresh ory_rt_AbC123-_xyz.SIGNATURE_part failed; access ory_at_q9W8e7"
        out = utils._sanitize_error_response(body)
        assert out == "refresh [REDACTED] failed; access [REDACTED]"

    def test_named_token_fields_are_redacted_in_json(self):
        body = (
            '{"access_token": "opaque-access-123", "refresh_token":"opaque\\"refresh",'
            ' "id_token": "x", "client_secret": "s3cret", "expires_in": 3600}'
        )
        out = utils._sanitize_error_response(body, max_length=10_000)
        assert "opaque" not in out and "s3cret" not in out
        assert out.count("[REDACTED]") == 4
        assert '"expires_in": 3600' in out

    def test_named_token_fields_are_redacted_in_form_body(self):
        body = "grant_type=refresh_token&refresh_token=abc123&client_secret=s3cret&scope=offline"
        out = utils._sanitize_error_response(body)
        assert out == (
            "grant_type=refresh_token&refresh_token=[REDACTED]"
            "&client_secret=[REDACTED]&scope=offline"
        )

    @pytest.mark.parametrize(
        "text",
        [
            '{"error":"invalid_grant","error_description":"The refresh token is invalid"}',
            "heyJude eyJshort is fine",
            "Not Found",
        ],
    )
    def test_ordinary_error_text_is_unchanged(self, text):
        assert utils._sanitize_error_response(text) == text

    def test_empty_text(self):
        assert utils._sanitize_error_response("") == ""

    def test_text_at_limit_is_not_truncated(self):
        assert utils._sanitize_error_response("y" * 200) == "y" * 200
