from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / 'scripts'))
import check_public_tree as public


class PublicTreeTests(unittest.TestCase):
    def test_private_paths_media_and_links_are_rejected(self):
        for path, mode in [('.local/config.json', '100644'),
                           ('templates/project-guidance/.project-local/README.md', '100644'),
                           ('docs/clip.mp4', '100644'), ('scripts/link.py', '120000'),
                           ('RunningHubData/projects.json', '100644')]:
            self.assertTrue(public.scan_file(path, b'{}', mode=mode), path)

    def test_sensitive_content_is_reported_without_values(self):
        examples = [('ghp_' + 'a' * 36), ('tbl' + 'Ab7xZ3pQ9vN2mK6r'),
                    ('C:' + '\\Users\\' + 'Person\\secret.txt'),
                    ('api_key = "' + 'sensitive-example-value' + '"')]
        for content in examples:
            report = public.scan_file('docs/example.md', content.encode())
            self.assertTrue(report)
            self.assertNotIn(content, repr(report))

    def test_synthetic_examples_are_allowed(self):
        example = b'fixtureBaseToken tblFixture vewFixture fldStageFixture\nRUNNINGHUB_API_KEY'
        self.assertEqual(public.scan_file('docs/example.md', example), [])

    def test_scan_uses_index_not_unstaged_replacement_or_ignored_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            private = root / '.local'
            private.mkdir()
            (root / '.gitignore').write_text('/.local/\n')
            (private / 'config.json').write_text('private untouched')
            readme = root / 'README.md'
            readme.write_text('ghp_' + 'a' * 36)
            subprocess.run(['git', '-C', td, 'add', 'README.md', '.gitignore'], check=True)
            readme.write_text('public replacement not staged')
            issues, count = public.scan_index(root)
            self.assertEqual(count, 2)
            self.assertTrue(issues)
            subprocess.run(['git', '-C', td, 'add', 'README.md'], check=True)
            self.assertEqual(public.scan_index(root)[0], [])
            subprocess.run(['git', '-C', td, 'add', '-f', '.local/config.json'], check=True)
            self.assertTrue(public.scan_index(root)[0])


if __name__ == '__main__':
    unittest.main()
