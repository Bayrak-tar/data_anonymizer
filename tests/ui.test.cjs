const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function setup(respond) {
  const elements = new Map();
  class Element {
    constructor() {
      this.value = '';
      this.checked = false;
      this.textContent = '';
      this.innerHTML = '';
      this.handlers = {};
      this.children = [];
      const classes = new Set();
      this.classList = {
        add: name => classes.add(name), remove: name => classes.delete(name),
        contains: name => classes.has(name),
        toggle: (name, enabled) => enabled ? classes.add(name) : classes.delete(name),
      };
    }
    addEventListener(name, callback) { this.handlers[name] = callback; }
    replaceChildren() { this.children = []; }
    appendChild(child) { this.children.push(child); }
    focus() {}
    setAttribute() {}
    checkValidity() { return true; }
    reportValidity() {}
  }
  function el(selector) {
    if (!elements.has(selector)) elements.set(selector, new Element());
    return elements.get(selector);
  }
  let copied = null;
  const requests = [];
  const context = {
    document: { querySelector: el, createElement: () => new Element() },
    AbortController, setTimeout: () => {}, Blob, URL,
    navigator: { clipboard: { writeText: async text => { copied = text; } } },
    fetch: async (url, options) => {
      if (url === '/health') return { json: async () => ({model_loaded: true, authentication_required: false}) };
      requests.push(JSON.parse(options.body));
      return respond(options);
    },
  };
  vm.runInNewContext(fs.readFileSync('static/app.js', 'utf8'), context);
  return { el, requests, copied: () => copied, event: (id, name = 'click') => el(id).handlers[name]() };
}

const ok = { ok: true, text: async () => JSON.stringify({ masked_text: '😀 [MANUAL_1]', entities: [], entities_count: 1, counts_by_label: { MANUAL: 1 } }) };

test('submits original text unchanged using API defaults', async () => {
  const ui = setup(async () => ok);
  ui.el('#sourceText').value = '  😀 sır\n';
  await ui.event('#anonymizeButton');
  assert.deepEqual(ui.requests[0], { text: '  😀 sır\n' });
  assert.equal(ui.el('#downloadButton').disabled, false);
  await ui.event('#copyButton');
  assert.equal(ui.copied(), '😀 [MANUAL_1]');
  ui.el('#sourceText').value = 'new input';
  ui.event('#sourceText', 'input');
  assert.equal(ui.el('#downloadButton').disabled, true);
});

test('late responses cannot restore results after clearing', async () => {
  let resolve;
  const pending = new Promise(r => { resolve = r; });
  const ui = setup(() => pending);
  ui.el('#sourceText').value = 'sensitive';
  const request = ui.event('#anonymizeButton');
  ui.event('#clearButton');
  resolve(ok);
  await request;
  assert.equal(ui.el('#downloadButton').disabled, true);
  assert.equal(ui.el('#resultBox').classList.contains('has-result'), false);
});

test('failed requests cannot be exported', async () => {
  const ui = setup(async () => ({ok: false, status: 503, text: async () => '{"detail":"Model unavailable"}'}));
  ui.el('#sourceText').value = 'sensitive';
  await ui.event('#anonymizeButton');
  assert.equal(ui.el('#downloadButton').disabled, true);
  await ui.event('#copyButton');
  assert.equal(ui.copied(), null);
});

test('changing the API key clears the previous result', async () => {
  const ui = setup(async () => ok);
  ui.el('#sourceText').value = 'sensitive';
  await ui.event('#anonymizeButton');
  ui.el('#apiKey').value = 'new-key';
  ui.event('#apiKey', 'input');
  assert.equal(ui.el('#entityList').children.length, 0);
  assert.equal(ui.el('#downloadButton').disabled, true);
});
