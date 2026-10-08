"""Preview/install a public guide bundle; never export the local project."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

APP = Path(__file__).resolve().parents[1]
KIT = APP / 'templates/project-guidance'
BUNDLE = KIT / 'bundle'
FILES = ('AGENTS.md', '.project-guidance/child.md', '.project-guidance/roles.md',
         '.project-guidance/replication.md', '.project-guidance/audio-visual.md',
         '.project-guidance/pages.md', '.project-guidance/h3.md',
         '.project-guidance/tshirt-replication.md')
STATE = '.project-local/template-state.json'
CONTEXT = '.project-local/README.md'
IGNORE = b'/.project-local/'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(root, relative):
    path = root / relative
    for component in (path, *path.parents):
        if component == root:
            break
        if component.is_symlink() or component.is_junction():
            raise ValueError('Linked destination is not supported: ' + relative)
    if not path.resolve().is_relative_to(root):
        raise ValueError('Destination escapes project: ' + relative)
    if path.exists() and not path.is_file():
        raise ValueError('Expected a regular file: ' + relative)
    return path


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.guidance-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def sync(target, *, apply=False, source=BUNDLE):
    target = Path(target).expanduser().resolve()
    if target == APP or target.is_relative_to(APP):
        raise ValueError('Choose a project directory outside the manager code repository.')
    if target.exists() and not target.is_dir():
        raise ValueError('Project target must be a directory.')
    paths = {rel: safe_path(target, rel) for rel in (*FILES, STATE, CONTEXT, '.gitignore')}
    original = {rel: path.read_bytes() if path.exists() else None for rel, path in paths.items()}
    previous = {}
    if original[STATE] is not None:
        try:
            state = json.loads(original[STATE].decode('utf-8-sig'))
            if state['schema_version'] != 1 or not isinstance(state['files'], dict):
                raise ValueError()
            previous = state['files']
            if any(not isinstance(k, str) or not isinstance(v, str) or len(v) != 64
                   or any(c not in '0123456789abcdef' for c in v) for k, v in previous.items()):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise ValueError('Invalid local template state; preserve it and review manually.') from None

    # Only these public files are read. Never enumerate/copy private directories.
    content = {rel: (Path(source) / rel).read_bytes() for rel in FILES}
    report = {'applied': False, 'files': {}, 'conflicts': []}
    writes = {}
    for rel, new in content.items():
        old = original[rel]
        if old == new:
            status = 'current'
        elif old is None and rel not in previous:
            status = 'create'
        elif old is not None and digest(old) == previous.get(rel):
            status = 'update'
        else:
            status = 'conflict'
            report['conflicts'].append(rel)
        report['files'][rel] = status
        if status in ('create', 'update'):
            writes[rel] = new

    if not apply or report['conflicts']:
        return report

    ignore = original['.gitignore'] or b''
    # Append last: earlier negation patterns cannot accidentally undo this rule.
    if ignore.rstrip(b'\r\n').splitlines()[-1:] != [IGNORE]:
        writes['.gitignore'] = ignore + (b'\n' if ignore and not ignore.endswith(b'\n') else b'') + IGNORE + b'\n'
    if original[CONTEXT] is None:
        writes[CONTEXT] = (KIT / 'local-context.example.md').read_bytes()
    state_bytes = (json.dumps({'schema_version': 1, 'files': {
        rel: digest(data) for rel, data in content.items()}}, indent=2) + '\n').encode('utf-8')
    if original[STATE] != state_bytes:
        writes[STATE] = state_bytes

    # Recheck after planning, before creating any files. Individual writes are atomic.
    for rel, expected in original.items():
        path = safe_path(target, rel)
        if (path.read_bytes() if path.exists() else None) != expected:
            raise ValueError('Project changed during preview; retry without concurrent editing.')
    for rel, data in writes.items():
        atomic_write(paths[rel], data)
    report['applied'] = True
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, help='Existing or new project root, outside this code repository')
    parser.add_argument('--apply', action='store_true', help='Write only when all template paths are safe and conflict-free')
    args = parser.parse_args()
    try:
        report = sync(args.project, apply=args.apply)
    except (ValueError, OSError) as error:
        # OS exception paths can be private; print only the category in that case.
        parser.exit(2, (str(error) if isinstance(error, ValueError) else 'Local file operation failed; inspect project permissions.') + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if report['conflicts'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
