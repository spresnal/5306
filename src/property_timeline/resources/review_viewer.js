// Optional local review overlay. Imported text is always rendered as text, never HTML.
function validateReview(documentValue) {
  const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  const strings = value => Array.isArray(value) && value.every(item => typeof item === 'string');
  const hash = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
  if (!object(documentValue) || documentValue.schema_version !== 1 || !object(documentValue.assessments)) {
    throw new Error('Select entry_review.json from the review workspace (schema version 1).');
  }
  const entries = new Map();
  for (const [id, entry] of Object.entries(documentValue.assessments)) {
    if (!/^(gmail|android|iphone_[a-z0-9_]+):\d+$/.test(id) || !object(entry) || entry.id !== id ||
        !['high', 'medium', 'low', 'uncertain'].includes(entry.priority) ||
        !['supports', 'challenges', 'context', 'unclear'].includes(entry.stance) ||
        !hash(entry.source_hash) || !hash(entry.review_hash) || !hash(entry.criteria_hash) ||
        !['summary', 'relevance', 'assertion', 'uncertainty'].every(key => typeof entry[key] === 'string') ||
        !['topics', 'related_ids', 'questions', 'review_gaps'].every(key => strings(entry[key])) ||
        !Array.isArray(entry.quotes) || !entry.quotes.every(q => object(q) &&
          typeof q.source_id === 'string' && typeof q.text === 'string')) {
      throw new Error('Malformed assessment: ' + id + '. The previous review remains loaded.');
    }
    entries.set(id, entry);
  }
  return entries;
}

function reviewState(entry, card, expectedCriteria) {
  if (!entry) return 'none';
  if (entry.source_hash !== card.dataset.sourceHash || entry.review_hash !== card.dataset.reviewHash ||
      (expectedCriteria && entry.criteria_hash !== expectedCriteria)) return 'stale';
  return expectedCriteria ? 'current' : 'unverified';
}

function contextualFindings(value, cards, expectedCriteria) {
  if (!value) return {byEntry: new Map(), message: 'No source-based second-pass findings saved.'};
  if (value.version !== 2 || typeof value.complete !== 'boolean' ||
      typeof value.criteria_hash !== 'string' || !value.entry_hashes || typeof value.entry_hashes !== 'object' ||
      !Array.isArray(value.findings)) throw new Error('Malformed contextual review.');
  const excluded = value.excluded_ids || [];
  if (!Array.isArray(excluded) || !excluded.every(id => typeof id === 'string')) {
    throw new Error('Malformed contextual exclusions.');
  }
  const validIds = new Set(cards.map(card => card.id));
  const byEntry = new Map();
  for (const finding of value.findings) {
    if (!finding || !/^finding:[a-f0-9]{16}$/.test(finding.id) ||
        !['high', 'medium', 'low', 'uncertain'].includes(finding.contextual_priority) ||
        !['sequence', 'conflict', 'support', 'challenge', 'context', 'uncertain'].includes(finding.kind) ||
        typeof finding.title !== 'string' || typeof finding.analysis !== 'string' ||
        !Array.isArray(finding.entry_ids) || new Set(finding.entry_ids).size < 2 ||
        !finding.entry_ids.every(id => typeof id === 'string') ||
        !Array.isArray(finding.questions) || !finding.questions.every(q => typeof q === 'string') ||
        !Array.isArray(finding.quotes) || !finding.quotes.every(q => q &&
          typeof q.source_id === 'string' && typeof q.text === 'string' &&
          finding.entry_ids.includes(q.source_id.split('/')[0])) ||
        new Set(finding.quotes.map(q => q.source_id.split('/')[0])).size < 2) {
      throw new Error('Malformed cross-entry finding.');
    }
  }
  // A finding depends on the complete review snapshot, not just its visible entry.
  const matching = expectedCriteria && value.criteria_hash === expectedCriteria &&
    Object.keys(value.entry_hashes).length === cards.length && cards.every(card => {
      const hashes = value.entry_hashes[card.id];
      return hashes && hashes.source_hash === card.dataset.sourceHash && hashes.review_hash === card.dataset.reviewHash;
    });
  if (!matching) return {byEntry, message: 'Second-pass findings outdated or criteria unchecked; contextual priorities are not applied.'};
  for (const finding of value.findings) {
    if (!finding.entry_ids.every(id => validIds.has(id))) continue;
    for (const id of finding.entry_ids) {
      if (!byEntry.has(id)) byEntry.set(id, []);
      byEntry.get(id).push(finding);
    }
  }
  return {byEntry, message: value.findings.length + ' cross-entry findings · second pass ' +
    (value.complete ? 'complete for included entries.' : 'in progress.') +
    (excluded.length ? ' Partial coverage: ' + excluded.length + ' manual-review entries excluded.' : '')};
}

function effectivePriority(entry, findings) {
  const ranks = ['high', 'medium', 'uncertain', 'low'];
  return [entry.priority, ...findings.map(f => f.contextual_priority)].sort((a, b) => ranks.indexOf(a) - ranks.indexOf(b))[0];
}

const reviewInput = document.getElementById('review-file');
const reviewPriority = document.getElementById('review-priority');
const reviewTopic = document.getElementById('review-topic');
const reviewStatusFilter = document.getElementById('review-state');
const reviewStatus = document.getElementById('review-status');
const reviewClear = document.getElementById('review-clear');
const expectedCriteria = document.querySelector('meta[name="review-criteria"]').content;
let loadedReview = new Map(), loadedContext = new Map(), loadSequence = 0;

function reviewMatches(card) {
  const entry = loadedReview.get(card.id);
  const state = card.dataset.reviewState || 'none';
  if (reviewStatusFilter.value === 'gaps') {
    if (!entry || !entry.review_gaps.length) return false;
  } else if (reviewStatusFilter.value && reviewStatusFilter.value !== state) return false;
  // Outdated classifications never silently enter the current priority/topic filters.
  if (reviewPriority.value && (state !== 'current' || effectivePriority(entry, loadedContext.get(card.id) || []) !== reviewPriority.value)) return false;
  if (reviewTopic.value && (state !== 'current' || !entry.topics.includes(reviewTopic.value))) return false;
  return true;
}

function reviewNode(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function renderReview(card, entry, state) {
  if (!entry) return;
  const panel = reviewNode('details', undefined, 'review-panel');
  const findings = state === 'current' ? loadedContext.get(card.id) || [] : [];
  const label = state === 'stale' ? 'Review outdated · previous priority: ' :
    state === 'unverified' ? 'Criteria unchecked · priority: ' : findings.length ? 'Pass one · priority: ' : 'AI review · priority: ';
  const summary = reviewNode('summary');
  summary.append(reviewNode('span', label + entry.priority, 'review-badge review-' + (state === 'current' ? entry.priority : state)));
  summary.append(reviewNode('span', ' · ' + entry.topics.map(t => t.replaceAll('_', ' ')).join(' · ')));
  if (findings.length) {
    const effective = effectivePriority(entry, findings);
    summary.append(reviewNode('span', ' · Effective priority: ' + effective, 'review-badge review-' + effective));
    summary.append(reviewNode('span', ' · contextual priority: ' + effectivePriority({priority:'low'}, findings) + ' · ' + findings.length + ' linked findings'));
  }
  if (entry.review_gaps.length) summary.append(reviewNode('span', ' · attachment review gaps'));
  panel.append(summary);
  if (state === 'stale') panel.append(reviewNode('p', 'The entry, indexed evidence, or review criteria changed. Re-review this entry before relying on these annotations.', 'review-warning'));
  if (state === 'unverified') panel.append(reviewNode('p', 'This viewer has no case-brief fingerprint. Rebuild it with the current case brief and review instructions to check the criteria.', 'review-warning'));
  panel.append(reviewNode('p', 'Provisional AI assessment; check the original evidence.'));
  for (const [title, text] of [['Summary', entry.summary], ['Relevance', entry.relevance],
      ['Assertion / stance', entry.assertion + ' / ' + entry.stance], ['Uncertainty', entry.uncertainty]]) {
    panel.append(reviewNode('h4', title), reviewNode('p', text || 'None recorded.'));
  }
  for (const quote of entry.quotes) {
    panel.append(reviewNode('blockquote', quote.text), reviewNode('p', 'Quotation source: ' + quote.source_id, 'review-reference'));
  }
  for (const [title, values] of [['Questions for counsel', entry.questions], ['Review gaps', entry.review_gaps]]) {
    if (!values.length) continue;
    const list = reviewNode('ul');
    for (const value of values) list.append(reviewNode('li', value));
    panel.append(reviewNode('h4', title), list);
  }
  if (entry.related_ids.length) {
    const links = reviewNode('p', 'Related entries: ');
    for (const id of entry.related_ids) {
      if (cards.some(c => c.id === id)) {
        const link = reviewNode('a', id);
        link.href = '#' + encodeURIComponent(id);
        links.append(link, document.createTextNode(' '));
      } else links.append(document.createTextNode(id + ' (not in this viewer) '));
    }
    panel.append(links);
  }
  for (const finding of findings) {
    const section = reviewNode('details', undefined, 'contextual-finding');
    section.append(reviewNode('summary', 'Pass two · ' + finding.contextual_priority + ' · ' + finding.title));
    section.append(reviewNode('p', finding.analysis));
    const links = reviewNode('p', 'Evidence entries: ');
    for (const id of finding.entry_ids) {
      const link = reviewNode('a', id); link.href = '#' + encodeURIComponent(id);
      links.append(link, document.createTextNode(' '));
    }
    section.append(links);
    for (const quote of finding.quotes) section.append(reviewNode('blockquote', quote.text),
      reviewNode('p', 'Quotation source: ' + quote.source_id, 'review-reference'));
    for (const question of finding.questions) section.append(reviewNode('p', 'Counsel question: ' + question));
    panel.append(section);
  }
  card.querySelector('.record-top').after(panel);
}

function clearReview() {
  loadSequence++;
  loadedReview = new Map();
  loadedContext = new Map();
  for (const card of cards) {
    card.querySelector('.review-panel')?.remove();
    delete card.dataset.reviewState;
  }
  for (const control of [reviewPriority, reviewTopic, reviewStatusFilter]) {
    control.value = '';
    control.disabled = true;
  }
  reviewTopic.replaceChildren(reviewNode('option', 'All topics'));
  reviewTopic.firstElementChild.value = '';
  reviewClear.disabled = true;
  reviewInput.value = '';
  reviewStatus.textContent = 'No review loaded. Choose data/reviews/entry_review.json. Review annotations stay in this tab only.';
  filter();
}

reviewInput.addEventListener('change', async () => {
  const file = reviewInput.files[0];
  if (!file) return;
  const sequence = ++loadSequence;
  try {
    if (file.size > 50 * 1024 * 1024) throw new Error('Review file exceeds the 50 MB limit.');
    const value = JSON.parse((await file.text()).replace(/^\uFEFF/, ''));
    const entries = validateReview(value);
    const context = contextualFindings(value.contextual_review, cards, expectedCriteria);
    if (sequence !== loadSequence) return;
    loadedReview = entries;
    loadedContext = context.byEntry;
    const counts = {current: 0, stale: 0, none: 0, unverified: 0};
    const topics = new Set();
    for (const card of cards) {
      card.querySelector('.review-panel')?.remove();
      const entry = entries.get(card.id), state = reviewState(entry, card, expectedCriteria);
      card.dataset.reviewState = state;
      counts[state]++;
      if (state === 'current') for (const topic of entry.topics) topics.add(topic);
      renderReview(card, entry, state);
    }
    reviewTopic.replaceChildren(reviewNode('option', 'All topics'));
    reviewTopic.firstElementChild.value = '';
    for (const topic of [...topics].sort()) {
      const option = reviewNode('option', topic.replaceAll('_', ' '));
      option.value = topic;
      reviewTopic.append(option);
    }
    for (const control of [reviewPriority, reviewTopic, reviewStatusFilter]) {
      control.value = '';
      control.disabled = false;
    }
    reviewClear.disabled = false;
    const orphaned = [...entries.keys()].filter(id => !cards.some(card => card.id === id)).length;
    reviewStatus.textContent = file.name + ': ' + counts.current + ' current · ' + counts.stale +
      ' outdated · ' + counts.none + ' unreviewed · ' + counts.unverified + ' criteria unchecked · ' +
      orphaned + ' IDs absent from this viewer. ' + context.message + ' Annotations are provisional and stored in this tab only.';
    filter();
  } catch (error) {
    if (sequence === loadSequence) reviewStatus.textContent = 'Could not load review. ' +
      (error instanceof SyntaxError ? 'Invalid JSON. The previous review remains loaded.' : error.message);
  } finally {
    if (sequence === loadSequence) reviewInput.value = '';
  }
});
reviewClear.addEventListener('click', clearReview);
for (const control of [reviewPriority, reviewTopic, reviewStatusFilter]) control.addEventListener('input', filter);
document.getElementById('reset').addEventListener('click', () => {
  for (const control of [reviewPriority, reviewTopic, reviewStatusFilter]) control.value = '';
  filter();
});
clearReview();
