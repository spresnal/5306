// Exercise the actual overlay script with a small DOM; no dependencies or correspondence.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
if (process.argv[3]) {
  const html=fs.readFileSync(process.argv[3],'utf8');
  for(const match of html.matchAll(/<script>([\s\S]*?)<\/script>/g)) new vm.Script(match[1]);
}
class Element {
  constructor(tag='div') { this.tag=tag; this.children=[]; this.dataset={}; this.listeners={}; this.value=''; this.disabled=false; this._text=''; this.className=''; }
  set textContent(value) { this._text=String(value); this.children=[]; }
  get textContent() { return this._text+this.children.map(c=>c.textContent).join(''); }
  get firstElementChild() { return this.children[0]; }
  append(...children) { for(const child of children) { child.parent=this; this.children.push(child); } }
  replaceChildren(...children) { this.children=[]; this.append(...children); }
  addEventListener(name, callback) { this.listeners[name]=callback; }
  querySelector(selector) { return this.children.find(c=>c.className.split(' ').includes(selector.slice(1))) || null; }
  after(child) { child.parent=this.parent; this.parent.children.splice(this.parent.children.indexOf(this)+1,0,child); }
  remove() { this.parent.children=this.parent.children.filter(c=>c!==this); }
}
const hash='a'.repeat(64), changed='b'.repeat(64), criteria='c'.repeat(64);
const controls=Object.fromEntries(['review-file','review-priority','review-topic','review-state','review-status','review-clear','reset'].map(id=>[id,new Element()]));
const cards=['gmail:0001','gmail:0002','iphone_darcy:0001'].map(id=>{
  const card=new Element(); card.id=id; card.dataset={sourceHash:hash,reviewHash:hash};
  const header=new Element(); header.className='record-top'; card.append(header); return card;
});
const document={getElementById:id=>controls[id],querySelector:()=>({content:criteria}),
  createElement:tag=>new Element(tag),createTextNode:text=>{const n=new Element();n.textContent=text;return n;}};
const context=vm.createContext({document,cards,Map,Set,console});
vm.runInContext('function filter(){for(const card of cards)card.hidden=!reviewMatches(card);}',context);
vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),context);
function entry(id,options={}) { return {id,source_hash:hash,review_hash:hash,criteria_hash:criteria,priority:'high',
  topics:['disclosure'],summary:'<img src=x onerror=alert(1)>',relevance:'Evidence',assertion:'Claim',stance:'context',
  uncertainty:'Check',quotes:[{source_id:id,text:'<script>alert(1)</script>'}],questions:['Question?'],
  review_gaps:[],related_ids:['gmail:0002'],...options}; }
async function load(value) {controls['review-file'].files=[{name:'entry_review.json',size:100,text:async()=>JSON.stringify(value)}];await controls['review-file'].listeners.change();}
(async()=>{
  assert.equal(vm.runInContext("validateReview({schema_version:1,assessments:{'iphone_derrick:0001':" +
    JSON.stringify(entry('iphone_derrick:0001')) + "}}).size", context), 1);
  assert.equal(controls['review-clear'].disabled,true);
  await load({schema_version:1,assessments:{'gmail:0001':entry('gmail:0001'),
    'gmail:0002':entry('gmail:0002',{source_hash:changed,review_gaps:['Missing PDF']}),
    'android:9999':entry('android:9999')}});
  assert.equal(cards[0].dataset.reviewState,'current');
  assert.equal(cards[1].dataset.reviewState,'stale');
  assert.equal(cards[2].dataset.reviewState,'none');
  assert.match(controls['review-status'].textContent,/1 IDs absent/);
  const panel=cards[0].querySelector('.review-panel');
  assert.match(panel.textContent,/<img src=x onerror=alert\(1\)>/);
  assert.equal(panel.children.some(c=>c.tag==='img'||c.tag==='script'),false);
  controls['review-priority'].value='high';controls['review-priority'].listeners.input();
  assert.equal(cards[0].hidden,false); assert.equal(cards[1].hidden,true);assert.equal(cards[2].hidden,true);
  controls['review-priority'].value='';controls['review-state'].value='stale';controls['review-state'].listeners.input();
  assert.equal(cards[0].hidden,true);assert.equal(cards[1].hidden,false);
  controls['review-state'].value='gaps';controls['review-state'].listeners.input();
  assert.equal(cards[1].hidden,false);
  controls.reset.listeners.click();assert.equal(cards[0].hidden,false);
  await load({schema_version:1,assessments:{'gmail:0001':entry('gmail:0001',{priority:'invented'})}});
  assert.match(controls['review-status'].textContent,/Could not load/);
  assert.equal(cards[0].querySelector('.review-panel'),panel);
  controls['review-clear'].listeners.click();
  assert.equal(cards[0].querySelector('.review-panel'),null);
  assert.equal(controls['review-priority'].disabled,true);
  assert.equal(cards[2].hidden,false);
  const finding={id:'finding:'+'e'.repeat(16),title:'Related later statement',analysis:'Context matters.',kind:'context',
    entry_ids:['gmail:0001','gmail:0002'],contextual_priority:'high',questions:['Check timing?'],
    quotes:[{source_id:'gmail:0001',text:'First statement'},{source_id:'gmail:0002',text:'Later statement'}]};
  const manifest={version:2,complete:true,criteria_hash:criteria,findings:[finding],
    entry_hashes:Object.fromEntries(cards.map(card=>[card.id,{source_hash:hash,review_hash:hash}]))};
  await load({schema_version:1,assessments:{'gmail:0001':entry('gmail:0001',{priority:'low'}),
    'gmail:0002':entry('gmail:0002',{priority:'low'})},contextual_review:manifest});
  assert.match(cards[0].querySelector('.review-panel').textContent,/contextual priority: high/);
  assert.match(cards[0].querySelector('.review-panel').textContent,/Related later statement/);
  controls['review-priority'].value='high';controls['review-priority'].listeners.input();
  assert.equal(cards[0].hidden,false);
  assert.equal(cards[1].hidden,false);
  assert.equal(cards[2].hidden,true);
  await load({schema_version:1,assessments:{'gmail:0001':entry('gmail:0001',{priority:'low'}),
    'gmail:0002':entry('gmail:0002',{priority:'low'})},
    contextual_review:{...manifest,excluded_ids:[cards[2].id]}});
  assert.match(controls['review-status'].textContent,/Partial coverage: 1 manual-review entries excluded/);
  assert.match(cards[0].querySelector('.review-panel').textContent,/Related later statement/);
  // A changed third entry invalidates contextual priorities even for unchanged linked entries.
  cards[2].dataset.reviewHash=changed;
  await load({schema_version:1,assessments:{'gmail:0001':entry('gmail:0001',{priority:'low'})},contextual_review:manifest});
  assert.match(controls['review-status'].textContent,/Second-pass findings outdated/);
  assert.doesNotMatch(cards[0].querySelector('.review-panel').textContent,/contextual priority/);
  controls['review-priority'].value='high';controls['review-priority'].listeners.input();
  assert.equal(cards[0].hidden,true);
  cards[2].dataset.reviewHash=hash;
  controls['review-clear'].listeners.click();
  assert.equal(vm.runInContext("reviewState({source_hash:'a'.repeat(64),review_hash:'a'.repeat(64),criteria_hash:'c'.repeat(64)},cards[0],'')",context),'unverified');
  assert.equal(vm.runInContext("reviewState({source_hash:'a'.repeat(64),review_hash:'a'.repeat(64),criteria_hash:'c'.repeat(64)},cards[0],'d'.repeat(64))",context),'stale');
  console.log('Review overlay tests passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
