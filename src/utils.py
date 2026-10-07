"""
Utility functions for the strapkit SDK.

This module provides helper functions for:
- Token storage and retrieval (atomic, owner-only token file)
- Cross-process locking of the token file
- Token expiry checking
- Datetime formatting/parsing for API compatibility
- Rate limit header parsing

Example:
    >>> from strapkit.utils import save_tokens, load_tokens, is_token_expired
    >>> save_tokens(token_data, ".whoop_tokens.json")
    >>> tokens = load_tokens(".whoop_tokens.json")
    >>> if is_token_expired(tokens):
    ...     # Refresh token
    ...     pass
"""

import asyncio
import contextlib
import errno
import importlib
import json
import os
import re
import secrets
import stat
import threading
import time
from datetime import datetime, timezone
from types import ModuleType
from typing import Any, AsyncIterator, Dict, Iterator, Mapping, Optional, Tuple, cast

from .constants import DEFAULT_TOKEN_FILE, TOKEN_REFRESH_BUFFER_SECONDS
from .logger import get_logger
from .type_defs import TokenData

logger = get_logger(__name__)


# =============================================================================
# Error Text Sanitization
# =============================================================================

_REDACTED = "[REDACTED]"

_TOKEN_FIELD_JSON_PATTERN = re.compile(
    r'("(?:access_token|refresh_token|id_token|client_secret)"\s*:\s*")'
    r'(?:[^"\\]|\\.)*(")'
)
"""Matches the string value of a token-bearing field in a JSON body."""

_TOKEN_FIELD_FORM_PATTERN = re.compile(
    r"\b((?:access_token|refresh_token|id_token|client_secret)=)[^&\s\"']+"
)
"""Matches the value of a token-bearing field in a form-encoded body."""

_JWT_PATTERN = re.compile(r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]*){2,4}")
"""Matches a compact JWS (three segments) or JWE (five segments)."""

_JWT_SEGMENT_PATTERN = re.compile(r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{10,}")
"""Matches a lone base64url-encoded JSON segment, e.g. part of a JWT."""

_OPAQUE_TOKEN_PATTERN = re.compile(r"(?<![A-Za-z0-9_-])ory_[a-z]{2}_[A-Za-z0-9_.-]+")
"""Matches opaque Ory-issued tokens (ory_at_..., ory_rt_..., ory_ac_...)."""


def _sanitize_error_response(text: str, max_length: int = 200) -> str:
    """
    Redact credentials from API error response text, then truncate it.

    Redaction runs before truncation so a token that straddles the cut can
    never leak partially. The following are replaced with ``[REDACTED]``:

    - values of ``access_token``, ``refresh_token``, ``id_token`` and
      ``client_secret`` fields (JSON or form-encoded),
    - JWTs (``eyJ...`` header, payload and signature segments) and lone
      ``eyJ...`` base64url segments,
    - opaque Ory-issued tokens (``ory_at_...``, ``ory_rt_...``).

    Args:
        text: Raw response body.
        max_length: Maximum number of characters to keep after redaction.
                    Longer text is cut and suffixed with ``...[truncated]``.

    Returns:
        The sanitized (and possibly truncated) text, or ``""`` for empty input.

    Example:
        >>> _sanitize_error_response('{"error": "bad", "token": "eyJa.eyJb.sig"}')
        '{"error": "bad", "token": "[REDACTED]"}'
    """
    if not text:
        return ""
    sanitized = _TOKEN_FIELD_JSON_PATTERN.sub(r"\1" + _REDACTED + r"\2", text)
    sanitized = _TOKEN_FIELD_FORM_PATTERN.sub(r"\1" + _REDACTED, sanitized)
    sanitized = _JWT_PATTERN.sub(_REDACTED, sanitized)
    sanitized = _JWT_SEGMENT_PATTERN.sub(_REDACTED, sanitized)
    sanitized = _OPAQUE_TOKEN_PATTERN.sub(_REDACTED, sanitized)
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + "...[truncated]"
    return sanitized


__all__ = [
    "_sanitize_error_response",
    "save_tokens",
    "load_tokens",
    "delete_tokens",
    "token_file_lock",
    "async_token_file_lock",
    "is_token_expired",
    "calculate_expiry",
    "format_datetime",
    "parse_datetime",
    "milliseconds_to_hours",
    "milliseconds_to_minutes",
    "parse_rate_limit_reset",
]


# =============================================================================
# Token File Storage
# =============================================================================

_TOKEN_FILE_MODE = 0o600
"""Owner read/write only, for the token file, its temp files and its lock file."""

_IS_WINDOWS = os.name == "nt"

_TEMP_NAME_ATTEMPTS = 10
"""How many unique temp file names save_tokens tries before giving up."""

_REPLACE_ATTEMPTS = 5
"""Attempts at os.replace on Windows, where an open reader blocks the rename."""

_LOAD_ATTEMPTS = 5
"""Attempts at reading a token file that keeps changing while it is read."""

_RETRY_DELAY_SECONDS = 0.01
"""Base back-off between Windows sharing-violation retries."""

_IN_PLACE_TEMP_ERRNOS = frozenset({errno.EACCES, errno.EPERM})
"""
Errors creating the temp file that make save_tokens rewrite the file in place.

They mean the token file's directory is not writable, while the file itself
may still be (the in-place write of 0.3.x worked there).
"""

_IN_PLACE_REPLACE_ERRNOS = frozenset({errno.EBUSY})
"""
os.replace errors that make save_tokens rewrite the file in place.

EBUSY is what Linux reports when the token file is a mount point (e.g. a
Docker single-file bind mount), which cannot be renamed over.
"""


def _optional_module(name: str) -> Optional[ModuleType]:
    """
    Import a platform-specific standard library module if it exists.

    Args:
        name: Module name, e.g. ``"fcntl"`` or ``"msvcrt"``.

    Returns:
        The module, or None when it is not available on this platform.
    """
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


_fcntl: Optional[ModuleType] = _optional_module("fcntl")
"""POSIX ``flock`` support; None on Windows."""

_msvcrt: Optional[ModuleType] = _optional_module("msvcrt")
"""Windows byte-range locking; None on POSIX."""


def _refuse_symlink(path: str) -> None:
    """
    Raise if ``path`` is a symbolic link (dangling or not).

    Args:
        path: Token file path.

    Raises:
        OSError: With errno ELOOP if ``path`` is a symbolic link.
    """
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(st.st_mode):
        raise OSError(
            getattr(errno, "ELOOP", errno.EINVAL),
            "Refusing to write tokens through a symbolic link; "
            "point token_file at a regular file instead",
            path,
        )


def _create_temp_file(directory: str, basename: str) -> Tuple[str, int]:
    """
    Exclusively create an owner-only temp file next to the token file.

    Args:
        directory: Directory of the token file.
        basename: File name of the token file.

    Returns:
        Tuple of (temp file path, open write-only file descriptor).

    Raises:
        OSError: If the file cannot be created.
    """
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_BINARY", 0)
    )
    for _ in range(_TEMP_NAME_ATTEMPTS):
        tmp_path = os.path.join(directory, f".{basename}.{secrets.token_hex(8)}.tmp")
        try:
            return tmp_path, os.open(tmp_path, flags, _TOKEN_FILE_MODE)
        except FileExistsError:
            continue
    raise FileExistsError(
        errno.EEXIST, "Could not create a unique temporary token file", directory
    )


def _write_all(fd: int, payload: bytes) -> None:
    """
    Write all of ``payload`` to ``fd``, handling short writes.

    Args:
        fd: Open file descriptor.
        payload: Bytes to write.

    Raises:
        OSError: If the write fails or makes no progress.
    """
    view = memoryview(payload)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError(errno.EIO, "Short write while saving tokens")
        view = view[written:]


def _replace(src: str, dst: str) -> None:
    """
    Atomically move ``src`` over ``dst``.

    On Windows the rename fails with a sharing violation while another
    process has ``dst`` open, so it is retried briefly there.

    Args:
        src: Fully written temp file.
        dst: Token file path.

    Raises:
        OSError: If the replace keeps failing.
    """
    for attempt in range(1, _REPLACE_ATTEMPTS + 1):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if not _IS_WINDOWS or attempt == _REPLACE_ATTEMPTS:
                raise
            time.sleep(_RETRY_DELAY_SECONDS * attempt)


def _discard_temp_file(tmp_path: str) -> None:
    """
    Remove a temp file left behind by a failed save (best effort).

    Args:
        tmp_path: Temp file path.
    """
    try:
        os.unlink(tmp_path)
    except OSError as e:
        logger.debug(
            "Could not remove temporary token file",
            extra={"filepath": tmp_path, "error": str(e)}
        )


def _fsync_directory(directory: str) -> None:
    """
    Flush a directory entry change to disk (best effort, POSIX only).

    Args:
        directory: Directory whose entries changed.
    """
    if _IS_WINDOWS:
        return
    try:
        dir_fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError as e:
        logger.debug(
            "Could not open token directory for fsync",
            extra={"directory": directory, "error": str(e)}
        )
        return
    try:
        os.fsync(dir_fd)
    except OSError as e:
        logger.debug(
            "Could not fsync token directory",
            extra={"directory": directory, "error": str(e)}
        )
    finally:
        os.close(dir_fd)


def _set_owner_only(fd: int, tmp_path: str) -> None:
    """
    Force mode 0600 on a freshly created temp file (best effort).

    The file was created with mode 0600 filtered by the umask, so it is
    never looser than 0600. The explicit chmod restores owner write access
    when a strict umask removed it. File systems that do not support
    permissions may reject it, which is harmless.

    Args:
        fd: Open temp file descriptor.
        tmp_path: Temp file path (for logging).
    """
    if not hasattr(os, "fchmod"):
        return
    try:
        os.fchmod(fd, _TOKEN_FILE_MODE)
    except OSError as e:
        logger.debug(
            "Could not chmod temporary token file",
            extra={"filepath": tmp_path, "error": str(e)}
        )


def _write_in_place(path: str, payload: bytes) -> None:
    """
    Overwrite an existing token file in place, leaving it mode 0600.

    Only used when the atomic temp-file-and-rename cannot work (see
    _atomic_write). The write is not atomic: a concurrent reader may see
    a partial file (load_tokens retries such a read) and a crash in the
    middle can leave a damaged file.

    Args:
        path: Existing token file (never created here, never a symlink).
        payload: Complete file contents.

    Raises:
        OSError: If the file cannot be opened or written.
    """
    flags = os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags)
    try:
        _set_owner_only(fd, path)
        _write_all(fd, payload)
        # Write first, then cut off the rest, so the file is never empty
        os.ftruncate(fd, len(payload))
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write(path: str, payload: bytes) -> None:
    """
    Replace ``path`` with ``payload`` atomically, leaving it mode 0600.

    The payload goes to a new temp file in the same directory, which is
    fsynced and then renamed over ``path``. Readers see either the old or
    the new file, never a partial one, and a failure at any step leaves
    the previous file untouched.

    Two set-ups cannot rename over the token file, and there an existing
    file is rewritten in place instead (with a warning): a directory the
    process may not create files in (EACCES/EPERM), and a token file that
    is a mount point (os.replace fails with EBUSY, e.g. a Docker
    single-file bind mount).

    Args:
        path: Token file path.
        payload: Complete file contents.

    Raises:
        OSError: If any step fails. The temp file is removed first.
    """
    directory = os.path.dirname(os.path.abspath(path))
    try:
        tmp_path, fd = _create_temp_file(directory, os.path.basename(path))
    except OSError as e:
        if e.errno not in _IN_PLACE_TEMP_ERRNOS or not os.path.isfile(path):
            raise
        logger.warning(
            "Token file directory is not writable, rewriting the token file in place",
            extra={"filepath": path, "error": str(e)}
        )
        _write_in_place(path, payload)
        return
    try:
        try:
            _set_owner_only(fd, tmp_path)
            _write_all(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)
        _replace(tmp_path, path)
    except OSError as e:
        _discard_temp_file(tmp_path)
        if e.errno not in _IN_PLACE_REPLACE_ERRNOS or not os.path.isfile(path):
            raise
        logger.warning(
            "Cannot replace the token file (mount point?), rewriting it in place",
            extra={"filepath": path, "error": str(e)}
        )
        _write_in_place(path, payload)
        return
    except BaseException:
        _discard_temp_file(tmp_path)
        raise
    _fsync_directory(directory)


def _check_token_file_writable(filepath: str) -> None:
    """
    Make sure save_tokens() can write ``filepath``, without changing it.

    Call this before spending a refresh token or an authorization code:
    WHOOP rotates the refresh token, so a refresh whose result cannot be
    saved loses the authorization for every later process. The check
    refuses a symbolic link or a non-regular file at the path, then
    creates and removes a temp file next to it. If the directory is not
    writable, it checks that the existing file can be opened for writing
    (save_tokens then rewrites it in place).

    Args:
        filepath: Token file path.

    Raises:
        OSError: If save_tokens() would fail: the path is a symbolic link
            (ELOOP) or not a regular file, or neither the directory nor
            the file is writable.
    """
    path = os.fspath(filepath)
    _refuse_symlink(path)
    if os.path.exists(path) and not os.path.isfile(path):
        raise OSError(errno.EISDIR, "The token file path is not a regular file", path)

    directory = os.path.dirname(os.path.abspath(path))
    try:
        tmp_path, fd = _create_temp_file(directory, os.path.basename(path))
    except OSError as e:
        if e.errno not in _IN_PLACE_TEMP_ERRNOS:
            raise
        flags = os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        try:
            # Opening without O_TRUNC leaves the file as it is
            os.close(os.open(path, flags))
        except OSError as file_error:
            raise OSError(
                e.errno,
                "Neither the token file's directory nor the token file is writable",
                path,
            ) from file_error
        return
    os.close(fd)
    _discard_temp_file(tmp_path)


def save_tokens(
    tokens: TokenData,
    filepath: str = DEFAULT_TOKEN_FILE
) -> None:
    """
    Save OAuth tokens to a JSON file, atomically and readable only by you.

    The JSON is written to a temp file in the same directory, fsynced and
    then moved over ``filepath`` with ``os.replace``. Concurrent readers
    therefore see the old or the new tokens, never a truncated file, and a
    failed write (full disk, serialization error, crash) leaves the previous
    file intact. The resulting file always has mode 0600, even when it
    existed before with looser permissions.

    If the directory does not allow creating the temp file, or the file
    cannot be replaced because it is a mount point (e.g. a Docker
    single-file bind mount), an existing token file is rewritten in place
    instead, which is not atomic. A warning is logged.

    This function does not lock. Wrap a read-refresh-save sequence in
    :func:`token_file_lock` when several processes share the file.

    Tokens are stored in plaintext JSON. For production use, consider
    using the keyring module for secure storage.

    Args:
        tokens: Token data dictionary to save.
        filepath: Path to save tokens to. Defaults to ~/.whoop_tokens.json.

    Raises:
        OSError: If file cannot be written, or if ``filepath`` is a symbolic
                 link (refused so tokens are never written somewhere else).
        TypeError: If tokens contain non-serializable data.
        ValueError: If tokens contain circular references.

    Example:
        >>> tokens: TokenData = {
        ...     "access_token": "abc123",
        ...     "refresh_token": "xyz789",
        ...     "expires_in": 3600,
        ...     "expires_at": time.time() + 3600,
        ...     "token_type": "Bearer",
        ...     "scope": "offline read:profile"
        ... }
        >>> save_tokens(tokens)
        >>> # Tokens saved to ~/.whoop_tokens.json
    """
    path = os.fspath(filepath)
    try:
        # Serialize first so bad data never touches the file system.
        payload = json.dumps(tokens, indent=2).encode("utf-8")
        _refuse_symlink(path)
        _atomic_write(path, payload)

        logger.info(
            "Tokens saved successfully",
            extra={"filepath": path}
        )
    except (OSError, TypeError, ValueError) as e:
        logger.error(
            "Failed to save tokens",
            extra={"filepath": path, "error": str(e)}
        )
        raise


def _changed_since(path: str, opened: os.stat_result, bytes_read: int) -> bool:
    """
    Tell whether the file at ``path`` changed after it was opened.

    Args:
        path: Token file path.
        opened: ``os.fstat`` of the descriptor that was read.
        bytes_read: Number of bytes actually read from it.

    Returns:
        True if the read was short or the path now names a different or
        modified file.
    """
    if bytes_read != opened.st_size:
        return True
    try:
        current = os.stat(path)
    except OSError:
        return True
    return (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != (
        opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns
    )


def load_tokens(
    filepath: str = DEFAULT_TOKEN_FILE
) -> Optional[TokenData]:
    """
    Load OAuth tokens from a JSON file.

    Safe to call while another thread or process saves tokens: if the file
    is replaced or rewritten during the read and the content is therefore
    unparseable, the read is retried instead of reporting "no tokens".

    Args:
        filepath: Path to load tokens from. Defaults to ~/.whoop_tokens.json.

    Returns:
        Token data dictionary if file exists and is valid, None otherwise.

    Example:
        >>> tokens = load_tokens()
        >>> if tokens:
        ...     print(f"Loaded token expiring at {tokens['expires_at']}")
        ... else:
        ...     print("No saved tokens found")
    """
    path = os.fspath(filepath)
    error = "unknown error"

    for attempt in range(1, _LOAD_ATTEMPTS + 1):
        try:
            with open(path, "rb") as f:
                opened = os.fstat(f.fileno())
                raw = f.read()
        except FileNotFoundError:
            logger.debug(
                "No token file found",
                extra={"filepath": path}
            )
            return None
        except PermissionError as e:
            # On Windows, opening can briefly fail while a writer replaces it.
            error = str(e)
            if _IS_WINDOWS and attempt < _LOAD_ATTEMPTS:
                time.sleep(_RETRY_DELAY_SECONDS * attempt)
                continue
            break
        except OSError as e:
            error = str(e)
            break

        try:
            data: Any = json.loads(raw)
        except ValueError as e:  # JSONDecodeError or UnicodeDecodeError
            error = str(e)
            if attempt < _LOAD_ATTEMPTS and _changed_since(path, opened, len(raw)):
                logger.debug(
                    "Token file changed while being read, retrying",
                    extra={"filepath": path, "attempt": attempt}
                )
                continue
            break

        if not isinstance(data, dict):
            error = "token file does not contain a JSON object"
            break

        logger.info(
            "Tokens loaded successfully",
            extra={"filepath": path}
        )
        return cast(TokenData, data)

    logger.error(
        "Failed to load tokens",
        extra={"filepath": path, "error": error}
    )
    return None


def delete_tokens(filepath: str = DEFAULT_TOKEN_FILE) -> bool:
    """
    Delete saved tokens file.

    Useful for logout/cleanup operations. The ``<filepath>.lock`` sidecar
    used by :func:`token_file_lock` is intentionally left in place: removing
    a lock file other processes may hold would break their exclusion.

    Args:
        filepath: Path to token file. Defaults to ~/.whoop_tokens.json.

    Returns:
        True if file was deleted, False if it didn't exist or could not be
        deleted.

    Example:
        >>> delete_tokens()
        True
    """
    path = os.fspath(filepath)

    try:
        os.unlink(path)
    except FileNotFoundError:
        logger.debug(
            "No token file to delete",
            extra={"filepath": path}
        )
        return False
    except OSError as e:
        logger.error(
            "Failed to delete tokens",
            extra={"filepath": path, "error": str(e)}
        )
        return False

    logger.info(
        "Tokens deleted",
        extra={"filepath": path}
    )
    return True


# =============================================================================
# Token File Locking
# =============================================================================

_LOCK_SUFFIX = ".lock"

_LOCK_POLL_INTERVAL_SECONDS = 0.05
"""Polling period while waiting for a lock without a blocking primitive."""

_LOCK_DEGRADE_ERRNOS = frozenset({errno.ENOENT, errno.EACCES, errno.EPERM, errno.EROFS})
"""Errors opening the lock file that downgrade locking to a no-op."""

_MSVCRT_BUSY_ERRNOS = frozenset({errno.EACCES, getattr(errno, "EDEADLOCK", errno.EDEADLK)})
"""Errors msvcrt.locking raises when another handle holds the lock."""

_LockOwner = Tuple[int, Optional[int]]
"""(thread ident, id of the asyncio task or None) of a lock holder."""

_held_locks: Dict[str, _LockOwner] = {}
"""Lock files this process currently holds, keyed by real path."""

_held_locks_guard = threading.Lock()


def _current_owner() -> _LockOwner:
    """
    Identify the current thread and asyncio task (if any).

    Returns:
        The (thread ident, task id) pair used to detect re-entry.
    """
    try:
        task = asyncio.current_task()
    except RuntimeError:
        task = None
    return threading.get_ident(), (None if task is None else id(task))


def _describe_holder(holder: _LockOwner, owner: _LockOwner) -> str:
    """
    Say who holds a lock that the current thread or task cannot wait for.

    Args:
        holder: Registered (thread ident, task id) of the holder.
        owner: (thread ident, task id) of the caller; same thread as holder.

    Returns:
        A phrase for an error message.
    """
    if holder[1] is not None and holder[1] == owner[1]:
        return "this task already"
    if holder[1] is None:
        if owner[1] is None:
            return "this thread already"
        return "synchronous code on this thread already"
    return (
        "an asyncio task suspended on this thread's event loop (e.g. an async "
        "token refresh in progress)"
    )


def _file_lock_held_by_current_thread(filepath: str) -> bool:
    """
    Tell whether this thread, or a task of its event loop, holds a token file lock.

    Synchronous code that finds this True must not block on anything the
    lock holder might be waiting for: a task suspended on this thread can
    only resume once the synchronous code returns. The answer cannot change
    while synchronous code runs on this thread, so it is safe to act on.

    Args:
        filepath: Token file path (the lock file is ``filepath + ".lock"``).

    Returns:
        True if the lock is registered to the current thread.
    """
    key = os.path.realpath(os.fspath(filepath) + _LOCK_SUFFIX)
    with _held_locks_guard:
        holder = _held_locks.get(key)
    return holder is not None and holder[0] == threading.get_ident()


def _open_lock_file(lock_path: str) -> Optional[int]:
    """
    Open (creating if needed) the sidecar lock file.

    Args:
        lock_path: Lock file path.

    Returns:
        An open file descriptor, or None if the lock file cannot be created
        because the directory is missing, read-only or not writable, in which
        case locking is skipped with a warning.

    Raises:
        OSError: If ``lock_path`` is a symbolic link, or on other errors.
    """
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    try:
        return os.open(lock_path, flags, _TOKEN_FILE_MODE)
    except OSError as e:
        if e.errno == getattr(errno, "ELOOP", None):
            raise OSError(
                e.errno,
                "Refusing to use a symbolic link as the token lock file",
                lock_path,
            ) from e
        if e.errno in _LOCK_DEGRADE_ERRNOS:
            logger.warning(
                "Cannot create token lock file, continuing without cross-process locking",
                extra={"lock_path": lock_path, "error": str(e)}
            )
            return None
        raise


def _prepare_lock(filepath: str, in_async: bool) -> Optional[Tuple[str, str, _LockOwner, int]]:
    """
    Check for re-entry and open the lock file, before waiting for the lock.

    Args:
        filepath: Token file path.
        in_async: True for :func:`async_token_file_lock`, which may wait for
                  another task of its own thread; False for the blocking
                  :func:`token_file_lock`, which must not.

    Returns:
        (lock path, registry key, owner, open descriptor), or None when
        locking is unavailable and the caller should act as a no-op.

    Raises:
        RuntimeError: If waiting would deadlock on a holder in this thread.
        OSError: If the lock file cannot be opened.
    """
    lock_path = os.fspath(filepath) + _LOCK_SUFFIX
    if _fcntl is None and _msvcrt is None:
        logger.debug(
            "No file locking available on this platform, token lock is a no-op",
            extra={"lock_path": lock_path}
        )
        return None

    key = os.path.realpath(lock_path)
    owner = _current_owner()
    with _held_locks_guard:
        holder = _held_locks.get(key)
    # A blocking wait can never see a holder on its own thread release the
    # lock. An async wait can, unless the holder is this very task or
    # synchronous code further down this thread's stack.
    if holder is not None and holder[0] == owner[0] and (
        not in_async or holder[1] in (None, owner[1])
    ):
        raise RuntimeError(
            f"The token file lock is not re-entrant: {_describe_holder(holder, owner)} "
            f"holds {lock_path}, so waiting for it here would deadlock"
        )

    fd = _open_lock_file(lock_path)
    if fd is None:
        return None
    return lock_path, key, owner, fd


def _try_lock(fd: int) -> bool:
    """
    Try once to take the exclusive lock without blocking.

    Args:
        fd: Open lock file descriptor.

    Returns:
        True if the lock was taken, False if someone else holds it.
    """
    if _fcntl is not None:
        try:
            _fcntl.flock(fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        return True
    if _msvcrt is not None:
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            _msvcrt.locking(fd, _msvcrt.LK_NBLCK, 1)
        except OSError as e:
            if e.errno in _MSVCRT_BUSY_ERRNOS:
                return False
            raise
    return True


def _poll_delays(lock_path: str, timeout: Optional[float]) -> Iterator[float]:
    """
    Yield how long to sleep before each further lock attempt.

    The generator never ends on its own: it raises once ``timeout`` has
    elapsed, so callers break out when they get the lock.

    Args:
        lock_path: Lock file path (for the error message).
        timeout: Seconds to keep trying, or None for no limit.

    Yields:
        Sleep durations in seconds.

    Raises:
        TimeoutError: Once ``timeout`` has elapsed.
    """
    deadline = None if timeout is None else time.monotonic() + max(0.0, timeout)
    while True:
        delay = _LOCK_POLL_INTERVAL_SECONDS
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"Timed out after {timeout:g}s waiting for token file lock {lock_path}; "
                    "another process or client is using the token file"
                )
            delay = min(delay, remaining)
        yield delay


def _release_lock(key: str, fd: int, lock_path: str) -> None:
    """
    Unregister, unlock and close a held lock.

    Args:
        key: Registry key of the lock file.
        fd: Locked file descriptor.
        lock_path: Lock file path (for logging).
    """
    with _held_locks_guard:
        _held_locks.pop(key, None)
    try:
        if _fcntl is not None:
            _fcntl.flock(fd, _fcntl.LOCK_UN)
        elif _msvcrt is not None:
            os.lseek(fd, 0, os.SEEK_SET)
            _msvcrt.locking(fd, _msvcrt.LK_UNLCK, 1)
    except OSError as e:
        # Closing the descriptor below releases the lock anyway.
        logger.debug(
            "Explicit token lock release failed",
            extra={"lock_path": lock_path, "error": str(e)}
        )
    finally:
        os.close(fd)


@contextlib.contextmanager
def token_file_lock(
    filepath: str = DEFAULT_TOKEN_FILE,
    *,
    timeout: Optional[float] = None,
) -> Iterator[None]:
    """
    Hold an exclusive cross-process lock on a token file.

    WHOOP rotates the refresh token on every refresh, so two processes that
    refresh with the same token at once leave one of them with an invalid
    grant. Wrap "load tokens, refresh, save tokens" in this lock so they
    take turns. The lock is a sidecar file ``"<filepath>.lock"`` (mode 0600,
    never deleted) locked with ``fcntl.flock`` on POSIX or
    ``msvcrt.locking`` on Windows. Threads of one process exclude each other
    too. Where neither primitive exists, or the lock file cannot be created
    (missing or read-only directory), the lock is a logged no-op.

    The lock is not re-entrant. Taking it again from the thread that already
    holds it, or from synchronous code on an event loop thread while a task
    of that loop holds it, raises RuntimeError instead of deadlocking.
    Acquire in-process
    locks (threading/asyncio) first and this lock last. In ``async`` code use
    :func:`async_token_file_lock`, which waits without blocking the event
    loop.

    Args:
        filepath: Token file to lock. Defaults to ~/.whoop_tokens.json.
        timeout: Seconds to wait for the lock. None (default) waits
                 indefinitely; 0 tries exactly once.

    Yields:
        None, while the lock is held.

    Raises:
        TimeoutError: If ``timeout`` elapsed before the lock was free.
        RuntimeError: If the current thread, or an asyncio task suspended on
            this thread's event loop, already holds the lock.
        OSError: If the lock file is a symbolic link or cannot be opened.

    Example:
        >>> with token_file_lock(handler.token_file):
        ...     tokens = load_tokens(handler.token_file)
        ...     # refresh, then save_tokens(new_tokens, handler.token_file)
    """
    prepared = _prepare_lock(filepath, in_async=False)
    if prepared is None:
        yield
        return
    lock_path, key, owner, fd = prepared

    try:
        if not _try_lock(fd):
            logger.debug("Waiting for token file lock", extra={"lock_path": lock_path})
            if timeout is None and _fcntl is not None:
                _fcntl.flock(fd, _fcntl.LOCK_EX)
            else:
                for delay in _poll_delays(lock_path, timeout):
                    time.sleep(delay)
                    if _try_lock(fd):
                        break
    except BaseException:
        os.close(fd)
        raise

    with _held_locks_guard:
        _held_locks[key] = owner
    try:
        yield
    finally:
        _release_lock(key, fd, lock_path)


@contextlib.asynccontextmanager
async def async_token_file_lock(
    filepath: str = DEFAULT_TOKEN_FILE,
    *,
    timeout: Optional[float] = None,
) -> AsyncIterator[None]:
    """
    Async twin of :func:`token_file_lock` that never blocks the event loop.

    While another process, thread or task holds the lock, this polls with
    ``await asyncio.sleep`` so other tasks keep running. That matters when
    two clients in the same event loop share a token file: a blocking lock
    would stall the loop while the holder waits for its HTTP refresh, and
    neither could finish.

    Args:
        filepath: Token file to lock. Defaults to ~/.whoop_tokens.json.
        timeout: Seconds to wait for the lock. None (default) waits
                 indefinitely; 0 tries exactly once.

    Yields:
        None, while the lock is held.

    Raises:
        TimeoutError: If ``timeout`` elapsed before the lock was free.
        RuntimeError: If the current task already holds the lock.
        OSError: If the lock file is a symbolic link or cannot be opened.

    Example:
        >>> async with async_token_file_lock(handler.token_file):
        ...     tokens = load_tokens(handler.token_file)
    """
    prepared = _prepare_lock(filepath, in_async=True)
    if prepared is None:
        yield
        return
    lock_path, key, owner, fd = prepared

    try:
        if not _try_lock(fd):
            logger.debug("Waiting for token file lock", extra={"lock_path": lock_path})
            for delay in _poll_delays(lock_path, timeout):
                await asyncio.sleep(delay)
                if _try_lock(fd):
                    break
    except BaseException:
        os.close(fd)
        raise

    with _held_locks_guard:
        _held_locks[key] = owner
    try:
        yield
    finally:
        _release_lock(key, fd, lock_path)


# =============================================================================
# Token Expiry and Formatting Helpers
# =============================================================================


def is_token_expired(
    tokens: TokenData,
    buffer_seconds: int = TOKEN_REFRESH_BUFFER_SECONDS
) -> bool:
    """
    Check if access token is expired or about to expire.
    
    Uses a buffer to proactively refresh tokens before actual expiry,
    preventing failed requests due to race conditions.
    
    Args:
        tokens: Token data to check.
        buffer_seconds: Seconds before expiry to consider expired.
                       Defaults to TOKEN_REFRESH_BUFFER_SECONDS (60s).
    
    Returns:
        True if token is expired or will expire within buffer period.
    
    Example:
        >>> tokens = load_tokens()
        >>> if is_token_expired(tokens):
        ...     # Token expired or expiring soon - refresh it
        ...     tokens = refresh_token(tokens)
        >>> else:
        ...     # Token is still valid
        ...     pass
    """
    expires_at = tokens.get("expires_at", 0)
    current_time = time.time()
    
    # Token is "expired" if current time + buffer >= expiry time
    is_expired = current_time >= (expires_at - buffer_seconds)
    
    if is_expired:
        logger.debug(
            "Token expired or expiring soon",
            extra={
                "expires_at": expires_at,
                "current_time": current_time,
                "buffer_seconds": buffer_seconds
            }
        )
    
    return is_expired


def calculate_expiry(expires_in: int) -> float:
    """
    Calculate token expiry timestamp from expires_in value.
    
    Args:
        expires_in: Seconds until token expires (from OAuth response).
    
    Returns:
        Unix timestamp when token will expire.
    
    Example:
        >>> expires_at = calculate_expiry(3600)  # 1 hour
        >>> print(f"Token expires at {datetime.fromtimestamp(expires_at)}")
    """
    return time.time() + expires_in


def format_datetime(dt: datetime) -> str:
    """
    Format datetime for Whoop API requests.
    
    Converts datetime to ISO 8601 format. If datetime is naive (no timezone),
    assumes UTC.
    
    Args:
        dt: Datetime to format.
    
    Returns:
        ISO 8601 formatted string (e.g., "2024-01-15T10:30:00+00:00").
    
    Example:
        >>> from datetime import datetime
        >>> dt = datetime(2024, 1, 15, 10, 30, 0)
        >>> format_datetime(dt)
        '2024-01-15T10:30:00+00:00'
    """
    # If naive datetime, assume UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    return dt.isoformat()


def parse_datetime(dt_str: str) -> datetime:
    """
    Parse datetime from Whoop API response.
    
    Handles ISO 8601 format with various timezone representations.
    
    Args:
        dt_str: ISO 8601 datetime string from API.
    
    Returns:
        Parsed datetime object with timezone info.
    
    Raises:
        ValueError: If string cannot be parsed.
    
    Example:
        >>> dt = parse_datetime("2024-01-15T10:30:00.000Z")
        >>> print(dt.year, dt.month, dt.day)
        2024 1 15
    """
    # Handle 'Z' suffix (Zulu time = UTC)
    if dt_str.endswith("Z"):
        dt_str = dt_str[:-1] + "+00:00"
    
    return datetime.fromisoformat(dt_str)


def milliseconds_to_hours(milliseconds: int) -> float:
    """
    Convert milliseconds to hours.
    
    Useful for converting sleep/activity durations from API responses.
    
    Args:
        milliseconds: Duration in milliseconds.
    
    Returns:
        Duration in hours (rounded to 2 decimal places).
    
    Example:
        >>> milliseconds_to_hours(28800000)  # 8 hours
        8.0
        >>> milliseconds_to_hours(27000000)  # 7.5 hours
        7.5
    """
    hours = milliseconds / (1000 * 60 * 60)
    return round(hours, 2)


def milliseconds_to_minutes(milliseconds: int) -> float:
    """
    Convert milliseconds to minutes.
    
    Args:
        milliseconds: Duration in milliseconds.
    
    Returns:
        Duration in minutes (rounded to 1 decimal place).
    
    Example:
        >>> milliseconds_to_minutes(3600000)  # 60 minutes
        60.0
    """
    minutes = milliseconds / (1000 * 60)
    return round(minutes, 1)


_NON_NEGATIVE_INT_PATTERN = re.compile(r"[0-9]+")
"""Matches a header value that is a plain non-negative integer (delta-seconds)."""


def _get_header(headers: Mapping[str, str], name: str) -> Optional[str]:
    """
    Look up a header value case-insensitively.

    ``httpx.Headers`` is already case-insensitive; plain dictionaries are
    scanned for a key that matches ``name`` ignoring case.

    Args:
        headers: Response headers.
        name: Header name to look up.

    Returns:
        The header value, or None if the header is absent.
    """
    value = headers.get(name)
    if value is not None:
        return value

    lowered = name.lower()
    for key, candidate in headers.items():
        if isinstance(key, str) and key.lower() == lowered:
            return candidate
    return None


def parse_rate_limit_reset(
    headers: Mapping[str, str],
    default: int = 60,
) -> int:
    """
    Determine how many seconds to wait after a 429 (rate limited) response.

    WHOOP documents an ``X-RateLimit-Reset`` header holding the number of
    seconds until the current rate limit window resets, so it is preferred.
    The standard ``Retry-After`` header (delta-seconds form) is used as a
    fallback. Header names are matched case-insensitively, so both
    ``httpx.Headers`` and plain dictionaries are supported. Values that are
    not plain non-negative integers (e.g. negative numbers, decimals, or
    HTTP-date ``Retry-After`` values) are ignored.

    Args:
        headers: Response headers from the rate-limited request.
        default: Seconds to return when neither header holds a valid
                 non-negative integer. Defaults to 60.

    Returns:
        Number of seconds to wait before retrying.

    Example:
        >>> parse_rate_limit_reset({"X-RateLimit-Reset": "17", "Retry-After": "30"})
        17
        >>> parse_rate_limit_reset({"retry-after": "30"})
        30
        >>> parse_rate_limit_reset({"X-RateLimit-Reset": "-1"})
        60
    """
    for name in ("X-RateLimit-Reset", "Retry-After"):
        raw = _get_header(headers, name)
        if raw is None:
            continue

        text = str(raw).strip()
        if _NON_NEGATIVE_INT_PATTERN.fullmatch(text):
            return int(text)

        logger.debug(
            "Ignoring invalid rate limit header",
            extra={"header": name, "value": text[:32]}
        )

    return default
