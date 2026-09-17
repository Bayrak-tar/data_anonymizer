const sourceText = document.querySelector('#sourceText');
const resultBox = document.querySelector('#resultBox');
const entityList = document.querySelector('#entityList');
const charCount = document.querySelector('#charCount');
const anonymizeButton = document.querySelector('#anonymizeButton');
const clearButton = document.querySelector('#clearButton');
const copyButton = document.querySelector('#copyButton');
const downloadButton = document.querySelector('#downloadButton');
const apiKey = document.querySelector('#apiKey');
const summary = document.querySelector('#resultSummary');
let requestVersion = 0;
let controller = null;
let exportText = null;

function invalidate() {
  requestVersion++;
  controller?.abort();
  exportText = null;
  copyButton.disabled = downloadButton.disabled = true;
  entityList.replaceChildren();
  entityList.classList.remove('has-entities');
  resultBox.textContent = 'Sonuç burada görünecek...';
  resultBox.classList.remove('has-result');
  summary.textContent = '';
  anonymizeButton.disabled = false;
  anonymizeButton.textContent = 'Anonimleştir';
}

function updateCount() {
  charCount.textContent = Array.from(sourceText.value).length;
}

function setResult(text) {
  resultBox.textContent = text;
  resultBox.classList.add('has-result');
}

const entityLabels = {
  NAME: 'Kişi adı', LOCATION: 'Konum', ORGANIZATION: 'Kurum', ADDRESS: 'Adres',
  EMAIL: 'E-posta', PHONE: 'Telefon', TC: 'TC kimlik numarası', IBAN: 'IBAN',
  CREDIT_CARD: 'Kart numarası', CARD_END: 'Kart son hanesi', PLATE: 'Plaka',
  DATE: 'Tarih', TIME: 'Saat', URL: 'Bağlantı', HOSTNAME: 'Hostname',
  IP_ADDRESS: 'IP adresi', CUSTOMER_ID: 'Müşteri numarası', REGISTRY_NO: 'Sicil numarası',
  ORDER_NO: 'Sipariş numarası', MESSAGE_ID: 'Mesaj numarası', BRAND: 'Marka',
  DEVICE: 'Cihaz', SERVER: 'Sunucu', ID: 'Kayıt numarası', TRANSACTION: 'İşlem',
  STATUS: 'Durum', VALUE: 'Değer', MANUAL: 'Elle seçilen alan', SENSITIVE: 'Hassas bilgi',
};

function renderEntities(entities, originalText) {
  entityList.replaceChildren();
  entityList.classList.toggle('has-entities', entities.length > 0);
  const characters = Array.from(originalText);
  const seen = new Set();
  entities.forEach((entity) => {
    const isRepeat = seen.has(entity.placeholder);
    seen.add(entity.placeholder);
    const item = document.createElement('article');
    item.className = 'entity-item';
    const heading = document.createElement('h3');
    heading.className = 'entity-title';
    heading.textContent = entityLabels[entity.label] || entity.label;
    item.appendChild(heading);
    if (isRepeat) {
      const badge = document.createElement('span');
      badge.className = 'entity-repeat';
      badge.textContent = 'Tekrar';
      heading.appendChild(badge);
    }
    const original = characters.slice(entity.start, entity.end).join('');
    for (const [label, value, className] of [
      ['Maskelenen veri', original, 'entity-original'],
      ['Yerine yazılan', entity.placeholder, 'entity-output'],
    ]) {
      const caption = document.createElement('p');
      caption.className = 'entity-caption';
      caption.textContent = label;
      const content = document.createElement('p');
      content.className = className;
      content.textContent = value;
      item.appendChild(caption);
      item.appendChild(content);
    }
    entityList.appendChild(item);
  });
}

sourceText.addEventListener('input', () => {
  updateCount();
  invalidate();
});
apiKey.addEventListener('input', invalidate);

clearButton.addEventListener('click', () => {
  invalidate();
  apiKey.value = '';
  sourceText.value = '';
  resultBox.innerHTML = '<span>Sonuç burada görünecek...</span>';
  resultBox.classList.remove('has-result');
  entityList.innerHTML = '';
  entityList.classList.remove('has-entities');
  updateCount();
  sourceText.focus();
});

anonymizeButton.addEventListener('click', async () => {
  const text = sourceText.value;
  if (!text.trim()) {
    sourceText.focus();
    return;
  }

  invalidate();
  const version = requestVersion;
  controller = new AbortController();
  anonymizeButton.disabled = true;
  anonymizeButton.textContent = 'İşleniyor...';
  try {
    const response = await fetch('/anonymize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(apiKey.value ? { 'X-API-Key': apiKey.value } : {}) },
      signal: controller.signal,
      body: JSON.stringify({ text }),
    });
    const responseText = await response.text();
    let data;
    try {
      data = responseText ? JSON.parse(responseText) : null;
    } catch {
      data = null;
    }
    if (version !== requestVersion) return;
    if (!response.ok) {
      throw new Error(data?.detail || `Sunucu hatası (${response.status}).`);
    }
    if (!data?.masked_text) {
      throw new Error('Sunucudan geçerli bir anonimleştirme sonucu alınamadı.');
    }
    setResult(data.masked_text);
    exportText = data.masked_text;
    copyButton.disabled = downloadButton.disabled = false;
    summary.textContent = `${data.entities_count} alan maskelendi. ` +
      Object.entries(data.counts_by_label || {}).map(([label, count]) => `${label}: ${count}`).join(' · ');
    renderEntities(data.entities || [], text);
  } catch (error) {
    if (error.name === 'AbortError' || version !== requestVersion) return;
    const message = error instanceof TypeError
      ? 'Sunucuya bağlanılamadı. Uygulamanın çalıştığından emin olun.'
      : error.message;
    setResult(`Hata: ${message}`);
  } finally {
    if (version === requestVersion) {
    anonymizeButton.disabled = false;
    anonymizeButton.innerHTML = '<svg class="anonymize-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M5 20c.8-3.2 3.1-5 7-5s6.2 1.8 7 5"/><circle cx="12" cy="9" r="4.2"/><path d="M8.4 8.7h7.2M9.4 11.1c1.5.8 3.7.8 5.2 0"/><path d="m18.5 3 .5 1.5L20.5 5 19 5.5 18.5 7 18 5.5 16.5 5 18 4.5Z"/></svg> Anonimleştir';
    }
  }
});

copyButton.addEventListener('click', async () => {
  const text = exportText;
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    summary.textContent = 'Panoya kopyalanamadı. Sonucu seçip kopyalayabilir veya indirebilirsiniz.';
    return;
  }
  copyButton.classList.add('copied');
  copyButton.setAttribute('aria-label', 'Kopyalandı');
  setTimeout(() => {
    copyButton.classList.remove('copied');
    copyButton.setAttribute('aria-label', 'Sonucu kopyala');
  }, 1200);
});

downloadButton.addEventListener('click', () => {
  const text = exportText;
  if (!text) return;
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'anonimlestirilmis-metin.txt';
  link.click();
  URL.revokeObjectURL(url);
});

invalidate();
fetch('/health', { cache: 'no-store' }).then(async response => {
  const health = await response.json();
  document.querySelector('#serviceStatus').textContent = health.model_loaded ? 'Sistem hazır' : 'Model hazır değil';
  document.querySelector('#apiKeyLabel').hidden = !health.authentication_required;
}).catch(() => {
  document.querySelector('#serviceStatus').textContent = 'Sunucuya ulaşılamıyor';
});
