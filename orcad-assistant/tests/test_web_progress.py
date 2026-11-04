import unittest
from types import SimpleNamespace
from unittest.mock import patch
import web_app


class WebProgressTests(unittest.TestCase):
    def run_job(self, kind, work):
        workspace = web_app.Workspace()
        with patch.object(workspace, 'save'), patch.object(web_app.core, 'atomic_json'), patch.object(
            web_app.threading, 'Thread', side_effect=lambda target, daemon: SimpleNamespace(start=target)
        ):
            workspace.start(work, kind=kind)
        return workspace.job

    def test_import_completion_is_waiting_for_generation(self):
        job = self.run_job('import', lambda progress: None)
        self.assertEqual(job['progress'], 0)
        self.assertIn('待生成', job['message'])
        self.assertFalse(job['busy'])

    def test_only_successful_generation_reaches_100(self):
        job = self.run_job('build', lambda progress: progress('正在验证'))
        self.assertEqual(job['progress'], 100)
        self.assertEqual(job['message'], '生成并验证完成')

    def test_generation_failure_does_not_reach_100(self):
        def fail(progress):
            raise ValueError('验证失败')
        job = self.run_job('build', fail)
        self.assertEqual(job['progress'], 0)
        self.assertEqual(job['error'], '验证失败')

    def test_new_project_clears_previous_completion(self):
        workspace = web_app.Workspace()
        workspace.job.update(progress=100, message='生成并验证完成')
        with patch.object(workspace, 'save'):
            workspace.action({'action': 'new'})
        self.assertEqual(workspace.job['progress'], 0)
        self.assertEqual(workspace.job['message'], '准备就绪')
