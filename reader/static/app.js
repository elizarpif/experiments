// ====================================================
// АВТОРИЗАЦИЯ И СОСТОЯНИЕ
// ====================================================

let authToken = sessionStorage.getItem("auth_token") || null;
let currentUsername = sessionStorage.getItem("auth_user") || null;
let isRegisterMode = false;

// Универсальная обертка для fetch с авторизацией
async function apiFetch(url, options = {}) {
      options.headers = options.headers || {};
      if (authToken) {
            options.headers["Authorization"] = `Bearer ${authToken}`;
      }

      // Вызываем нативный fetch браузера
      const res = await fetch(url, options);

      if (res.status === 401) {
            logout();
            throw new Error("Требуется авторизация");
      }
      return res;
}

function checkAuthUI() {
      const modal = document.getElementById("authModal");
      const userLabel = document.getElementById("displayUsername");
      const authBtn = document.getElementById("btnAuthAction");
      const btnSettings = document.getElementById("btnSettings");
      if (btnSettings) {
            btnSettings.style.display = (authToken && currentUsername) ? "inline-block" : "none";
      }

      if (authToken && currentUsername) {
            if (modal) modal.style.display = "none";
            if (userLabel) userLabel.innerText = `👤 ${currentUsername}`;
            if (authBtn) authBtn.innerText = "Выйти";
      } else {
            if (modal) modal.style.display = "flex";
            if (userLabel) userLabel.innerText = "";
            if (authBtn) authBtn.innerText = "Войти";
      }
}

function toggleAuthMode() {
      isRegisterMode = !isRegisterMode;
      const title = document.getElementById("authModalTitle");
      const btnSubmit = document.getElementById("btnSubmitAuth");
      const btnToggle = document.getElementById("btnToggleAuthMode");

      if (title) title.innerText = isRegisterMode ? "Регистрация" : "Вход в аккаунт";
      if (btnSubmit) btnSubmit.innerText = isRegisterMode ? "Зарегистрироваться" : "Войти";
      if (btnToggle) btnToggle.innerText = isRegisterMode ? "Уже есть аккаунт? Войти" : "Создать новый аккаунт";
}

async function submitAuthForm() {
      const usernameInput = document.getElementById("authLogin");
      const passwordInput = document.getElementById("authPassword");

      const username = usernameInput ? usernameInput.value.trim() : "";
      const password = passwordInput ? passwordInput.value.trim() : "";

      if (!username || !password) return alert("Заполните логин и пароль!");

      try {
            let res;
            if (isRegisterMode) {
                  res = await fetch("/api/auth/register", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ username, password })
                  });
            } else {
                  const formData = new URLSearchParams();
                  formData.append("username", username);
                  formData.append("password", password);
                  res = await fetch("/api/auth/login", {
                        method: "POST",
                        headers: { "Content-Type": "application/x-www-form-urlencoded" },
                        body: formData
                  });
            }

            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Ошибка авторизации");

            authToken = data.access_token;
            currentUsername = data.username || username;
            sessionStorage.setItem("auth_token", authToken);
            sessionStorage.setItem("auth_user", currentUsername);

            checkAuthUI();
            loadSourcesList();
            updateDictBadgeCount();
      } catch (e) {
            alert(e.message);
      }
}

function logout() {
      authToken = null;
      currentUsername = null;
      sessionStorage.removeItem("auth_token");
      sessionStorage.removeItem("auth_user");

      // Сбрасываем таблицы и счетчики
      const tbody = document.getElementById("vocabTableBody");
      if (tbody) tbody.innerHTML = "";

      const countEl = document.getElementById("dictCount");
      if (countEl) countEl.innerText = "0";

      const phrasesList = document.getElementById("phrasesList");
      if (phrasesList) phrasesList.innerHTML = "";

      const wordsList = document.getElementById("wordsList");
      if (wordsList) wordsList.innerHTML = "";

      checkAuthUI();

      // Перезагружаем страницу, чтобы полностью обнулить состояние в памяти
      window.location.reload();
}

function handleAuthButtonClick() {
      if (authToken) {
            logout();
      } else {
            const modal = document.getElementById("authModal");
            if (modal) modal.style.display = "flex";
      }
}


// ====================================================
// РИДЕР, ВЫДЕЛЕНИЕ И АНАЛИЗ
// ====================================================

let currentSelectedText = "";
let currentSelectedSentence = "";

function hideSelectionTooltip() {
      const tooltip = document.getElementById("selectionTooltip");
      if (tooltip) tooltip.style.display = "none";
}

function switchTab(tabId, btn) {
      hideSelectionTooltip();

      document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));

      const targetTab = document.getElementById(tabId);
      if (targetTab) targetTab.classList.add('active');
      if (btn) btn.classList.add('active');
}

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
            if (readModeContainer) readModeContainer.style.display = "block";

            if (btnEdit) btnEdit.classList.remove("active");
            if (btnRead) btnRead.classList.add("active");
      } else {
            if (readModeContainer) readModeContainer.style.display = "none";
            inputArea.style.display = "block";

            if (btnRead) btnRead.classList.remove("active");
            if (btnEdit) btnEdit.classList.add("active");
      }
}

async function analyzeText() {
      const text = document.getElementById("inputText").value.trim();
      if (!text) return alert("Введите текст!");

      const lang = document.getElementById("readerLanguage") ? document.getElementById("readerLanguage").value : "es";

      try {
            const res = await apiFetch("/api/analyze", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                        text: text,
                        language: lang
                  })
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
      if (!container) return;

      if (!items.length) {
            container.innerHTML = "<p style='color:var(--text-muted); font-style:italic;'>Ничего нового не найдено.</p>";
            return;
      }

      container.innerHTML = items.map(item => {
            let statusBadge = "";
            let cardClass = "card";

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
            const res = await apiFetch("/api/explain", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                        text: term,
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
      const lang = document.getElementById("readerLanguage") ? document.getElementById("readerLanguage").value : "es";
      const source = getActiveReaderSource();
      localStorage.setItem("last_selected_source", source);

      const translation = transDiv ? (transDiv.dataset.translation || transDiv.innerText.replace('🇷🇺 ', '').replace('⏳ Разбираем...', '')) : "";
      const breakdown = breakDiv ? (breakDiv.dataset.breakdown || breakDiv.innerText.replace('🧩 Состав: ', '')) : "";

      try {
            await apiFetch("/api/vocab/save", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                        user_id: currentUsername,
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

async function handleManualSelection() {
      hideSelectionTooltip();

      const term = currentSelectedText;
      const sentence = currentSelectedSentence;
      if (!term) return;

      const isPhrase = term.includes(" ");
      const itemType = isPhrase ? "phrase" : "word";

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

      if (container) container.insertAdjacentHTML("afterbegin", cardHtml);
      explainItem(term, term, sentence, safeId, itemType);
}

// Слушатели мыши для всплывающей кнопки
document.addEventListener("mousedown", (e) => {
      if (!e.target.closest("#selectionTooltip")) {
            hideSelectionTooltip();
      }
});

document.addEventListener("mouseup", (e) => {
      const tooltip = document.getElementById("selectionTooltip");
      if (!tooltip) return;

      if (e.target.closest("#selectionTooltip")) return;

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

function extractSurroundingSentence(selection, term) {
      try {
            const anchorNode = selection.anchorNode;
            if (!anchorNode) return term;
            const fullNodeText = anchorNode.textContent || "";
            const sentences = fullNodeText.match(/[^.!?\n]+[.!?]?/g) || [fullNodeText];
            const matchedSentence = sentences.find(s => s.includes(term));
            return (matchedSentence ? matchedSentence.trim() : term);
      } catch {
            return term;
      }
}


// ====================================================
// СЛОВАРЬ И ПАГИНАЦИЯ
// ====================================================

let currentOffset = 0;
const PAGE_SIZE = 20;
let currentItems = [];
let totalMatchingItems = 0;
let debounceTimer = null;

async function loadVocabulary(reset = true) {
      if (!authToken || !currentUsername) return;

      if (reset) {
            currentOffset = 0;
            currentItems = [];
      }

      const lang = document.getElementById("filterLanguage") ? document.getElementById("filterLanguage").value : "all";
      const source = document.getElementById("filterSource") ? document.getElementById("filterSource").value : "all";
      const search = document.getElementById("filterInput") ? document.getElementById("filterInput").value.trim() : "";

      let url = `/api/vocab/${encodeURIComponent(currentUsername)}?limit=${PAGE_SIZE}&offset=${currentOffset}`;
      if (lang !== "all") url += `&language=${encodeURIComponent(lang)}`;
      if (source !== "all") url += `&source=${encodeURIComponent(source)}`;
      if (search) url += `&search=${encodeURIComponent(search)}`;

      try {
            const res = await apiFetch(url);
            const data = await res.json();

            totalMatchingItems = data.total;
            const dictCountEl = document.getElementById("dictCount");
            if (dictCountEl) dictCountEl.innerText = data.total;

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
      await apiFetch(`/api/vocab/${id}/status?status=${newStatus}`, { method: "PATCH" });
      const item = currentItems.find(i => i.id === id);
      if (item) item.status = newStatus;
}

async function deleteItem(id) {
      if (!confirm("Удалить из словаря?")) return;
      await apiFetch(`/api/vocab/${id}`, { method: "DELETE" });
      currentItems = currentItems.filter(i => i.id !== id);
      renderVocabTable(currentItems);
      updateDictBadgeCount();
}

async function updateDictBadgeCount() {
      if (!authToken || !currentUsername) return;
      try {
            const res = await apiFetch(`/api/vocab/${encodeURIComponent(currentUsername)}?limit=1&offset=0`);
            const data = await res.json();
            const dictCountEl = document.getElementById("dictCount");
            if (dictCountEl) dictCountEl.innerText = data.total || 0;
      } catch (e) {
            console.error(e);
      }
}

async function loadSourcesList() {
      if (!authToken || !currentUsername) return;
      try {
            const res = await apiFetch(`/api/sources/${encodeURIComponent(currentUsername)}`);
            const data = await res.json();
            const sources = data.sources || [];

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

            updateSourceDropdown(sources);
      } catch (e) {
            console.error("Ошибка загрузки источников:", e);
      }
}

function getActiveReaderSource() {
      const input = document.getElementById("readerSourceInput");
      const select = document.getElementById("readerSourceSelect");

      if (input && input.style.display !== "none" && input.value.trim()) {
            return input.value.trim();
      }
      return select ? select.value : "Общее";
}

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

function escapeJs(str) { return (str || '').replace(/'/g, "\\'").replace(/"/g, '&quot;'); }
function escapeId(str) { return encodeURIComponent(str).replace(/%/g, '_'); }


// ====================================================
// ЕДИНАЯ ТОЧКА СТАРТА ПРИЛОЖЕНИЯ
// ====================================================

document.addEventListener("DOMContentLoaded", () => {
      checkAuthUI();

      const savedLang = localStorage.getItem("last_selected_lang");
      if (savedLang) {
            const langEl = document.getElementById("readerLanguage");
            if (langEl) langEl.value = savedLang;
      }

      if (authToken && currentUsername) {
            loadSourcesList();
            updateDictBadgeCount();
      }
});

// modal for gemini key

function openApiKeyModal() {
      const modal = document.getElementById("apiKeyModal");
      if (modal) {
            modal.style.display = "flex";
            document.getElementById("inputApiKey").value = "";
            document.getElementById("inputApiKey").focus();
      }
}

function closeApiKeyModal() {
      const modal = document.getElementById("apiKeyModal");
      if (modal) {
            modal.style.display = "none";
            document.getElementById("inputApiKey").value = "";
      }
}

async function saveApiKey() {
      const keyInput = document.getElementById("inputApiKey");
      const key = keyInput ? keyInput.value.trim() : "";
      if (!key) return alert("Введите ключ!");

      try {
            const res = await apiFetch("/api/auth/api-key", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ api_key: key })
            });

            if (!res.ok) {
                  const err = await res.json();
                  throw new Error(err.detail || "Ошибка сохранения");
            }

            const data = await res.json();
            alert(data.message || "Ключ успешно сохранен!");
            closeApiKeyModal();
      } catch (e) {
            alert(e.message);
      }
}