"""Creation order is independent of status updates, queue state and metadata ctime."""
import copy
import datetime
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/core'))
import project_order


class ProjectCreationOrder(unittest.TestCase):
    def test_explicit_creation_time_wins_over_directory_and_recent_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entry = {'path': 'projects/old', 'createdAt': '2026-09-01T08:00:00+08:00', 'updatedAt': '2099-01-01T00:00:00Z'}
            self.assertEqual(project_order.created_at(root, entry), entry['createdAt'])
            older = {'id': 'old', 'created_at': entry['createdAt'], 'updated': '2099-01-01T00:00:00Z'}
            newer = {'id': 'new', 'created_at': '2026-10-02T00:00:00Z', 'updated': '2000-01-01T00:00:00Z'}
            self.assertEqual(sorted([older, newer], key=project_order.sort_key, reverse=True)[0]['id'], 'new')

    def test_equal_instants_with_different_offsets_and_missing_invalid_dates(self):
        self.assertEqual(project_order.timestamp('2026-10-02T08:00:00+08:00'), project_order.timestamp('2026-10-02T00:00:00Z'))
        for value in (None, '', 'invalid', '2026-10-02T00:00:00'):
            self.assertEqual(project_order.timestamp(value), 0)

    def test_windows_legacy_directory_creation_is_not_its_modified_time(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / 'projects/legacy'
            folder.mkdir(parents=True)
            entry = {'path': 'projects/legacy', 'updatedAt': '2099-01-01T00:00:00Z'}
            before = project_order.created_at(root, entry)
            os.utime(folder, (1000000000, 1000000000))
            after = project_order.created_at(root, entry)
            self.assertEqual(before, after)
            if os.name == 'nt':
                self.assertIsNotNone(before)

    def test_unix_ctime_cannot_be_used_as_creation_and_paths_stay_in_projects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / 'projects/legacy'
            folder.mkdir(parents=True)
            with patch.object(project_order, 'os', SimpleNamespace(name='posix')), patch.object(Path, 'stat', return_value=SimpleNamespace(st_ctime=1234567890)):
                self.assertIsNone(project_order.created_at(root, {'path': 'projects/legacy'}))
            self.assertIsNone(project_order.created_at(root, {'path': '../outside'}))

    def test_unknown_creation_never_falls_back_to_fresh_activity(self):
        unknown = {'id': 'unknown', 'updatedAt': '2099-01-01T00:00:00Z'}
        known = {'id': 'known', 'created_at': '2026-10-02T00:00:00Z'}
        self.assertEqual(sorted([unknown, known], key=project_order.sort_key, reverse=True)[0]['id'], 'known')

    def test_render_contains_creation_order_pagination_and_retains_existing_filters(self):
        from test_progress_visual import complete_item
        import progress_visual
        old = complete_item()
        old.update(project_id='old', title='old', created_at='2026-09-01T00:00:00Z', updated_at='2099-01-01T00:00:00Z')
        new = copy.deepcopy(old)
        new.update(project_id='new', title='new', created_at='2026-10-02T00:00:00Z')
        page = progress_visual.render_panel({'projects': [old, new], 'alerts': [], 'observed_at': '2026-10-02T00:00:00Z'})
        self.assertLess(page.index('data-project="new"'), page.index('data-project="old"'))
        self.assertIn('pageSize=30', page)
        self.assertIn('id="project-pagination"', page)
        self.assertIn('上一页', page)
        self.assertIn('下一页', page)
        for name in ('search', 'stage', 'batch'):
            self.assertIn('id="' + name + '"', page)


if __name__ == '__main__':
    unittest.main()
