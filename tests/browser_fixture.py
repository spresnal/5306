"""Build a real-browser integration fixture containing synthetic correspondence only."""
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from property_timeline.combine_timeline import compact_record, parse_archive
from property_timeline.review_evidence import hashed, evidence_hash, criteria_hash
from property_timeline.timeline_html import write_html


def build(root):
    output = root / 'output/timeline.html'
    output.parent.mkdir(parents=True)
    reviews = root / 'data/reviews'
    reviews.mkdir(parents=True)
    brief, instructions = 'Synthetic brief', 'Synthetic instructions'
    (reviews / 'case_brief.md').write_text(brief, encoding='utf-8')
    (reviews / 'REVIEW_INSTRUCTIONS.md').write_text(instructions, encoding='utf-8')
    records, assessments, failures = [], {}, {}
    for origin, body in [('gmail', 'First fixture message.'), ('android', 'Second fixture message.')]:
        archive = root / 'data/archives' / origin / 'fixture.md'
        archive.parent.mkdir(parents=True)
        kind, zone = ('Email', ' UTC') if origin == 'gmail' else ('Message', '')
        archive.write_text(f'## {kind} 0001 — 2026-05-01 12:00{zone}\n'
                           f'**From:** Fixture\n**To:** Reader\n\n{body}\n', encoding='utf-8')
        record = parse_archive(archive, origin, ZoneInfo('America/New_York'))[0][0]
        records.append(record)
        hashes = {'review_hash': evidence_hash(record['text'], {}, archive.parent),
                  'criteria_hash': criteria_hash(brief, instructions)}
        if origin == 'gmail':
            assessments[record['id']] = {'id': record['id'], 'source_hash': hashed(record['text']),
                **hashes, 'priority': 'high', 'topics': ['other'], 'stance': 'context', 'summary': 'Fixture',
                'relevance': 'Fixture', 'assertion': 'Fixture', 'uncertainty': 'Fixture',
                'quotes': [], 'questions': [], 'related_ids': [], 'review_gaps': []}
        else:
            failures[record['id']] = {**hashes, 'manual_review': True, 'error': '<b>Manual fixture reason</b>'}
    write_html(records, {}, 'America/New_York', output, compact_record)
    payload = json.dumps({'schema_version': 1, 'assessments': assessments, 'failures': failures})
    script = r'''
<script>
(async () => {
  const result = document.createElement('pre'); result.id = 'browser-test-result'; document.body.append(result);
  const check = (value, message) => {if (!value) throw new Error(message);};
  const pause = () => new Promise(resolve => setTimeout(resolve, 10));
  const control = id => document.getElementById(id);
  const input = (id, value) => {control(id).value = value; control(id).dispatchEvent(new Event('input'));};
  try {
    const file = new File([PAYLOAD], 'fixture-review.json', {type:'application/json'});
    Object.defineProperty(control('review-file'), 'files', {value:[file], configurable:true});
    control('review-file').dispatchEvent(new Event('change'));
    for (let i=0;i<100 && !control('review-status').textContent.includes('fixture-review.json:');i++) await pause();
    check(control('review-status').textContent.includes('1 manual review'), 'Manual count missing');
    check(control('review-status').textContent.includes('1 current'), 'Current count missing');
    check(document.getElementById('android:0001').querySelector('.review-panel').textContent.includes('<b>Manual fixture reason</b>'), 'Reason text missing');
    check(!document.getElementById('android:0001').querySelector('.review-panel b'), 'Reason interpreted as markup');
    input('review-state', 'manual');
    check(document.getElementById('gmail:0001').hidden, 'Review filter failed');
    input('search', 'First fixture');
    check(document.getElementById('android:0001').hidden, 'Combined correspondence/review filter failed');
    control('reset').click();
    check([...document.querySelectorAll('.card')].every(card => !card.hidden), 'Both reset listeners must run');
    check(control('search').value === '' && control('review-state').value === '', 'Reset values');
    input('origin', 'gmail');
    location.hash = '#android:0001';
    for(let i=0;i<100 && document.getElementById('android:0001').hidden;i++) await pause();
    check(!document.getElementById('android:0001').hidden, 'Hash navigation failed to reveal filtered card');
    control('review-clear').click();
    check(!document.querySelector('.review-panel') && control('review-state').disabled, 'Clear failed');
    check([...document.querySelectorAll('.card')].every(card => !card.hidden), 'Clear visibility');
    result.textContent = 'PASS';
  } catch(error) {result.textContent = 'FAIL: ' + error.message;}
})();
</script>
'''.replace('PAYLOAD', json.dumps(payload).replace('<', '\\u003c'))
    output.write_text(output.read_text(encoding='utf-8').replace('</body>', script + '</body>'), encoding='utf-8')
    return output
