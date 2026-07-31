/* ============================================================
   Curator — Single-Page Application
   ============================================================ */

const API = '/api';

// ---- State ----
const State = {
    currentPage: 'dashboard',
    items: [],
    stats: null,
    filters: { item_type: '', source: '', difficulty: '', language: '', tags: '', q: '' },
    currentItem: null,
    duplicates: [],
    settings: null,
    searchTimeout: null,
};

// ---- API Client ----
const Api = {
    async get(path) {
        const resp = await fetch(`${API}${path}`);
        if (!resp.ok) throw new Error(`GET ${path}: ${resp.status}`);
        return resp.json();
    },
    async post(path, body) {
        const resp = await fetch(`${API}${path}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `POST ${path}: ${resp.status}`);
        }
        return resp.json();
    },
    async put(path, body) {
        const resp = await fetch(`${API}${path}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!resp.ok) throw new Error(`PUT ${path}: ${resp.status}`);
        return resp.json();
    },
    async del(path) {
        const resp = await fetch(`${API}${path}`, { method: 'DELETE' });
        if (!resp.ok) throw new Error(`DELETE ${path}: ${resp.status}`);
    },
    async upload(path, file) {
        const form = new FormData();
        form.append('file', file);
        const resp = await fetch(`${API}${path}`, { method: 'POST', body: form });
        if (!resp.ok) throw new Error(`Upload ${path}: ${resp.status}`);
        return resp.json();
    },
};

// ---- Toast ----
function toast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    const icons = { success: '✓', error: '✗', info: 'ℹ' };
    el.textContent = `${icons[type] || ''} ${message}`;
    container.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, 3000);
}

// ---- Router ----
function navigate(page, data) {
    State.currentPage = page;
    document.querySelectorAll('.nav-link').forEach(l => {
        l.classList.toggle('active', l.dataset.page === page);
    });
    renderPage(page, data);
}

window.addEventListener('hashchange', () => {
    const hash = location.hash.slice(2) || 'dashboard';
    const parts = hash.split('/');
    if (parts[0] === 'item' && parts[1]) {
        navigate('item-detail', { id: parseInt(parts[1]) });
    } else {
        navigate(parts[0] || 'dashboard');
    }
});

// ---- Page Renderer ----
async function renderPage(page, data) {
    const container = document.getElementById('page-container');
    container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

    try {
        switch (page) {
            case 'dashboard': await renderDashboard(container); break;
            case 'browse': await renderBrowse(container); break;
            case 'item-detail': await renderItemDetail(container, data.id); break;
            case 'duplicates': await renderDuplicates(container); break;
            case 'import': await renderImportExport(container); break;
            case 'settings': await renderSettings(container); break;
            default: container.innerHTML = '<div class="empty-state"><h3>Page not found</h3></div>';
        }
    } catch (err) {
        container.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠️</div><h3>Error</h3><p>${err.message}</p></div>`;
    }
}

// ---- Dashboard ----
async function renderDashboard(el) {
    const stats = await Api.get('/settings/stats');
    State.stats = stats;

    // Update duplicate badge
    const badge = document.getElementById('dup-badge');
    if (stats.pending_duplicates > 0) {
        badge.textContent = stats.pending_duplicates;
        badge.classList.remove('hidden');
    } else {
        badge.classList.add('hidden');
    }

    el.innerHTML = `
        <div class="page-header"><h1>Dashboard</h1></div>
        <div class="stats-grid">
            <div class="stat-card"><div class="stat-value">${stats.total_items}</div><div class="stat-label">Total Items</div></div>
            <div class="stat-card"><div class="stat-value">${stats.total_tags}</div><div class="stat-label">Unique Tags</div></div>
            <div class="stat-card"><div class="stat-value">${stats.has_embeddings}</div><div class="stat-label">With Embeddings</div></div>
            <div class="stat-card"><div class="stat-value">${stats.pending_duplicates}</div><div class="stat-label">Pending Duplicates</div></div>
        </div>

        ${Object.keys(stats.by_type).length > 0 ? `
        <div class="stats-grid">
            ${Object.entries(stats.by_type).map(([t, c]) => `
                <div class="stat-card" style="cursor:pointer" onclick="location.hash='#/browse';setTimeout(()=>{const s=document.getElementById('filter-type');if(s){s.value='${t}';s.dispatchEvent(new Event('change'))}},100)">
                    <div class="stat-value" style="font-size:1.5rem">${c}</div>
                    <div class="stat-label">${t}</div>
                </div>
            `).join('')}
        </div>` : ''}

        <h2 style="font-size:1.1rem;margin-bottom:16px;color:var(--text-secondary)">Recent Items</h2>
        <div class="items-grid">
            ${stats.recent_items.length === 0 ? '<div class="empty-state"><div class="empty-state-icon">📭</div><h3>No items yet</h3><p>Add your first item using the + button or import from GitHub/Safari.</p></div>' : ''}
            ${stats.recent_items.map(renderItemCard).join('')}
        </div>
    `;
}

// ---- Browse ----
async function renderBrowse(el) {
    el.innerHTML = `
        <div class="page-header"><h1>Browse</h1></div>
        <div class="search-container">
            <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input type="text" class="search-input" id="search-input" placeholder="Search by meaning, keywords, or tags..." value="${State.filters.q}">
        </div>
        <div class="filters" id="filters-bar">
            <select class="filter-select" id="filter-type"><option value="">All Types</option>
                <option value="repo">Repo</option><option value="website">Website</option><option value="blog">Blog</option>
                <option value="course">Course</option><option value="textbook">Textbook</option><option value="document">Document</option>
                <option value="note">Note</option><option value="snippet">Snippet</option>
            </select>
            <select class="filter-select" id="filter-source"><option value="">All Sources</option>
                <option value="github">GitHub</option><option value="safari">Safari</option>
                <option value="manual">Manual</option><option value="import">Import</option>
            </select>
            <select class="filter-select" id="filter-difficulty"><option value="">Any Difficulty</option>
                <option value="beginner">Beginner</option><option value="intermediate">Intermediate</option><option value="advanced">Advanced</option>
            </select>
        </div>
        <div id="browse-results"><div class="loading"><div class="spinner"></div></div></div>
        <div id="browse-pagination" class="flex justify-between items-center mt-4"></div>
    `;

    // Restore filters
    if (State.filters.item_type) document.getElementById('filter-type').value = State.filters.item_type;
    if (State.filters.source) document.getElementById('filter-source').value = State.filters.source;
    if (State.filters.difficulty) document.getElementById('filter-difficulty').value = State.filters.difficulty;

    // Wire events
    const searchInput = document.getElementById('search-input');
    searchInput.addEventListener('input', () => {
        clearTimeout(State.searchTimeout);
        State.searchTimeout = setTimeout(() => { State.filters.q = searchInput.value; loadBrowseResults(); }, 300);
    });

    ['filter-type', 'filter-source', 'filter-difficulty'].forEach(id => {
        document.getElementById(id).addEventListener('change', (e) => {
            const key = id.replace('filter-', '');
            State.filters[key === 'type' ? 'item_type' : key] = e.target.value;
            loadBrowseResults();
        });
    });

    await loadBrowseResults();
}

async function loadBrowseResults(offset = 0) {
    const resultsEl = document.getElementById('browse-results');
    if (!resultsEl) return;

    const params = new URLSearchParams();
    if (State.filters.q) params.set('q', State.filters.q);
    if (State.filters.item_type) params.set('item_type', State.filters.item_type);
    if (State.filters.source) params.set('source', State.filters.source);
    if (State.filters.difficulty) params.set('difficulty', State.filters.difficulty);
    params.set('limit', '50');
    params.set('offset', String(offset));

    const endpoint = State.filters.q ? '/search' : '/items';
    const data = await Api.get(`${endpoint}?${params}`);

    if (data.items.length === 0) {
        resultsEl.innerHTML = '<div class="empty-state"><div class="empty-state-icon">🔍</div><h3>No items found</h3><p>Try adjusting your search or filters.</p></div>';
        return;
    }

    resultsEl.innerHTML = `
        <div style="font-size:0.8rem;color:var(--text-muted);margin-bottom:12px">${data.total} result${data.total !== 1 ? 's' : ''}</div>
        <div class="items-grid">${data.items.map(renderItemCard).join('')}</div>
    `;
}

function renderItemCard(item) {
    const tags = (item.tags || []).map(t => {
        const tagName = typeof t === 'string' ? t : t.tag;
        const isAi = typeof t === 'object' && t.source === 'ai';
        return `<span class="tag ${isAi ? 'ai-tag' : ''}">${tagName}</span>`;
    }).join('');

    const date = item.created_at ? new Date(item.created_at).toLocaleDateString() : '';

    return `
        <div class="item-card" onclick="location.hash='#/item/${item.id}'">
            <div class="item-card-header">
                <div class="item-title">${escHtml(item.title)}</div>
                <span class="item-type-badge ${item.item_type}">${item.item_type}</span>
            </div>
            ${item.url ? `<div class="item-url">${escHtml(item.url)}</div>` : ''}
            ${item.description ? `<div class="item-description">${escHtml(item.description)}</div>` : ''}
            ${tags ? `<div class="item-tags">${tags}</div>` : ''}
            <div class="item-meta">
                <span>${item.source}</span>
                ${item.difficulty ? `<span>• ${item.difficulty}</span>` : ''}
                ${item.language ? `<span>• ${item.language}</span>` : ''}
                <span>• ${date}</span>
                ${item.has_embedding ? '<span>• 🧠</span>' : ''}
            </div>
        </div>
    `;
}

// ---- Item Detail ----
async function renderItemDetail(el, itemId) {
    const item = await Api.get(`/items/${itemId}`);
    State.currentItem = item;

    const tags = (item.tags || []).map(t => {
        const tagName = typeof t === 'string' ? t : t.tag;
        return `<span class="tag">${tagName} <span style="cursor:pointer;margin-left:4px" onclick="App.removeTag(${item.id},'${tagName}')">×</span></span>`;
    }).join('');

    el.innerHTML = `
        <div class="detail-view">
            <div class="detail-back" onclick="history.back()">← Back</div>
            <div class="detail-header">
                <div class="flex items-center gap-2" style="margin-bottom:8px">
                    <span class="item-type-badge ${item.item_type}">${item.item_type}</span>
                    ${item.difficulty ? `<span class="item-type-badge" style="background:var(--bg-surface-3);color:var(--text-secondary)">${item.difficulty}</span>` : ''}
                    ${item.has_embedding ? '<span title="Has embedding">🧠</span>' : ''}
                </div>
                <div class="detail-title">${escHtml(item.title)}</div>
                ${item.url ? `<a class="detail-url" href="${item.url}" target="_blank">${escHtml(item.url)}</a>` : ''}
            </div>

            ${item.description ? `<div class="detail-section"><h3>Description</h3><p style="color:var(--text-secondary);font-size:0.9rem;line-height:1.6">${escHtml(item.description)}</p></div>` : ''}

            <div class="detail-section">
                <h3>Tags</h3>
                <div class="flex flex-wrap gap-2 items-center">
                    ${tags || '<span class="text-muted" style="font-size:0.85rem">No tags</span>'}
                    <input type="text" id="new-tag-input" placeholder="Add tag..." class="input" style="width:140px;padding:4px 10px;font-size:0.8rem"
                           onkeydown="if(event.key==='Enter'){App.addTag(${item.id},this.value);this.value=''}">
                </div>
            </div>

            <div class="detail-section">
                <div class="flex items-center justify-between">
                    <h3 style="margin-bottom:0">Notes</h3>
                    <button class="btn btn-sm btn-primary" onclick="App.saveNotes(${item.id})">Save Notes</button>
                </div>
                <textarea class="notes-editor" id="notes-editor" placeholder="Write your notes here (Markdown supported)...">${escHtml(item.notes || '')}</textarea>
            </div>

            <div class="detail-section">
                <div class="flex items-center justify-between">
                    <h3 style="margin-bottom:0">Highlights</h3>
                    <button class="btn btn-sm btn-secondary" onclick="App.showAddHighlight(${item.id})">+ Add</button>
                </div>
                <div id="highlights-list">
                    ${(item.highlights || []).map(h => `
                        <div class="highlight-item">
                            <div class="highlight-text">"${escHtml(h.text)}"</div>
                            ${h.annotation ? `<div class="highlight-annotation">${escHtml(h.annotation)}</div>` : ''}
                            <button class="btn-icon" style="font-size:0.7rem;margin-top:4px" onclick="App.deleteHighlight(${item.id},${h.id})">🗑</button>
                        </div>
                    `).join('') || '<p class="text-muted" style="font-size:0.85rem">No highlights yet</p>'}
                </div>
                <div id="add-highlight-form" class="hidden mt-4">
                    <textarea id="hl-text" class="input" rows="2" placeholder="Highlighted text..."></textarea>
                    <input type="text" id="hl-annotation" class="input mt-4" placeholder="Your annotation..." style="margin-top:8px">
                    <div style="margin-top:8px;display:flex;gap:8px">
                        <button class="btn btn-sm btn-primary" onclick="App.saveHighlight(${item.id})">Save</button>
                        <button class="btn btn-sm btn-secondary" onclick="document.getElementById('add-highlight-form').classList.add('hidden')">Cancel</button>
                    </div>
                </div>
            </div>

            ${Object.keys(item.metadata || {}).length > 0 ? `
            <div class="detail-section">
                <h3>Metadata</h3>
                <div style="font-size:0.8rem;color:var(--text-secondary);background:var(--bg-surface-2);padding:12px;border-radius:var(--radius-sm);font-family:monospace;white-space:pre-wrap">${JSON.stringify(item.metadata, null, 2)}</div>
            </div>` : ''}

            <div class="detail-section">
                <div class="item-meta">
                    <span>Source: ${item.source}</span>
                    <span>Added: ${new Date(item.created_at).toLocaleString()}</span>
                    <span>Updated: ${new Date(item.updated_at).toLocaleString()}</span>
                </div>
            </div>

            <div class="flex gap-2" style="margin-top:20px">
                <button class="btn btn-secondary btn-sm" onclick="App.archiveItem(${item.id}, ${!item.archived})">${item.archived ? 'Unarchive' : 'Archive'}</button>
                <button class="btn btn-danger btn-sm" onclick="App.deleteItem(${item.id})">Delete</button>
            </div>
        </div>
    `;
}

// ---- Duplicates ----
async function renderDuplicates(el) {
    const data = await Api.get('/duplicates?status=pending');
    State.duplicates = data.duplicates;

    el.innerHTML = `
        <div class="page-header"><h1>Duplicate Review</h1></div>
        ${data.duplicates.length === 0 ? '<div class="empty-state"><div class="empty-state-icon">✨</div><h3>No pending duplicates</h3><p>All clear! Duplicates will appear here when detected.</p></div>' : ''}
        <div id="duplicates-list">
            ${data.duplicates.map(renderDuplicateCard).join('')}
        </div>
    `;
}

function renderDuplicateCard(dup) {
    const scoreClass = dup.similarity_score >= 0.95 ? 'high' : 'medium';
    const item = dup.item || {};
    const similar = dup.similar_to || {};

    return `
        <div class="duplicate-card" id="dup-${dup.id}">
            <div class="duplicate-header">
                ⚠️ ${dup.match_type.replace('_', ' ')} match
                <span class="score-badge ${scoreClass}">${(dup.similarity_score * 100).toFixed(0)}% similar</span>
            </div>
            <div class="duplicate-comparison">
                <div class="duplicate-item">
                    <div style="font-weight:600;margin-bottom:4px;font-size:0.9rem">${escHtml(item.title || 'Unknown')}</div>
                    ${item.url ? `<div style="font-size:0.75rem;color:var(--text-muted);word-break:break-all">${escHtml(item.url)}</div>` : ''}
                    <div style="font-size:0.75rem;color:var(--text-muted);margin-top:4px">${item.item_type || ''} • ${item.source || ''}</div>
                </div>
                <div class="duplicate-vs">VS</div>
                <div class="duplicate-item">
                    <div style="font-weight:600;margin-bottom:4px;font-size:0.9rem">${escHtml(similar.title || 'Unknown')}</div>
                    ${similar.url ? `<div style="font-size:0.75rem;color:var(--text-muted);word-break:break-all">${escHtml(similar.url)}</div>` : ''}
                    <div style="font-size:0.75rem;color:var(--text-muted);margin-top:4px">${similar.item_type || ''} • ${similar.source || ''}</div>
                </div>
            </div>
            <div class="duplicate-actions">
                <button class="btn btn-sm btn-secondary" onclick="App.resolveDuplicate(${dup.id},'dismissed')">Keep Both</button>
                <button class="btn btn-sm btn-success" onclick="App.resolveDuplicate(${dup.id},'merged',${item.id})">Keep Left</button>
                <button class="btn btn-sm btn-success" onclick="App.resolveDuplicate(${dup.id},'merged',${similar.id})">Keep Right</button>
            </div>
        </div>
    `;
}

// ---- Import / Export ----
async function renderImportExport(el) {
    el.innerHTML = `
        <div class="page-header"><h1>Import / Export</h1></div>

        <div class="import-section">
            <h3>🐙 Import GitHub Stars</h3>
            <p>Import your starred repositories from GitHub. Configure your username in Settings first.</p>
            <button class="btn btn-primary" onclick="App.importGitHub()">Import Stars</button>
        </div>

        <div class="import-section">
            <h3>🧭 Import Safari Bookmarks</h3>
            <p>Import bookmarks directly from Safari's bookmark file.</p>
            <button class="btn btn-primary" onclick="App.importSafari()">Import from Safari</button>
        </div>

        <div class="import-section">
            <h3>📄 Import from File</h3>
            <p>Upload a bookmark file (Netscape HTML, JSON, or CSV).</p>
            <div class="file-drop-zone" id="file-drop"
                 onclick="document.getElementById('file-input').click()"
                 ondragover="event.preventDefault();this.classList.add('dragover')"
                 ondragleave="this.classList.remove('dragover')"
                 ondrop="event.preventDefault();this.classList.remove('dragover');App.handleFileDrop(event)">
                Click or drag a file here
            </div>
            <input type="file" id="file-input" class="hidden" accept=".html,.htm,.json,.csv" onchange="App.handleFileSelect(event)">
        </div>

        <hr style="border:none;border-top:1px solid var(--border);margin:28px 0">

        <div class="import-section">
            <h3>📤 Export Data</h3>
            <p>Download your data in various formats.</p>
            <div class="flex gap-2 flex-wrap">
                <a href="/api/export/json" class="btn btn-secondary" download>Export JSON</a>
                <a href="/api/export/csv" class="btn btn-secondary" download>Export CSV</a>
                <a href="/api/export/html" class="btn btn-secondary" download>Export HTML</a>
            </div>
        </div>
    `;
}

// ---- Settings ----
async function renderSettings(el) {
    const settings = await Api.get('/settings');
    const bookmarklet = await Api.get('/settings/bookmarklet');
    State.settings = settings;

    const providers = settings.ai.providers || [];

    el.innerHTML = `
        <div class="page-header"><h1>Settings</h1></div>

        <div class="settings-section">
            <h3>🔖 Safari Bookmarklet</h3>
            <p style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:12px">
                To save pages from Safari with one click, create a bookmark and paste this code as the URL:
            </p>
            <textarea class="input" rows="3" readonly style="font-family:monospace;font-size:0.75rem" onclick="this.select()">${bookmarklet.bookmarklet}</textarea>
            <p style="font-size:0.8rem;color:var(--text-muted);margin-top:8px">${bookmarklet.instructions}</p>
        </div>

        <div class="settings-section">
            <h3>🐙 GitHub</h3>
            <div class="form-row">
                <div class="form-group">
                    <label>Username</label>
                    <input type="text" id="gh-username" class="input" value="${settings.github.username}" placeholder="your-username">
                </div>
                <div class="form-group">
                    <label>Personal Access Token (optional, for private stars)</label>
                    <input type="password" id="gh-token" class="input" placeholder="${settings.github.has_token ? '••••••••' : 'ghp_...'}" value="">
                </div>
            </div>
            ${settings.github.last_sync ? `<p style="font-size:0.8rem;color:var(--text-muted)">Last sync: ${new Date(settings.github.last_sync).toLocaleString()}</p>` : ''}
        </div>

        <div class="settings-section">
            <h3>🤖 AI Configuration</h3>
            <div class="toggle-wrapper mb-4">
                <div class="toggle ${settings.ai.enabled ? 'active' : ''}" id="ai-toggle" onclick="this.classList.toggle('active')"></div>
                <span style="font-size:0.85rem">Enable AI features</span>
            </div>
            <p style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:16px">
                Add API keys in priority order. Curator tries each provider top-to-bottom and falls back to rule-based when all fail.
            </p>
            <div id="providers-list">
                ${providers.map((p, i) => renderProviderRow(p, i)).join('')}
            </div>
            <button class="btn btn-sm btn-secondary mt-4" onclick="App.addProvider()">+ Add Provider</button>
        </div>

        <div class="settings-section">
            <h3>⚙️ General</h3>
            <div class="toggle-wrapper mb-4">
                <div class="toggle ${settings.general.auto_tag_on_add ? 'active' : ''}" id="toggle-autotag" onclick="this.classList.toggle('active')"></div>
                <span style="font-size:0.85rem">Auto-tag new items</span>
            </div>
            <div class="toggle-wrapper mb-4">
                <div class="toggle ${settings.general.auto_embed_on_add ? 'active' : ''}" id="toggle-autoembed" onclick="this.classList.toggle('active')"></div>
                <span style="font-size:0.85rem">Auto-embed new items (for semantic search)</span>
            </div>
            <div class="toggle-wrapper mb-4">
                <div class="toggle ${settings.general.auto_dedupe_on_add ? 'active' : ''}" id="toggle-autodedupe" onclick="this.classList.toggle('active')"></div>
                <span style="font-size:0.85rem">Auto-check duplicates on add</span>
            </div>
        </div>

        <div class="form-actions" style="border:none;padding-top:0">
            <button class="btn btn-primary" onclick="App.saveSettings()">Save Settings</button>
        </div>
    `;
}

function renderProviderRow(p, idx) {
    return `
        <div class="provider-row" data-idx="${idx}">
            <select class="input prov-name">
                <option value="openai" ${p.name === 'openai' ? 'selected' : ''}>OpenAI</option>
                <option value="gemini" ${p.name === 'gemini' ? 'selected' : ''}>Gemini</option>
                <option value="claude" ${p.name === 'claude' ? 'selected' : ''}>Claude</option>
                <option value="ollama" ${p.name === 'ollama' ? 'selected' : ''}>Ollama</option>
            </select>
            <input type="text" class="input prov-model" placeholder="Model name" value="${p.model || ''}">
            <input type="password" class="input prov-key" placeholder="API Key" value="${p.has_key ? '' : ''}" ${p.has_key ? 'placeholder="••••••••"' : ''}>
            <input type="number" class="input prov-priority" placeholder="#" value="${p.priority || idx + 1}" min="1" max="10">
            <button class="btn-icon" onclick="this.closest('.provider-row').remove()">🗑</button>
        </div>
    `;
}

// ---- App actions (global) ----
const App = {
    openModal() {
        document.getElementById('add-modal').classList.remove('hidden');
        document.getElementById('add-url').focus();
    },
    closeModal() {
        document.getElementById('add-modal').classList.add('hidden');
        document.getElementById('add-form').reset();
    },
    async handleAddItem(e) {
        e.preventDefault();
        const url = document.getElementById('add-url').value.trim();
        const title = document.getElementById('add-title').value.trim();
        const description = document.getElementById('add-description').value.trim();
        const itemType = document.getElementById('add-type').value;
        const difficulty = document.getElementById('add-difficulty').value;
        const tags = document.getElementById('add-tags').value;
        const notes = document.getElementById('add-notes').value;

        try {
            await Api.post('/items', {
                url: url || null,
                title,
                description,
                item_type: itemType,
                difficulty: difficulty || null,
                tags: tags ? tags.split(',').map(t => t.trim()).filter(Boolean) : [],
                notes,
            });
            toast('Item saved! Enrichment running in background...', 'success');
            App.closeModal();
            navigate(State.currentPage);
        } catch (err) {
            toast(err.message, 'error');
        }
    },
    async addTag(itemId, tag) {
        if (!tag.trim()) return;
        try {
            await Api.post(`/items/${itemId}/tags`, { tag: tag.trim() });
            navigate('item-detail', { id: itemId });
        } catch (err) { toast(err.message, 'error'); }
    },
    async removeTag(itemId, tag) {
        try {
            await Api.del(`/items/${itemId}/tags/${encodeURIComponent(tag)}`);
            navigate('item-detail', { id: itemId });
        } catch (err) { toast(err.message, 'error'); }
    },
    async saveNotes(itemId) {
        const notes = document.getElementById('notes-editor').value;
        try {
            await Api.put(`/items/${itemId}`, { notes });
            toast('Notes saved', 'success');
        } catch (err) { toast(err.message, 'error'); }
    },
    showAddHighlight() {
        document.getElementById('add-highlight-form').classList.remove('hidden');
        document.getElementById('hl-text').focus();
    },
    async saveHighlight(itemId) {
        const text = document.getElementById('hl-text').value.trim();
        const annotation = document.getElementById('hl-annotation').value.trim();
        if (!text) return;
        try {
            await Api.post(`/items/${itemId}/highlights`, { text, annotation });
            toast('Highlight added', 'success');
            navigate('item-detail', { id: itemId });
        } catch (err) { toast(err.message, 'error'); }
    },
    async deleteHighlight(itemId, hlId) {
        try {
            await Api.del(`/items/${itemId}/highlights/${hlId}`);
            navigate('item-detail', { id: itemId });
        } catch (err) { toast(err.message, 'error'); }
    },
    async archiveItem(itemId, archive) {
        try {
            await Api.put(`/items/${itemId}`, { archived: archive });
            toast(archive ? 'Item archived' : 'Item restored', 'success');
            location.hash = '#/browse';
        } catch (err) { toast(err.message, 'error'); }
    },
    async deleteItem(itemId) {
        if (!confirm('Delete this item permanently?')) return;
        try {
            await Api.del(`/items/${itemId}`);
            toast('Item deleted', 'success');
            location.hash = '#/browse';
        } catch (err) { toast(err.message, 'error'); }
    },
    async resolveDuplicate(dupId, status, keepId) {
        try {
            await Api.put(`/duplicates/${dupId}`, { status, keep_item_id: keepId || null });
            const card = document.getElementById(`dup-${dupId}`);
            if (card) { card.style.opacity = '0'; setTimeout(() => card.remove(), 300); }
            toast('Duplicate resolved', 'success');
        } catch (err) { toast(err.message, 'error'); }
    },
    async importGitHub() {
        try {
            const result = await Api.post('/import/github', {});
            toast(result.message || 'GitHub import started', 'info');
        } catch (err) { toast(err.message, 'error'); }
    },
    async importSafari() {
        try {
            const result = await Api.post('/import/safari', {});
            toast(`Safari: ${result.created} imported, ${result.skipped} skipped`, 'success');
            navigate(State.currentPage);
        } catch (err) { toast(err.message, 'error'); }
    },
    async handleFileDrop(e) {
        const file = e.dataTransfer.files[0];
        if (file) await App.uploadFile(file);
    },
    async handleFileSelect(e) {
        const file = e.target.files[0];
        if (file) await App.uploadFile(file);
    },
    async uploadFile(file) {
        try {
            const result = await Api.upload('/import/file', file);
            toast(`Imported: ${result.created} created, ${result.skipped} skipped`, 'success');
            navigate(State.currentPage);
        } catch (err) { toast(err.message, 'error'); }
    },
    addProvider() {
        const list = document.getElementById('providers-list');
        const idx = list.children.length;
        list.insertAdjacentHTML('beforeend', renderProviderRow({ name: 'openai', model: '', priority: idx + 1 }, idx));
    },
    async saveSettings() {
        const providers = [];
        document.querySelectorAll('.provider-row').forEach(row => {
            const name = row.querySelector('.prov-name').value;
            const model = row.querySelector('.prov-model').value;
            const key = row.querySelector('.prov-key').value;
            const priority = parseInt(row.querySelector('.prov-priority').value) || 1;
            if (model) {
                const p = { name, model, priority, timeout: 15 };
                if (key) p.api_key = key;
                else if (State.settings) {
                    const existing = (State.settings.ai.providers || []).find(ep => ep.name === name);
                    if (existing && existing.has_key) p.api_key = '__KEEP__';
                }
                providers.push(p);
            }
        });

        const payload = {
            ai_enabled: document.getElementById('ai-toggle')?.classList.contains('active'),
            providers: providers.filter(p => p.api_key !== '__KEEP__'),
            auto_tag_on_add: document.getElementById('toggle-autotag')?.classList.contains('active'),
            auto_embed_on_add: document.getElementById('toggle-autoembed')?.classList.contains('active'),
            auto_dedupe_on_add: document.getElementById('toggle-autodedupe')?.classList.contains('active'),
            github_username: document.getElementById('gh-username')?.value || '',
        };

        const token = document.getElementById('gh-token')?.value;
        if (token) payload.github_token = token;

        try {
            await Api.put('/settings', payload);
            toast('Settings saved. Restart Curator for AI changes to take effect.', 'success');
        } catch (err) { toast(err.message, 'error'); }
    },
};

// ---- Utilities ----
function escHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ---- Init ----
document.addEventListener('DOMContentLoaded', () => {
    const hash = location.hash.slice(2) || 'dashboard';
    const parts = hash.split('/');
    if (parts[0] === 'item' && parts[1]) {
        navigate('item-detail', { id: parseInt(parts[1]) });
    } else {
        navigate(parts[0] || 'dashboard');
    }
});
