/**
 * Client-side debounce + auto-retry tests for the WP availability toggle.
 * Tests the JavaScript logic extracted from profile_v2.html in isolation.
 *
 * Run: node test_wp_debounce.mjs
 *
 * Uses fake setTimeout/clearTimeout (no npm required) so timers are
 * controlled synchronously, and awaits microtask flush after each tick
 * to let Promise chains settle.
 */

// ── Fake clock ───────────────────────────────────────────────────────────────

let _clock = 0;
const _timers = [];
let _nextTimerId = 1;

function setTimeout(fn, delay) {
  const id = _nextTimerId++;
  _timers.push({ id, fn, at: _clock + delay });
  return id;
}

function clearTimeout(id) {
  const i = _timers.findIndex(t => t.id === id);
  if (i !== -1) _timers.splice(i, 1);
}

function tick(ms) {
  _clock += ms;
  // Fire all timers that are now due, in chronological order.
  // Iterate over a snapshot so timers added during firing don't run now.
  const due = _timers
    .filter(t => t.at <= _clock)
    .sort((a, b) => a.at - b.at);
  due.forEach(t => {
    const i = _timers.indexOf(t);
    if (i !== -1) { _timers.splice(i, 1); t.fn(); }
  });
}

// Flush the microtask queue so Promise .then() chains settle after a tick.
async function flush() {
  for (let i = 0; i < 5; i++) await Promise.resolve();
}

// ── Fake DOM ─────────────────────────────────────────────────────────────────

const _fakeEl = () => ({
  classList: { add() {}, remove() {} },
  style: {},
  textContent: '',
});
const _dom = {
  'wp-avail-icon':  _fakeEl(),
  'wp-avail-label': _fakeEl(),
  'wp-avail-btn':   _fakeEl(),
};
const document = {
  getElementById: id => _dom[id] ?? null,
  cookie: 'csrftoken=test-csrf',
};

// ── Fake window (toast spy) ───────────────────────────────────────────────────

const _toasts = [];
const window = { dasToast: (msg, color) => _toasts.push({ msg, color }) };

// ── Debounce logic (verbatim from profile_v2.html, minus the Django tags) ────
// _WP_AVAIL_DEBOUNCE_MS is set to 600 in production; tests may override it.

var _WP_AVAIL_DEBOUNCE_MS = 600;
var _WP_AVAIL_MAX_RETRIES  = 3;

var _wpAvailConfirmed = false;
var _wpAvailShown     = false;
var _wpAvailTimer     = null;
var _wpAvailInFlight  = false;

function _wpAvailSetUI(isAvail, isPending) {
  var icon  = document.getElementById('wp-avail-icon');
  var label = document.getElementById('wp-avail-label');
  var btn   = document.getElementById('wp-avail-btn');
  if (!icon || !label) return;
  if (isAvail) {
    icon.classList.remove('bg-ink-800', 'text-ink-400');
    icon.classList.add('bg-emerald-500/15', 'text-emerald-400');
    label.classList.remove('text-ink-400');
    label.classList.add('text-emerald-400');
    label.textContent = 'Müsait';
  } else {
    icon.classList.remove('bg-emerald-500/15', 'text-emerald-400');
    icon.classList.add('bg-ink-800', 'text-ink-400');
    label.classList.remove('text-emerald-400');
    label.classList.add('text-ink-400');
    label.textContent = 'Meşgul';
  }
  if (btn) {
    btn.style.opacity = isPending ? '0.55' : '';
    btn.style.cursor  = isPending ? 'wait'  : '';
  }
}

function toggleWpAvailability() {
  if (_wpAvailInFlight) return;
  _wpAvailShown = !_wpAvailShown;
  _wpAvailSetUI(_wpAvailShown, true);
  clearTimeout(_wpAvailTimer);
  _wpAvailTimer = setTimeout(function () {
    _wpAvailTimer = null;
    _wpAvailFire(_wpAvailShown);
  }, _WP_AVAIL_DEBOUNCE_MS);
}

function _wpAvailFire(desired, retries) {
  retries = retries || 0;
  _wpAvailInFlight = true;
  _wpAvailSetUI(desired, true);

  fetch('/profil/wp-availability/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '',
    },
    body: JSON.stringify({ is_available: desired }),
  })
  .then(function (r) {
    return r.json().then(function (d) { return { status: r.status, data: d }; });
  })
  .then(function (res) {
    if (res.data.ok) {
      _wpAvailInFlight = false;
      _wpAvailConfirmed = res.data.is_available;
      _wpAvailShown     = _wpAvailConfirmed;
      _wpAvailSetUI(_wpAvailConfirmed, false);
      window.dasToast && window.dasToast(
        _wpAvailConfirmed ? 'Müsait olarak isaret edildi.' : 'Mesgul olarak isaret edildi.',
        _wpAvailConfirmed ? 'emerald' : 'steel'
      );
    } else if (res.status === 429 && retries < _WP_AVAIL_MAX_RETRIES) {
      var waitMs = ((res.data.retry_after || 2) + 0.1) * 1000;
      setTimeout(function () { _wpAvailFire(desired, retries + 1); }, waitMs);
    } else {
      _wpAvailInFlight = false;
      _wpAvailShown = _wpAvailConfirmed;
      _wpAvailSetUI(_wpAvailConfirmed, false);
      window.dasToast && window.dasToast(
        res.data.error || 'Web sitesi guncellenemedi, tekrar deneyin.', 'ruby'
      );
    }
  })
  .catch(function () {
    _wpAvailInFlight = false;
    _wpAvailShown = _wpAvailConfirmed;
    _wpAvailSetUI(_wpAvailConfirmed, false);
    window.dasToast && window.dasToast('Web sitesine ulasilamadi, tekrar deneyin.', 'ruby');
  });
}

// ── Test harness ─────────────────────────────────────────────────────────────

let _fetchCalls = [];
let _fetchResponses = [];  // queue of responses to return, in order

function _mockFetch(url, opts) {
  const body = JSON.parse(opts.body);
  _fetchCalls.push({ url, is_available: body.is_available });
  const resp = _fetchResponses.shift() ?? { status: 200, data: { ok: true, is_available: body.is_available } };
  return Promise.resolve({
    status: resp.status,
    json: () => Promise.resolve(resp.data),
  });
}

function reset(initialState = false) {
  _clock = 0;
  _timers.length = 0;
  _nextTimerId = 1;
  _fetchCalls.length = 0;
  _fetchResponses.length = 0;
  _toasts.length = 0;
  _wpAvailConfirmed = initialState;
  _wpAvailShown     = initialState;
  _wpAvailTimer     = null;
  _wpAvailInFlight  = false;
}

// Temporarily replace global fetch
globalThis.fetch = _mockFetch;

let passed = 0;
let failed = 0;

function assert(cond, label, actual, expected) {
  if (cond) {
    console.log(`  PASS  ${label}`);
    passed++;
  } else {
    console.log(`  FAIL  ${label}  (got ${JSON.stringify(actual)}, expected ${JSON.stringify(expected)})`);
    failed++;
  }
}

// ── TEST 1: single click — fetch fires after 600ms, not before ───────────────

console.log('\n============================================================');
console.log('TEST 1: SINGLE CLICK — FETCH FIRES EXACTLY AT DEBOUNCE BOUNDARY');
console.log('============================================================');
reset(false);

toggleWpAvailability();

assert(_fetchCalls.length === 0, 'No fetch immediately after click', _fetchCalls.length, 0);
assert(_wpAvailShown === true,   'Visual state flips immediately',     _wpAvailShown,   true);

tick(599);
assert(_fetchCalls.length === 0, 'No fetch at t=599ms (debounce not yet fired)', _fetchCalls.length, 0);

tick(1);  // total 600ms — debounce fires
await flush();

assert(_fetchCalls.length === 1,        'Exactly 1 fetch fires at t=600ms',         _fetchCalls.length, 1);
assert(_fetchCalls[0].is_available === true, 'Fetch carries correct desired state (true)', _fetchCalls[0].is_available, true);
assert(_wpAvailConfirmed === true,      'Confirmed state updated after success',     _wpAvailConfirmed, true);
assert(!_wpAvailInFlight,               'inFlight cleared after response',           _wpAvailInFlight,  false);
assert(_toasts.length === 1 && _toasts[0].color === 'emerald', 'Success toast shown', _toasts[0]?.color, 'emerald');

// ── TEST 2: 5 rapid clicks within 600ms — only 1 fetch, final state ──────────

console.log('\n============================================================');
console.log('TEST 2: 5 RAPID CLICKS WITHIN 600ms — 1 FETCH, FINAL STATE');
console.log('============================================================');
reset(false);

// Clicks at t=0,50,100,150,200ms — each one resets the debounce
// Visual state alternates: true, false, true, false, true (final = true)
console.log('  Simulating 5 clicks at t=0,50,100,150,200ms...');
for (let i = 0; i < 5; i++) {
  tick(50);
  toggleWpAvailability();
  console.log(`    t=${_clock}ms  click ${i+1}  shown=${_wpAvailShown}  timers=${_timers.length}`);
}

assert(_fetchCalls.length === 0, 'No fetch during the 5-click burst', _fetchCalls.length, 0);
console.log(`  Final _wpAvailShown after burst: ${_wpAvailShown}  (must be true — odd clicks)`);
assert(_wpAvailShown === true, 'Optimistic UI shows final desired state (true)', _wpAvailShown, true);

// Advance past the debounce window from the last click
tick(600);
await flush();

console.log(`  Fetch calls after debounce fires: ${_fetchCalls.length}  (must be 1)`);
console.log(`  Fetch desired state: ${_fetchCalls[0]?.is_available}  (must be true — final click state)`);
assert(_fetchCalls.length === 1,             '1 fetch fired (not 5)',                     _fetchCalls.length, 1);
assert(_fetchCalls[0].is_available === true, 'Fetch carries FINAL desired state (true)',  _fetchCalls[0].is_available, true);
assert(_wpAvailConfirmed === true,           'Confirmed updated to final state',           _wpAvailConfirmed, true);

// ── TEST 3: clicks during in-flight are ignored ───────────────────────────────

console.log('\n============================================================');
console.log('TEST 3: CLICKS DURING IN-FLIGHT ARE IGNORED');
console.log('============================================================');
reset(false);

// Trigger the fetch (it will not resolve until we flush)
toggleWpAvailability();
tick(600);
// At this point _wpAvailInFlight = true, fetch promise pending

const beforeClicks = _fetchCalls.length;
// Try to click 3 more times during in-flight
toggleWpAvailability();
toggleWpAvailability();
toggleWpAvailability();

assert(_timers.filter(t => t.fn.toString().includes('_wpAvailFire')).length === 0,
  'No new debounce timers set while in-flight', null, null);
assert(_fetchCalls.length === beforeClicks, 'No extra fetches queued during in-flight', _fetchCalls.length, beforeClicks);

// Resolve the in-flight request
await flush();
assert(!_wpAvailInFlight, 'inFlight cleared after response', _wpAvailInFlight, false);
assert(_fetchCalls.length === 1, 'Still only 1 total fetch', _fetchCalls.length, 1);

// ── TEST 4: 429 auto-retry — final state eventually reaches WP ───────────────

console.log('\n============================================================');
console.log('TEST 4: 429 AUTO-RETRY — FINAL STATE EVENTUALLY REACHES WP');
console.log('============================================================');
reset(false);

// First fetch returns 429 (rate-limited)
_fetchResponses.push({
  status: 429,
  data: { ok: false, error: 'Cok hizli deneme.', retry_after: 2 },
});
// Second fetch (auto-retry) returns success
_fetchResponses.push({
  status: 200,
  data: { ok: true, is_available: true },
});

toggleWpAvailability();  // desired = true
tick(600);               // debounce fires
await flush();           // first fetch settles → 429, schedules retry at +2.1s

console.log(`  After 1st fetch (429): fetchCalls=${_fetchCalls.length}  inFlight=${_wpAvailInFlight}  shown=${_wpAvailShown}  confirmed=${_wpAvailConfirmed}`);
assert(_fetchCalls.length === 1,  '1st fetch fired',                 _fetchCalls.length, 1);
assert(_wpAvailInFlight === true, 'inFlight stays true during retry wait', _wpAvailInFlight, true);
assert(_wpAvailShown === true,    'Optimistic UI preserved (not reverted)', _wpAvailShown, true);
assert(_wpAvailConfirmed === false,'Confirmed NOT yet updated (WP not synced)', _wpAvailConfirmed, false);

// Advance past the retry_after window (2s + 0.1s buffer = 2100ms)
tick(2100);
await flush();           // retry fetch settles → success

console.log(`  After retry (success): fetchCalls=${_fetchCalls.length}  inFlight=${_wpAvailInFlight}  shown=${_wpAvailShown}  confirmed=${_wpAvailConfirmed}`);
assert(_fetchCalls.length === 2,   'Retry fired (2 total fetches)',          _fetchCalls.length, 2);
assert(_fetchCalls[1].is_available === true, 'Retry carries correct desired state', _fetchCalls[1].is_available, true);
assert(_wpAvailInFlight === false,  'inFlight cleared after retry success',   _wpAvailInFlight, false);
assert(_wpAvailConfirmed === true,  'Confirmed updated to desired state (true)', _wpAvailConfirmed, true);
assert(_wpAvailShown === true,      'Shown matches confirmed',                 _wpAvailShown, true);
assert(_toasts.length === 1 && _toasts[0].color === 'emerald', 'Success toast shown after retry', _toasts[0]?.color, 'emerald');
console.log('  Final state reached WP after 429: CONFIRMED');

// ── TEST 5: retries exhausted after max attempts → revert + error toast ───────

console.log('\n============================================================');
console.log('TEST 5: MAX RETRIES EXHAUSTED — REVERT UI, SHOW ERROR');
console.log('============================================================');
reset(false);

// All 4 attempts (1 original + 3 retries) return 429
for (let i = 0; i < 4; i++) {
  _fetchResponses.push({ status: 429, data: { ok: false, error: 'Rate limited.', retry_after: 2 } });
}

toggleWpAvailability();  // desired = true
tick(600);
await flush();  // attempt 1 → 429, schedules retry

for (let attempt = 1; attempt <= 3; attempt++) {
  tick(2100);
  await flush();
  console.log(`  After attempt ${attempt + 1}: fetchCalls=${_fetchCalls.length}  inFlight=${_wpAvailInFlight}  confirmed=${_wpAvailConfirmed}`);
}

assert(_fetchCalls.length === 4,   '4 total attempts (1 + 3 retries)',      _fetchCalls.length, 4);
assert(_wpAvailInFlight === false,  'inFlight cleared after exhaustion',     _wpAvailInFlight, false);
assert(_wpAvailConfirmed === false, 'Confirmed NOT updated (WP never synced)', _wpAvailConfirmed, false);
assert(_wpAvailShown === false,     'Shown reverted to confirmed',            _wpAvailShown, false);
assert(_toasts.length === 1 && _toasts[0].color === 'ruby', 'Error toast shown', _toasts[0]?.color, 'ruby');

// ── Summary ──────────────────────────────────────────────────────────────────

console.log('\n============================================================');
console.log(`RESULTS: ${passed} passed, ${failed} failed`);
console.log('============================================================');
process.exit(failed > 0 ? 1 : 0);
