"""Inspect the Git index without printing matched private values; not a complete DLP system."""
import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT_FILES = {'README.md', 'AGENTS.md', 'START_HERE.md', 'CHANGELOG.md', 'LICENSE',
              '.gitignore', 'manage.py', 'setup.ps1', 'start.ps1', '安装指引.html'}
PUBLIC_DIRS = {'scripts', 'tests', 'docs', 'web', 'templates', '.github'}
PRIVATE_PARTS = {'.local', '.project-local', 'runninghubdata', '.env', '__pycache__',
                 '.venv', 'node_modules', '.git', 'workflow_baselines'}
PUBLIC_SUFFIXES = {'.py', '.md', '.json', '.js', '.css', '.html', '.ps1', '.yml', '.yaml', '.txt'}
PATTERNS = {
    'credential-token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{35,}|sk-[A-Za-z0-9_-]{24,})'),
    'literal-credential': re.compile(r'''(?i)(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)["']?\s*[:=]\s*["']([^"'\r\n]{8,})["']'''),
    'personal-path': re.compile(r'(?i)(?:[a-z]:[/\\](?:Users[/\\]|codex_[^/\\\s]+[/\\])|/(?:Users|home)/[^/\s]+/)'),
    'lark-resource-id': re.compile(r'\b(?:tbl|vew|fld|rec)[A-Za-z0-9]{12,}\b'),
    'private-document-url': re.compile(r'https?://[^/\s]*(?:feishu\.cn|larksuite\.com)/(?:base|sheets|wiki)/[^\s)]+'),
}


def scan_file(name, data, *, mode='100644'):
    path = PurePosixPath(name)
    issues = []
    if (mode not in ('100644', '100755') or
            any(part.lower() in PRIVATE_PARTS or part.lower().startswith('.env') for part in path.parts) or
            (name not in ROOT_FILES and (path.parts[0] not in PUBLIC_DIRS or path.suffix not in PUBLIC_SUFFIXES))):
        issues.append({'path': name, 'line': 0, 'rule': 'publication-path-or-mode'})
    try:
        content = data.decode('utf-8-sig')
        if '\x00' in content:
            raise ValueError()
    except (UnicodeError, ValueError):
        return issues + [{'path': name, 'line': 0, 'rule': 'binary-content'}]
    for line, value in enumerate(content.splitlines(), 1):
        for rule, pattern in PATTERNS.items():
            for match in pattern.finditer(value):
                # Existing examples deliberately use obvious synthetic identities.
                if rule == 'lark-resource-id' and 'fixture' in match.group().lower():
                    continue
                if rule == 'literal-credential' and match.group(1) in ('YOUR_API_KEY', '<API_KEY>'):
                    continue
                issues.append({'path': name, 'line': line, 'rule': rule})
    return issues


def scan_index(root):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE)
    entries = git('ls-files', '--stage', '-z').split(b'\0')
    issues, count = [], 0
    for entry in entries:
        if not entry:
            continue
        meta, raw_name = entry.split(b'\t', 1)
        mode, oid, stage = meta.decode('ascii').split()
        name = raw_name.decode('utf-8')
        count += 1
        if stage != '0':
            issues.append({'path': name, 'line': 0, 'rule': 'unmerged-index'})
            continue
        if mode == '160000':
            issues.append({'path': name, 'line': 0, 'rule': 'submodule-not-reviewed'})
            continue
        issues.extend(scan_file(name, git('cat-file', 'blob', oid), mode=mode))
    return issues, count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        issues, count = scan_index(args.repo)
    except (OSError, subprocess.CalledProcessError, ValueError):
        parser.exit(2, 'Unable to inspect Git index; no file contents printed.\n')
    print(json.dumps({'checked_files': count, 'issues': issues}, ensure_ascii=False, indent=2))
    return 1 if issues else 0


if __name__ == '__main__':
    raise SystemExit(main())
