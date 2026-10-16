"""Plan migration, fatal stops, and prepared-evidence recovery with mocked inference."""
import csv
import hashlib
import json
import unittest
from unittest.mock import patch

from property_timeline import review_runner as runner
from tests import test_review_runner as fixtures


class EnhancementReviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ReviewRunnerTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.args = self.fixture.args

    def first_pass(self):
        self.args.pilot = 23
        with patch.object(runner, 'model_request', side_effect=self.fixture.fake_model):
            runner.run(self.fixture.work(), self.args)
        self.args.pilot = None
        self.args.unattended = True

    def test_repartition_cannot_inherit_completion_or_count_old_tasks(self):
        self.first_pass()
        with patch.object(runner, 'model_request', side_effect=self.fixture.fake_model):
            runner.run(self.fixture.work(), self.args)
        previous = self.fixture.work()
        old_id = previous.state['cross_plan']['plan_id']
        self.assertTrue(previous.coverage()['cross_review_complete'])
        self.args.max_chars = 10000
        rejected = []
        def model(*args):
            if not rejected:
                rejected.append(True)
                return {'findings': [{'bad': 'shape'}]}, {}
            return self.fixture.fake_model(*args)
        with patch.object(runner, 'model_request', side_effect=model):
            runner.run(self.fixture.work(), self.args)
        work = self.fixture.work()
        coverage = work.coverage()
        self.assertNotEqual(old_id, work.state['cross_plan']['plan_id'])
        self.assertEqual(coverage['cross_tasks_completed'], coverage['cross_tasks_total'] - 1)
        self.assertEqual(coverage['cross_tasks_failed'], 1)
        self.assertFalse(coverage['cross_review_complete'])
        self.assertFalse(work.contextual_review()['complete'])
        self.assertIn('Cross-entry pass is incomplete', (self.fixture.root / 'output/counsel_review.md').read_text())
        with patch.object(runner, 'model_request', side_effect=self.fixture.fake_model) as model:
            runner.run(work, self.args)
            self.assertEqual(model.call_count, 1)
        # Repartition back to the exact old tasks; they can be reused safely.
        self.args.max_chars = 30000
        with patch.object(runner, 'model_request') as model:
            runner.run(self.fixture.work(), self.args)
            model.assert_not_called()
        self.assertTrue(self.fixture.work().coverage()['cross_review_complete'])

    def test_legacy_marker_is_unverified_until_manifest_is_rebuilt(self):
        self.first_pass()
        with patch.object(runner, 'model_request', side_effect=self.fixture.fake_model):
            runner.run(self.fixture.work(), self.args)
        work = self.fixture.work()
        work.state['cross_plan'].pop('task_ids')
        work.state['cross_plan'].pop('plan_id')
        self.assertFalse(work.coverage()['cross_review_complete_for_scope'])
        work.checkpoint()
        with patch.object(runner, 'model_request') as model:
            runner.run(self.fixture.work(), self.args)
            model.assert_not_called()
        self.assertTrue(self.fixture.work().coverage()['cross_review_complete'])

    def test_plan_preview_is_read_only_and_task_ceiling_precedes_calls(self):
        self.first_pass()
        work = self.fixture.work()
        original = work.state_path.read_bytes()
        self.args.max_chars = 10000
        with patch.object(runner, 'model_request') as model:
            preview = runner.preview_plan(work, self.args)
            model.assert_not_called()
        self.assertGreater(preview['total_tasks'], 1)
        self.assertEqual(original, work.state_path.read_bytes())
        self.args.max_cross_tasks = 1
        with patch.object(runner, 'model_request') as model:
            with self.assertRaisesRegex(ValueError, 'exceeding --max-cross-tasks'):
                runner.cross_review(work, self.args)
            model.assert_not_called()

    def test_global_errors_stop_cross_even_when_manual_skipping(self):
        self.first_pass()
        self.args.max_chars = 10000
        self.args.skip_manual_review = True
        for message in ('Plan quota reached', 'Authentication failed', 'Invalid configuration'):
            with self.subTest(message=message):
                with patch.object(runner, 'model_request', side_effect=runner.CodexError(message)) as model:
                    with self.assertRaisesRegex(runner.CodexError, message):
                        runner.run(self.fixture.work(), self.args)
                    self.assertEqual(model.call_count, 1)
                work = self.fixture.work()
                self.assertEqual(work.coverage()['cross_tasks_skipped'], 0)
                self.assertEqual(work.coverage()['reviewed'], 23)
                self.assertEqual(work.state['run_stop']['category'], 'backend')

    def attach_text(self):
        folder = self.fixture.root / 'data/archives/gmail'
        attachment = folder / 'fixture.txt'
        attachment.write_text('Attachment evidence ' * 100)
        index = folder / 'property_email_source_index.csv'
        with index.open(newline='') as stream:
            rows = list(csv.DictReader(stream))
        rows[0]['attachment_files_json'] = json.dumps([{'relative_path': attachment.name,
            'original_filename': attachment.name, 'sha256': hashlib.sha256(attachment.read_bytes()).hexdigest(),
            'byte_size': attachment.stat().st_size, 'available': True}])
        with index.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        return attachment

    def test_refresh_gaps_reprocesses_changed_prepared_inputs_only(self):
        attachment = self.attach_text()
        self.args.attachment_chars = 10
        self.first_pass()
        old = self.fixture.work().state['assessments']['gmail:0001']
        self.assertTrue(old['preparation']['sources'][0]['truncated'])
        with patch.object(runner, 'model_request', side_effect=self.fixture.fake_model):
            runner.cross_review(self.fixture.work(), self.args)
        self.assertTrue(self.fixture.work().coverage()['cross_review_complete'])
        self.args.pilot = 23
        self.args.attachment_chars = 20000
        self.args.refresh_review_gaps = True
        with patch.object(runner, 'model_request', side_effect=self.fixture.fake_model) as model:
            runner.run(self.fixture.work(), self.args)
            self.assertEqual(model.call_count, 1)
            self.assertEqual([e['id'] for e in model.call_args.args[2]['entries']], ['gmail:0001'])
        new = self.fixture.work().state['assessments']['gmail:0001']
        self.assertFalse(self.fixture.work().coverage()['cross_plan_verified'])
        self.assertNotEqual(old['preparation']['digest'], new['preparation']['digest'])
        self.assertFalse(new['preparation']['sources'][0]['truncated'])
        with patch.object(runner, 'model_request') as model:
            runner.run(self.fixture.work(), self.args)
            model.assert_not_called()
        self.assertTrue(attachment.read_text().startswith('Attachment evidence'))

    def test_repaired_extraction_and_failed_refresh_preserve_accepted_result(self):
        self.attach_text()
        self.args.pilot = 23
        with patch.object(runner, 'extract_text', side_effect=RuntimeError('Fixture unavailable')):
            with patch.object(runner, 'model_request', side_effect=self.fixture.fake_model):
                runner.run(self.fixture.work(), self.args)
        work = self.fixture.work()
        old = work.state['assessments']['gmail:0001']
        self.args.refresh_review_gaps = True
        self.args.attachment_chars = 20000
        with patch.object(runner, 'model_request', return_value=({'entries': []}, {})):
            runner.run(self.fixture.work(), self.args)
        self.assertEqual(old, self.fixture.work().state['assessments']['gmail:0001'])
        with patch.object(runner, 'model_request', side_effect=self.fixture.fake_model) as model:
            runner.run(self.fixture.work(), self.args)
            self.assertEqual(model.call_count, 1)
        self.assertFalse(self.fixture.work().state['assessments']['gmail:0001']['review_gaps'])
