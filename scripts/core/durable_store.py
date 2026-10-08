"""Cooperative single-writer fencing and compare-before-write JSON persistence.

No scheduler or cloud calls. Authority is opt-in, stored outside the repository.
It does not provide an OS ACL against arbitrary programs ignoring this contract.
"""
import contextlib
import contextvars
import hashlib
import json
import os
import uuid
from pathlib import Path

CODE_VERSION = 'h3-supervision-v0.2'
_current = contextvars.ContextVar('h3_writer', default=None)

def digest(path):
    path = Path(path)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None

def _authority(root):
    path = Path(root) / 'coordination/writer-authority.json'
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else None

def protected_root(path):
    path = Path(path).resolve()
    for parent in path.parents:
        if (parent/'coordination/writer-authority.json').is_file():
            rel = path.relative_to(parent).as_posix()
            # Credentials and arbitrary media are never read, backed up or served here.
            if rel in ('control_token.json',) or rel.startswith('.local/'):
                return None
            return parent
    return None

def _validate(ctx):
    authority = _authority(ctx['root'])
    if authority is None:
        return
    allowed=ctx['writer_id']==authority.get('writer_id') or ctx['writer_id'] in authority.get('project_writers',{})
    if (authority.get('schema_version') != 1 or not allowed
            or authority.get('epoch') != ctx['epoch']
            or authority.get('code_version') != ctx['code_version']):
        raise PermissionError('Writer identity, epoch or code version is obsolete')

@contextlib.contextmanager
def session(root, writer_id, epoch, code_version=CODE_VERSION):
    ctx = dict(root=Path(root).resolve(), writer_id=writer_id, epoch=epoch,
               code_version=code_version, versions={})
    _validate(ctx)
    token = _current.set(ctx)
    try:
        yield ctx
    finally:
        _current.reset(token)

def read(path, default=None):
    path = Path(path).resolve()
    raw = path.read_bytes() if path.exists() else None
    ctx = _current.get()
    if ctx and path.is_relative_to(ctx['root']):
        ctx['versions'][str(path)] = hashlib.sha256(raw).hexdigest() if raw is not None else None
    return json.loads(raw.decode('utf-8-sig')) if raw is not None else default

@contextlib.contextmanager
def _lock(root):
    import msvcrt
    path = Path(root)/'coordination/writer.process.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as file:
        file.seek(0)
        if os.fstat(file.fileno()).st_size == 0:
            file.write(b'0');file.flush()
        file.seek(0)
        try:
            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError('Shared state writer is busy; reread before retry') from None
        try:
            yield
        finally:
            file.seek(0);msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)

@contextlib.contextmanager
def process_lock(path):
    """Crash-releasing OS lock; PID files are never treated as authority."""
    import msvcrt
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as file:
        file.seek(0)
        if os.fstat(file.fileno()).st_size == 0:
            file.write(b'0');file.flush()
        file.seek(0)
        try:
            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError('Writer/runner busy; reread before retry') from None
        try:
            yield
        finally:
            file.seek(0);msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)

def save(path, value, expected_digest=None, compare=False):
    path = Path(path).resolve()
    root = protected_root(path)
    ctx = _current.get()
    if ctx and not path.is_relative_to(ctx['root']):
        raise PermissionError('Writer output must stay inside configured data root')
    if root and (ctx is None or ctx['root'] != root):
        raise PermissionError('An active coordinator writer session is required')
    with _lock(root) if root else process_lock(path.with_name('.'+path.name+'.write.lock')):
        if root:
            _validate(ctx)
            authority=_authority(root)
            if ctx['writer_id']!=authority['writer_id']:
                scopes=authority.get('project_writers',{}).get(ctx['writer_id'],{}).get('paths',[])
                if not any(path.is_relative_to((root/scope).resolve()) and (root/scope).resolve().is_relative_to(root/'projects') for scope in scopes):
                    raise PermissionError('Project owner cannot write another project or shared state')
        previous = digest(path)
        remembered = ctx['versions'].get(str(path)) if ctx else None
        if ((ctx and str(path) in ctx['versions'] and previous != remembered)
                or (compare and previous != expected_digest)):
            raise RuntimeError('State changed since read; stale write refused')
        serialized = json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')
        path.parent.mkdir(parents=True, exist_ok=True)
        if previous is not None and root and path.suffix == '.json':
            backup = root/'coordination/state-history'/path.relative_to(root)/f'{previous}.json'
            if not backup.exists():
                backup.parent.mkdir(parents=True, exist_ok=True)
                backup.write_bytes(path.read_bytes())
        temp = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            with temp.open('wb') as file:
                file.write(serialized);file.flush();os.fsync(file.fileno())
            os.replace(temp, path)
        finally:
            if temp.exists():temp.unlink()
        if ctx:
            ctx['versions'][str(path)] = hashlib.sha256(serialized).hexdigest()

@contextlib.contextmanager
def configured_session(root):
    """Bind this runtime's code version and current epoch at entry, never mid-write."""
    authority = _authority(root)
    if authority is None:
        yield None
    else:
        with session(root, authority['writer_id'], authority['epoch']):
            yield
