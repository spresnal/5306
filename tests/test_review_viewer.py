"""Match generated viewer fingerprints to runner fingerprints."""
import csv
import re
import unittest

from property_timeline.timeline_html import write_html
from property_timeline.combine_timeline import compact_record
from tests import test_review_runner as fixtures


class ReviewViewerTests(unittest.TestCase):
    def test_viewer_matches_runner_hashes_and_embeds_script(self):
        fixture = fixtures.ReviewRunnerTests()
        fixture.setUp()
        try:
            work = fixture.work()
            records = []
            for row in work.records:
                from property_timeline.combine_timeline import parse_archive
                from zoneinfo import ZoneInfo
                parsed, _ = parse_archive(fixture.root / row['archive'], row['id'].split(':')[0], ZoneInfo('America/New_York'))
                records.extend(record for record in parsed if record['id'] == row['id'])
            from property_timeline.review_runner import INSTRUCTIONS
            (work.folder / 'REVIEW_INSTRUCTIONS.md').write_text(INSTRUCTIONS)
            indexes = {}
            for origin, filename, column in (
                    ('gmail', 'property_email_source_index.csv', 'source_email_number'),
                    ('android', 'android_darcy_group_index.csv', 'message_number'),
                    ('iphone', 'iphone_darcy_index.csv', 'message_number')):
                with (fixture.root / 'data/archives' / origin / filename).open(newline='') as stream:
                    indexes[origin] = {int(row[column]): row for row in csv.DictReader(stream)}
            destination = fixture.root / 'output/master_timeline.html'
            write_html(records, indexes['gmail'], 'America/New_York', destination, compact_record,
                       android_index=indexes['android'], iphone_index=indexes['iphone'])
            html = destination.read_text()
            self.assertIn('id="review-file"', html)
            self.assertIn('function validateReview', html)
            self.assertNotIn('REVIEW_SCRIPT', html)
            self.assertIn('content="' + work.criteria_hash + '"', html)
            for record in work.records:
                article = re.search(r'<article id="' + re.escape(record['id']) + r'"[^>]+>', html).group()
                self.assertIn('data-source-hash="' + record['source_hash'] + '"', article)
                self.assertIn('data-review-hash="' + record['review_hash'] + '"', article)
        finally:
            fixture.doCleanups()
