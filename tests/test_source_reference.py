import json, os, re, subprocess, sys, tempfile, unittest
from urllib.parse import urljoin
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / 'scripts/core'))
import portable_runtime as rt


class SourceReferencePage(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'data'
        rt.initialize(self.root)
        self.project = self.root / 'projects' / 'synthetic'
        self.project.mkdir(parents=True)
        (self.project / 'reference').mkdir()
        (self.project / 'reference/original.mp4').write_bytes(b'synthetic media placeholder')
        (self.project / 'batches.json').write_text('[]', encoding='utf-8')
        entry = {'id': 'synthetic', 'title': 'Synthetic', 'path': 'projects/synthetic',
                 'mode': 'archive_only', 'conversation': 'Test', 'updatedAt': '2026-01-01T00:00:00+00:00'}
        (self.root / 'projects.json').write_text(json.dumps({'schema_version': 1, 'projects': [entry]}), encoding='utf-8')
        config = Path(self.temp.name) / 'config.json'
        config.write_text(json.dumps(rt.bind({'data_dir': str(self.root)})), encoding='utf-8')
        self.env = dict(os.environ, RUNNINGHUB_CONFIG_FILE=str(config))

    def metadata(self, **changes):
        meta = {'title': 'Source <script>', 'video': 'reference/original.mp4',
                'origin_url': 'https://example.com/source', 'lark_url': 'https://example.com/table',
                'record_id': 'synthetic-record', 'analysis_version': 'synthetic-v1',
                'duration_seconds': 30, 'sha256': 'synthetic-hash',
                'segments': [{'name': 'A01', 'start': 0, 'end': 10},
                             {'name': 'A02', 'start': 10, 'end': 20},
                             {'name': 'A03', 'start': 20, 'end': 30}]}
        meta.update(changes)
        (self.project / 'source_reference.json').write_text(json.dumps(meta), encoding='utf-8')

    def page(self):
        snippet = "import sys,socket,runpy;sys.argv=[sys.argv[1],'render'];socket.create_connection=lambda *a,**k:(_ for _ in ()).throw(AssertionError('network forbidden'));runpy.run_path(sys.argv[0],run_name='__main__')"
        result = subprocess.run([sys.executable, '-c', snippet, str(APP / 'scripts/hub.py')],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((self.root / 'queue_state.json').read_text())['jobs'], [])
        return (self.project / 'index.html').read_text(encoding='utf-8')

    def presentation(self, **changes):
        (self.project / 'review').mkdir(exist_ok=True)
        (self.project / 'review/assembled.mp4').write_bytes(b'synthetic assembled media')
        meta = {'schema_version': 1, 'result_video': 'review/assembled.mp4',
                'result_label': 'New <clip>', 'duration_seconds': 30.2,
                'voiceover': [{'title': 'First', 'text': 'Voice <script>'}]}
        meta.update(changes)
        (self.project / 'presentation.json').write_text(json.dumps(meta), encoding='utf-8')

    def test_assembled_result_is_beside_source_before_closed_production_details(self):
        self.metadata()
        self.presentation()
        for _ in range(2):
            page = self.page()
            self.assertIn('class="comparison-grid"', page)
            self.assertIn('id="comparison-result-player"', page)
            self.assertIn('src="review/assembled.mp4"', page)
            self.assertIn('New &lt;clip&gt;', page)
            self.assertIn('Voice &lt;script&gt;', page)
            self.assertIn('<details id="production-details">', page)
            self.assertIn('<details id="source-details">', page)
            self.assertLess(page.index('id="comparison-result-player"'), page.index('id="production-details"'))
            self.assertLess(page.index('id="production-details"'), page.index('来源对话：'))
            self.assertIn('"presentation": "comparison"', page)
            self.assertIn('异常与复核', page)

    def test_result_path_escape_keeps_source_but_not_external_result(self):
        self.metadata()
        (self.root / 'outside.mp4').write_bytes(b'synthetic outside')
        self.presentation(result_video='../../outside.mp4')
        page = self.page()
        self.assertIn('src="reference/original.mp4"', page)
        self.assertNotIn('id="comparison-result-player"', page)
        self.assertNotIn('src="../../outside.mp4"', page)
        self.assertIn('复刻成片暂不可用', page)

    def test_chinese_source_and_result_copy_are_review_only(self):
        self.metadata()
        self.presentation(audio_language='印尼语',
                          source_voiceover=[{'title': 'Source', 'text': 'Original <copy>'}],
                          source_transcript_note='Machine translation, not listened')
        page = self.page()
        self.assertIn('原片口播 · 中文翻译', page)
        self.assertIn('新版口播 · 中文翻译', page)
        self.assertIn('Original &lt;copy&gt;', page)
        self.assertIn('印尼语配音', page)
        self.assertIn('Machine translation, not listened', page)
        self.assertNotIn('autoplay', page)

    def test_comparison_uses_independent_native_players_without_sync_toolbar(self):
        self.metadata()
        self.presentation()
        page = self.page()
        self.assertIn('aria-label="参考原片"', page)
        self.assertIn('aria-label="复刻成片"', page)
        self.assertNotIn('id="comparison-play"', page)
        self.assertNotIn('id="comparison-audio"', page)
        self.assertNotIn('aria-label="参考原片" muted', page)

    def test_missing_or_malformed_result_metadata_has_honest_empty_state(self):
        self.metadata()
        self.assertIn('复刻成片待完成', self.page())
        self.presentation(result_video='review/missing.mp4')
        self.assertIn('复刻成片暂不可用', self.page())
        (self.project / 'presentation.json').write_text('{invalid', encoding='utf-8')
        self.assertIn('复刻成片暂不可用', self.page())

    def test_source_player_survives_render_and_escapes_metadata(self):
        self.metadata()
        for _ in range(2):
            page = self.page()
            self.assertIn('id="source-reference"', page)
            self.assertIn('src="reference/original.mp4"', page)
            self.assertIn('Source &lt;script&gt;', page)
            self.assertIn('href="https://example.com/source"', page)
            self.assertIn('synthetic-record', page)
            self.assertIn('A02', page)
            self.assertIn('10–20', page)
            self.assertNotIn('autoplay', page)

    def test_absent_metadata_keeps_legacy_page(self):
        page = self.page()
        self.assertNotIn('id="source-reference"', page)
        self.assertNotIn('id="production-details"', page)

    def test_back_link_returns_to_existing_index_at_any_project_depth(self):
        for relative in ('projects/synthetic', 'projects/synthetic/revision-v2'):
            with self.subTest(relative=relative):
                if relative.endswith('revision-v2'):
                    nested = self.project / 'revision-v2'
                    nested.mkdir()
                    (nested / 'batches.json').write_text('[]', encoding='utf-8')
                    self.project = nested
                    registry = json.loads((self.root / 'projects.json').read_text())
                    registry['projects'][0]['path'] = relative
                    (self.root / 'projects.json').write_text(json.dumps(registry))
                page = self.page()
                href = re.search(r'<a href="([^"]+)">← 全部项目</a>', page).group(1)
                destination = urljoin('http://127.0.0.1:18765/' + relative + '/index.html', href)
                self.assertEqual(destination, 'http://127.0.0.1:18765/index.html')
                self.assertTrue((self.root / 'index.html').is_file())

    def test_video_path_cannot_escape_project(self):
        (self.root / 'outside.mp4').write_bytes(b'synthetic outside')
        self.metadata(video='../../outside.mp4')
        page = self.page()
        self.assertNotIn('src="../../outside.mp4"', page)
        self.assertIn('参考原片不可用', page)

    def test_script_links_are_not_rendered(self):
        self.metadata(origin_url='javascript:alert(1)', lark_url='data:text/html,bad')
        page = self.page()
        self.assertIn('src="reference/original.mp4"', page)
        self.assertNotIn('javascript:', page)
        self.assertNotIn('data:text/html', page)


if __name__ == '__main__':
    unittest.main()
