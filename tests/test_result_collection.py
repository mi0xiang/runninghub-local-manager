"""Offline tests: synthetic registry, fake transport, no real tasks or secrets."""
import datetime, json, socket, sys, tempfile, threading, unittest
from pathlib import Path
from unittest.mock import patch

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / 'scripts/core'))
import global_queue, control_server, collector, runninghub_transport


class ResultCollection(unittest.TestCase):
    def test_collection_only_queries_existing_id_and_leaves_approved_waiter_untouched(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / 'projects/synthetic'
            project.mkdir(parents=True)
            (root / 'projects.json').write_text(json.dumps({'projects': [
                {'id': 'synthetic', 'path': 'projects/synthetic', 'title': 'Synthetic'}]}))
            (project / 'batches.json').write_text('["existing", "waiting"]')
            (project / 'approval.json').write_text(json.dumps({
                'status': 'APPROVED', 'submit_permitted': True, 'upload_permitted': True,
                'approved_batches': [{'name': 'waiting', 'hashes': {}}]}))
            for name in ('existing', 'waiting'):
                (project / name).mkdir()
                (project / name / 'manifest.json').write_text('{}')
            state = {'status': 'RUNNING', 'taskId': 'synthetic-id', 'submitAttempts': 1,
                     'submittedAt': (datetime.datetime.now().astimezone() - datetime.timedelta(minutes=10)).isoformat()}
            (project / 'existing/task_state.json').write_text(json.dumps(state))
            def transport(endpoint, payload, secret):
                self.assertEqual(endpoint, '/task/openapi/outputs', 'Only existing-task queries allowed')
                self.assertEqual(payload['taskId'], 'synthetic-id')
                return {'code': 0, 'msg': 'success', 'data': []}
            forbidden_calls = []
            def forbidden(*args, **kwargs):
                forbidden_calls.append(args)
                raise AssertionError('No real network or account/create endpoint allowed')
            with patch.object(collector, 'key', return_value='synthetic-secret'), \
                 patch.object(collector, 'post', side_effect=transport), \
                 patch.object(runninghub_transport, 'post', side_effect=forbidden), \
                 patch.object(socket, 'create_connection', side_effect=forbidden):
                global_queue.schedule(root, submit=False)
            self.assertEqual(forbidden_calls, [])
            stored = json.loads((project / 'existing/task_state.json').read_text())
            self.assertEqual(stored['status'], 'CLOUD_SUCCEEDED')
            self.assertEqual(stored['submitAttempts'], 1)
            self.assertFalse((project / 'waiting/task_state.json').exists())
            self.assertEqual(json.loads((root / 'queue_state.json').read_text())['jobs'][1]['status'], 'WAITING')

    def test_service_worker_runs_collection_only_and_exits_on_stop(self):
        stopped = threading.Event()
        actions = []
        def launch(action):
            actions.append(action)
            stopped.set()
        with patch.object(control_server, 'launch', side_effect=launch):
            control_server.collection_loop(stopped)
        self.assertEqual(actions, ['collect-results'])


if __name__ == '__main__':
    unittest.main()
