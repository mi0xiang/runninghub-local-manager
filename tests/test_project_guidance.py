import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / 'scripts'))
import project_guidance as guidance


class ProjectGuidanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / 'bundle'
        shutil.copytree(guidance.BUNDLE, self.source)
        self.target = self.base / 'project 中文 with spaces'

    def sync(self, apply=False):
        return guidance.sync(self.target, apply=apply, source=self.source)

    def test_preview_has_no_side_effects_and_install_is_idempotent(self):
        report = self.sync()
        self.assertFalse(self.target.exists())
        self.assertFalse(report['conflicts'])
        self.sync(True)
        before = {p.relative_to(self.target): p.read_bytes()
                  for p in self.target.rglob('*') if p.is_file()}
        self.sync(True)
        after = {p.relative_to(self.target): p.read_bytes()
                 for p in self.target.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_two_machine_layouts_and_all_guide_links(self):
        for name in ('work/项目A', 'other-drive/clients/项目B'):
            target = self.base / name
            guidance.sync(target, apply=True, source=self.source)
            for rel in guidance.FILES:
                path = target / rel
                for link in re.findall(r'\[[^\]]*\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
                    link = link.split('#')[0]
                    if link and '://' not in link:
                        self.assertTrue((path.parent / link).is_file(), (rel, link))
            self.assertNotIn(str(target), (target / 'AGENTS.md').read_text(encoding='utf-8'))

    def test_update_preserves_private_context_and_existing_ignore(self):
        self.target.mkdir()
        (self.target / '.gitignore').write_bytes(b'# custom\r\ncache/\r\n')
        self.sync(True)
        private = self.target / '.project-local/README.md'
        private.write_text('PRIVATE synthetic project context', encoding='utf-8')
        source = self.source / '.project-guidance/roles.md'
        source.write_text(source.read_text(encoding='utf-8') + '\nUpdated rule.\n', encoding='utf-8')
        report = self.sync(True)
        self.assertFalse(report['conflicts'])
        self.assertIn('Updated rule.', (self.target / '.project-guidance/roles.md').read_text(encoding='utf-8'))
        self.assertEqual(private.read_text(), 'PRIVATE synthetic project context')
        self.assertTrue((self.target / '.gitignore').read_bytes().startswith(b'# custom\r\ncache/\r\n'))

    def test_existing_or_customized_rules_block_all_writes(self):
        self.target.mkdir()
        root = self.target / 'AGENTS.md'
        root.write_text('user rules', encoding='utf-8')
        report = self.sync(True)
        self.assertIn('AGENTS.md', report['conflicts'])
        self.assertEqual(list(self.target.iterdir()), [root])
        root.unlink()
        self.sync(True)
        root.write_text('customized', encoding='utf-8')
        (self.source / 'AGENTS.md').write_text('upstream revision', encoding='utf-8')
        before = (self.target / '.project-local/template-state.json').read_bytes()
        self.assertIn('AGENTS.md', self.sync(True)['conflicts'])
        self.assertEqual(root.read_text(), 'customized')
        self.assertEqual((self.target / '.project-local/template-state.json').read_bytes(), before)

    def test_deleted_installed_rule_is_not_silently_recreated(self):
        self.sync(True)
        (self.target / '.project-guidance/roles.md').unlink()
        self.assertIn('.project-guidance/roles.md', self.sync(True)['conflicts'])
        self.assertFalse((self.target / '.project-guidance/roles.md').exists())

    def test_extra_private_source_files_never_copy(self):
        (self.source / 'private.json').write_text('{"private":"synthetic"}')
        self.sync(True)
        self.assertFalse((self.target / 'private.json').exists())
        state = json.loads((self.target / '.project-local/template-state.json').read_text())
        self.assertEqual(set(state['files']), set(guidance.FILES))

    def test_existing_comment_or_negation_does_not_expose_private_context(self):
        for index, line in enumerate(('# /.project-local/', '!/.project-local/')):
            target = self.base / ('ignore-case-' + str(index))
            subprocess.run(['git', 'init', '-q', str(target)], check=True)
            (target / '.gitignore').write_text(line + '\n')
            guidance.sync(target, apply=True, source=self.source)
            result = subprocess.run(['git', '-C', str(target), 'check-ignore', '--no-index',
                                     '.project-local/README.md'], capture_output=True)
            self.assertEqual(result.returncode, 0, 'Private context must actually be ignored')

    def test_repository_target_is_rejected(self):
        with self.assertRaises(ValueError):
            guidance.sync(APP / 'should-not-exist', apply=True)
        self.assertFalse((APP / 'should-not-exist').exists())

    def test_destination_cannot_escape_project_root(self):
        with self.assertRaises(ValueError):
            guidance.safe_path(self.target, '../outside.txt')

    def test_symlink_cannot_redirect_installed_files(self):
        self.target.mkdir()
        outside = self.base / 'outside'
        outside.mkdir()
        try:
            (self.target / '.project-guidance').symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('Directory symlink privilege unavailable')
        with self.assertRaises(ValueError):
            self.sync(True)
        self.assertEqual(list(outside.iterdir()), [])

    def test_corrupt_state_is_not_replaced(self):
        self.sync(True)
        state = self.target / '.project-local/template-state.json'
        state.write_text('not json')
        with self.assertRaises(ValueError):
            self.sync(True)
        self.assertEqual(state.read_text(), 'not json')


if __name__ == '__main__':
    unittest.main()
