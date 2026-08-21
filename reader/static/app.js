const USER_ID = "default_user";

// Состояние пагинации словаря
let currentOffset = 0;
const PAGE_SIZE = 20;
let currentItems = [];
let totalMatchingItems = 0;
let debounceTimer = null;

// Функция скрытия тултипа
function hideSelectionTooltip() {
      const tooltip = document.getElementById("selectionTooltip");
      if (tooltip) tooltip.style.display = "none";
}

// Переключение табов с гарантированным снятием старых состояний
function switchTab(tabId, btn) {
      hideSelectionTooltip();

      document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));

      const targetTab = document.getElementById(tabId);
      if (targetTab) targetTab.classList.add('active');
      if (btn) btn.classList.add('active');
}

// ----------------------------------------------------
// РИДЕР И АНАЛИЗ ТЕКСТА
// ----------------------------------------------------

async function analyzeText() {
      const text = document.getElementById("inputText").value.trim();
      if (!text) return alert("Введите текст!");

      try {
            const res = await fetch("/api/analyze", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ user_id: USER_ID, text: text })
            });
            const data = await res.json();
            renderList("phrasesList", data.phrases || [], "phrase");
            renderList("wordsList", data.rare_words || [], "word");
            updateDictBadgeCount();
      } catch (e) {
            console.error("Ошибка при анализе текста:", e);
            alert("Не удалось проанализировать текст.");
      }
}

function renderList(containerId, items, type) {
      const container = document.getElementById(containerId);
      if (!items.length) {
            container.innerHTML = "<p style='color:var(--text-muted); font-style:italic;'>Ничего нового не найдено.</p>";
            return;
      }

      container.innerHTML = items.map(item => {
            let statusBadge = "";
            let cardClass = "card";

            // ✅ Правильная проверка (двойное отрицание !! или не null):
            const isTracked = item.dict_info !== null && item.dict_info !== undefined;

            const existingTrans = item.dict_info?.translation || "";
            const existingBreakdown = item.dict_info?.breakdown || "";

            const termValue = item.original || item.word || item.term || "";
            const lemmaValue = item.lemma || termValue;
            const sentenceValue = item.sentence || item.context || "";
            const safeId = escapeId(lemmaValue + "_" + termValue);

            if (isTracked) {
                  if (item.dict_info?.status === 'learning') {
                        cardClass += " in-dict-learning";
                        statusBadge = `<span class="tag tag-learning">В словаре (${item.dict_info?.seen_count || 1})</span>`;
                  } else {
                        cardClass += " in-dict-known";
                        statusBadge = `<span class="tag tag-known">✓ Выучено (${item.dict_info?.seen_count || 1})</span>`;
                  }
            } else {
                  statusBadge = `<span class="tag tag-gray">${type === 'phrase' ? 'Оборот' : (item.pos || item.lemma)}</span>`;
            }

            const hasResult = Boolean(existingTrans || existingBreakdown);

            return `
        <div class="${cardClass}" id="card-${safeId}">
            <div class="card-content">
                <div class="card-header">
                    <span class="word-title">${termValue.toUpperCase()}</span>
                    ${statusBadge}
                </div>
                <div class="context">"${sentenceValue}"</div>
                
                <div class="llm-result-box" id="box-${safeId}" style="${hasResult ? '' : 'display:none;'}">
                    <div class="translation-text" id="trans-${safeId}">${existingTrans ? '🇷🇺 ' + existingTrans : ''}</div>
                    <div class="breakdown-text" id="break-${safeId}" style="${existingBreakdown ? '' : 'display:none;'}">
                        ${existingBreakdown ? '🧩 <strong>Состав:</strong> ' + existingBreakdown : ''}
                    </div>
                </div>
            </div>
            <div class="btn-group">
                <button class="btn btn-translate" onclick="explainItem('${escapeJs(termValue)}', '${escapeJs(lemmaValue)}', '${escapeJs(sentenceValue)}', '${safeId}', '${type}')">🌐 Разбор LLM</button>
                <button class="btn ${isTracked ? 'btn-known' : 'btn-learn'}" onclick="saveWord('${type}', '${escapeJs(termValue)}', '${escapeJs(lemmaValue)}', '${escapeJs(sentenceValue)}', 'learning', '${safeId}', this)">
                    ${isTracked ? 'В словарь (учу)' : '➕ В словарь'}
                </button>
                <button class="btn btn-known" onclick="saveWord('${type}', '${escapeJs(termValue)}', '${escapeJs(lemmaValue)}', '${escapeJs(sentenceValue)}', 'known', '${safeId}', this)">✓ Знаю</button>
            </div>
        </div>`;
      }).join("");
}

async function explainItem(term, lemma, sentence, safeId, itemType) {
      const boxDiv = document.getElementById("box-" + safeId);
      const transDiv = document.getElementById("trans-" + safeId);
      const breakDiv = document.getElementById("break-" + safeId);
      const lang = document.getElementById("readerLanguage") ? document.getElementById("readerLanguage").value : "es";

      if (boxDiv) boxDiv.style.display = "flex";
      if (transDiv) transDiv.innerText = "⏳ Разбираем...";
      if (breakDiv) breakDiv.style.display = "none";

      try {
            const res = await fetch("/api/explain", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                        text: term,           // <-- передаем именно параметр term
                        sentence: sentence || "",
                        lemma: lemma || term,
                        item_type: itemType || "word",
                        language: lang
                  })
            });
            const data = await res.json();

            const translation = data.translation || "Перевод не найден";
            if (transDiv) {
                  transDiv.innerText = "🇷🇺 " + translation;
                  transDiv.dataset.translation = translation;
            }

            if (data.breakdown && breakDiv) {
                  breakDiv.innerHTML = "🧩 <strong>Состав:</strong> " + data.breakdown;
                  breakDiv.dataset.breakdown = data.breakdown;
                  breakDiv.style.display = "block";
            }
      } catch (e) {
            if (transDiv) transDiv.innerText = "Ошибка разбора";
            console.error(e);
      }
}
async function saveWord(type, term, lemma, sentence, status, safeId, btnElement) {
      if (btnElement) {
            btnElement.disabled = true;
            btnElement.innerText = "⏳...";
      }

      const transDiv = document.getElementById("trans-" + safeId);
      const breakDiv = document.getElementById("break-" + safeId);
      const lang = document.getElementById("readerLanguage").value;
      const source = getActiveReaderSource();
      localStorage.setItem("last_selected_source", source);

      const translation = transDiv ? (transDiv.dataset.translation || transDiv.innerText.replace('🇷🇺 ', '').replace('⏳ Разбираем...', '')) : "";
      const breakdown = breakDiv ? (breakDiv.dataset.breakdown || breakDiv.innerText.replace('🧩 Состав: ', '')) : "";

      try {
            await fetch("/api/vocab/save", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                        user_id: USER_ID,
                        item_type: type,
                        term: term,
                        lemma: lemma,
                        context_sentence: sentence,
                        status: status,
                        translation: translation,
                        breakdown: breakdown,
                        source: source,
                        language: lang
                  })
            });

            const card = document.getElementById("card-" + safeId);
            if (card) {
                  card.classList.toggle('in-dict-known', status === 'known');
                  card.classList.toggle('in-dict-learning', status === 'learning');
            }

            if (btnElement) {
                  btnElement.disabled = false;
                  btnElement.innerText = status === 'known' ? "✓ Выучено" : "✓ В словаре!";
                  setTimeout(() => {
                        btnElement.innerText = status === 'known' ? "✓ Знаю" : "➕ В словарь";
                  }, 2000);
            }
            updateDictBadgeCount();
      } catch (e) {
            console.error(e);
            if (btnElement) btnElement.disabled = false;
      }
}

// ----------------------------------------------------
// СЛОВАРЬ И ПАГИНАЦИЯ
// ----------------------------------------------------

async function loadVocabulary(reset = true) {
      if (reset) {
            currentOffset = 0;
            currentItems = [];
      }

      const lang = document.getElementById("filterLanguage").value;
      const source = document.getElementById("filterSource").value;
      const search = document.getElementById("filterInput").value.trim();

      let url = `/api/vocab/${USER_ID}?limit=${PAGE_SIZE}&offset=${currentOffset}`;
      if (lang !== "all") url += `&language=${encodeURIComponent(lang)}`;
      if (source !== "all") url += `&source=${encodeURIComponent(source)}`;
      if (search) url += `&search=${encodeURIComponent(search)}`;

      try {
            const res = await fetch(url);
            const data = await res.json();

            totalMatchingItems = data.total;
            document.getElementById("dictCount").innerText = data.total;

            if (reset) {
                  currentItems = data.items;
                  updateSourceDropdown(data.sources || []);
            } else {
                  currentItems = [...currentItems, ...data.items];
            }

            renderVocabTable(currentItems);
            updatePaginationControls(data.has_more);
      } catch (e) {
            console.error("Ошибка загрузки словаря:", e);
      }
}

function handleFilterChange() {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
            loadVocabulary(true);
      }, 250);
}

function loadNextPage() {
      currentOffset += PAGE_SIZE;
      loadVocabulary(false);
}

function updatePaginationControls(hasMore) {
      const container = document.getElementById("loadMoreContainer");
      const countInfo = document.getElementById("loadedCountInfo");

      if (!container || !countInfo) return;

      if (hasMore) {
            container.style.display = "block";
            countInfo.innerText = `${currentItems.length} из ${totalMatchingItems}`;
      } else {
            container.style.display = "none";
      }
}

function updateSourceDropdown(sources) {
      const select = document.getElementById("filterSource");
      if (!select) return;
      const currentSelected = select.value;

      let html = '<option value="all">📚 Все источники</option>';
      sources.forEach(src => {
            const isSelected = (src === currentSelected) ? 'selected' : '';
            html += `<option value="${src}" ${isSelected}>${src}</option>`;
      });
      select.innerHTML = html;
}

function renderVocabTable(items) {
      const tbody = document.getElementById("vocabTableBody");
      if (!tbody) return;

      if (!items.length) {
            tbody.innerHTML = "<tr><td colspan='7' style='text-align:center; color:var(--text-muted); padding:20px;'>Ничего не найдено</td></tr>";
            return;
      }

      tbody.innerHTML = items.map(item => {
            const contextsHtml = (item.contexts || []).slice(0, 3).map(c => `<li>"${c}"</li>`).join("");
            const langBadge = item.language === 'en' ? '🇬🇧 EN' : '🇪🇸 ES';

            return `
        <tr id="row-${item.id}">
            <td><strong>${langBadge}</strong></td>
            <td><span class="tag ${item.item_type === 'phrase' ? 'tag-learning' : 'tag-gray'}">${item.item_type === 'phrase' ? 'Оборот' : 'Слово'}</span></td>
            <td class="vocab-word-block">
                <strong>${item.lemma}</strong> <small>(${item.term})</small>
                <div style="font-size: 11px; color: var(--text-muted); margin-top:2px;">📖 <em>${item.source || 'Общее'}</em></div>
                ${item.translation ? `<div class="vocab-translation">🇷🇺 ${item.translation}</div>` : ''}
                ${item.breakdown ? `<div class="vocab-breakdown">🧩 ${item.breakdown}</div>` : ''}
            </td>
            <td><ol class="context-list">${contextsHtml}</ol></td>
            <td><strong>${item.seen_count}</strong> раз(а)</td>
            <td>
                <select onchange="updateStatus(${item.id}, this.value)" style="padding:4px 6px; font-size:12px;">
                    <option value="learning" ${item.status === 'learning' ? 'selected' : ''}>🟡 Учу</option>
                    <option value="known" ${item.status === 'known' ? 'selected' : ''}>🟢 Знаю</option>
                </select>
            </td>
            <td><button class="btn btn-del" onclick="deleteItem(${item.id})">✕</button></td>
        </tr>`;
      }).join("");
}

async function updateStatus(id, newStatus) {
      await fetch(`/api/vocab/${id}/status?status=${newStatus}`, { method: "PATCH" });
      const item = currentItems.find(i => i.id === id);
      if (item) item.status = newStatus;
}

async function deleteItem(id) {
      if (!confirm("Удалить из словаря?")) return;
      await fetch(`/api/vocab/${id}`, { method: "DELETE" });
      currentItems = currentItems.filter(i => i.id !== id);
      renderVocabTable(currentItems);
      updateDictBadgeCount();
}

async function updateDictBadgeCount() {
      try {
            const res = await fetch(`/api/vocab/${USER_ID}?limit=1&offset=0`);
            const data = await res.json();
            document.getElementById("dictCount").innerText = data.total || 0;
      } catch (e) {
            console.error(e);
      }
}

function escapeJs(str) { return (str || '').replace(/'/g, "\\'").replace(/"/g, '&quot;'); }
function escapeId(str) { return encodeURIComponent(str).replace(/%/g, '_'); }

// Инициализация при открытии страницы
document.addEventListener("DOMContentLoaded", () => {
      updateDictBadgeCount();
});

// Загрузка источников из БД в ридер и фильтр словаря
async function loadSourcesList() {
      try {
            const res = await fetch(`/api/sources/${USER_ID}`);
            const data = await res.json();
            const sources = data.sources || [];

            // 1. Заполняем селектор в панели чтения
            const select = document.getElementById("readerSourceSelect");
            if (select) {
                  const savedSource = localStorage.getItem("last_selected_source") || "Общее";
                  let html = '<option value="Общее">Общее</option>';
                  sources.forEach(src => {
                        if (src !== "Общее") {
                              html += `<option value="${src}">${src}</option>`;
                        }
                  });
                  select.innerHTML = html;

                  if (sources.includes(savedSource) || savedSource === "Общее") {
                        select.value = savedSource;
                  }
            }

            // 2. Обновляем селектор в фильтре словаря
            updateSourceDropdown(sources);
      } catch (e) {
            console.error("Ошибка загрузки источников:", e);
      }
}

// Получение актуального источника перед сохранением
function getActiveReaderSource() {
      const input = document.getElementById("readerSourceInput");
      const select = document.getElementById("readerSourceSelect");

      if (input && input.style.display !== "none" && input.value.trim()) {
            return input.value.trim();
      }
      return select ? select.value : "Общее";
}

// Переключение между выбором из списка и вводом новой книги
function toggleNewSourceMode() {
      const input = document.getElementById("readerSourceInput");
      const select = document.getElementById("readerSourceSelect");
      const btn = document.getElementById("btnToggleNewSource");

      if (input.style.display === "none") {
            input.style.display = "inline-block";
            select.style.display = "none";
            btn.innerText = "✕ Выбрать из списка";
            input.focus();
      } else {
            input.style.display = "none";
            select.style.display = "inline-block";
            btn.innerText = "+ Новая книга";
      }
}

function onReaderSourceSelectChange() {
      const val = document.getElementById("readerSourceSelect").value;
      localStorage.setItem("last_selected_source", val);
}

function onLanguageChange() {
      const val = document.getElementById("readerLanguage").value;
      localStorage.setItem("last_selected_lang", val);
}

// ----------------------------------------------------
// ИНИЦИАЛИЗАЦИЯ ПРИ СТАРТЕ
// ----------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
      // Восстанавливаем ранее выбранный язык
      const savedLang = localStorage.getItem("last_selected_lang");
      if (savedLang) {
            const langEl = document.getElementById("readerLanguage");
            if (langEl) langEl.value = savedLang;
      }

      // Подгружаем сохраненные источники и счетчик слов
      loadSourcesList();
      updateDictBadgeCount();
});


let currentSelectedText = "";
let currentSelectedSentence = "";

// Переключение режимов отображения
function setReaderMode(mode) {
      hideSelectionTooltip();

      const inputArea = document.getElementById("inputText");
      const readModeContainer = document.getElementById("readModeContainer");
      const readArea = document.getElementById("readArea");
      const btnEdit = document.getElementById("btnModeEdit");
      const btnRead = document.getElementById("btnModeRead");

      const rawText = inputArea.value.trim();

      if (mode === 'read') {
            if (!rawText) {
                  alert("Сначала вставьте текст для чтения!");
                  return;
            }

            readArea.innerHTML = rawText
                  .split(/\n\s*\n/)
                  .map(p => `<p style="margin-bottom: 1.2em; line-height: 1.8;">${p.replace(/\n/g, "<br>")}</p>`)
                  .join("");

            inputArea.style.display = "none";
            readModeContainer.style.display = "block"; // Показываем читалку и контейнер ручных карточек

            btnEdit.classList.remove("active");
            btnRead.classList.add("active");
      } else {
            readModeContainer.style.display = "none";  // Скрываем читалку и ручные карточки
            inputArea.style.display = "block";

            btnRead.classList.remove("active");
            btnEdit.classList.add("active");
      }
}

// Добавление карточки при выделении
async function handleManualSelection() {
      hideSelectionTooltip();

      const term = currentSelectedText;
      const sentence = currentSelectedSentence;
      if (!term) return;

      const isPhrase = term.includes(" ");
      const itemType = isPhrase ? "phrase" : "word";

      // Открываем блок ручных карточек в читалке
      const manualSection = document.getElementById("manualSection");
      if (manualSection) manualSection.style.display = "block";

      const container = document.getElementById("manualList");
      const safeId = escapeId("manual_" + term + "_" + Date.now());

      const cardHtml = `
    <div class="card" id="card-${safeId}" style="border-left: 4px solid var(--primary);">
        <div class="card-content">
            <div class="card-header">
                <span class="word-title">${term.toUpperCase()}</span>
                <span class="tag tag-gray">${isPhrase ? 'Фраза (выбор)' : 'Слово (выбор)'}</span>
            </div>
            <div class="context">"${sentence}"</div>
            
            <div class="llm-result-box" id="box-${safeId}" style="display: flex;">
                <div class="translation-text" id="trans-${safeId}">⏳ Разбираем...</div>
                <div class="breakdown-text" id="break-${safeId}" style="display:none;"></div>
            </div>
        </div>
        <div class="btn-group">
            <button class="btn btn-learn" onclick="saveWord('${itemType}', '${escapeJs(term)}', '${escapeJs(term)}', '${escapeJs(sentence)}', 'learning', '${safeId}', this)">
                ➕ В словарь
            </button>
            <button class="btn btn-known" onclick="saveWord('${itemType}', '${escapeJs(term)}', '${escapeJs(term)}', '${escapeJs(sentence)}', 'known', '${safeId}', this)">
                ✓ Знаю
            </button>
        </div>
    </div>`;

      container.insertAdjacentHTML("afterbegin", cardHtml);
      explainItem(term, term, sentence, safeId, itemType);
}
// Скрываем тултип сразу при начале любого клика вне самого тултипа
document.addEventListener("mousedown", (e) => {
      if (!e.target.closest("#selectionTooltip")) {
            hideSelectionTooltip();
      }
});
// Отслеживание выделения ТОЛЬКО в блоке комфортного чтения (#readArea)
document.addEventListener("mouseup", (e) => {
      const tooltip = document.getElementById("selectionTooltip");
      if (!tooltip) return;

      if (e.target.closest("#selectionTooltip")) return;

      // Работает только если пользователь выделяет текст в режиме читалки
      const readArea = document.getElementById("readArea");
      if (!readArea || readArea.style.display === "none" || !readArea.contains(e.target)) {
            hideSelectionTooltip();
            return;
      }

      const selection = window.getSelection();
      const text = selection.toString().trim();

      if (text.length >= 2 && text.length <= 120) {
            currentSelectedText = text;
            currentSelectedSentence = extractSurroundingSentence(selection, text);

            const range = selection.getRangeAt(0);
            const rect = range.getBoundingClientRect();

            tooltip.style.display = "block";
            tooltip.style.top = `${window.scrollY + rect.top - 42}px`;
            tooltip.style.left = `${window.scrollX + rect.left + (rect.width / 2) - 65}px`;
      } else {
            hideSelectionTooltip();
      }
});

// Достаем предложение целиком из контекста узла
function extractSurroundingSentence(selection, term) {
      try {
            const anchorNode = selection.anchorNode;
            if (!anchorNode) return term;
            const fullNodeText = anchorNode.textContent || "";

            // Ищем границы предложения по знакам завершения (. ! ? \n)
            const sentences = fullNodeText.match(/[^.!?\n]+[.!?]?/g) || [fullNodeText];
            const matchedSentence = sentences.find(s => s.includes(term));
            return (matchedSentence ? matchedSentence.trim() : term);
      } catch {
            return term;
      }
}

