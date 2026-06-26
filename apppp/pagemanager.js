// ── PAGEMANAGER — generische CRUD-Page-Architektur ──
// Enthält: Utilities, initChatter, PageManager-Klasse
// App-spezifische Konfigurationen bleiben in index.html

const API_BASE = '/claudeapps/apppp/api';

export const get  = p     => fetch(API_BASE+p).then(r=>r.json());
export const post = (p,d) => fetch(API_BASE+p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)}).then(r=>r.json());
export const put  = (p,d) => fetch(API_BASE+p,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)}).then(r=>r.json());
export const del  = p     => fetch(API_BASE+p,{method:'DELETE'}).then(r=>r.json());

export function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

export function fmtDate(str) {
  const d = new Date(str);
  if (isNaN(d)) return str;
  return d.toLocaleDateString('de-DE',{day:'2-digit',month:'2-digit',year:'numeric'})
    + ' ' + d.toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit'});
}

export function toast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 2500);
}

export function showConfirm(msg, {title='BESTÄTIGEN', yesLabel='OK', danger=false}={}) {
  return new Promise(resolve => {
    document.getElementById('confirm-msg').textContent = msg;
    document.getElementById('confirm-title').textContent = title;
    const yesBtn = document.getElementById('confirm-yes');
    yesBtn.textContent = yesLabel;
    yesBtn.className = 'btn ' + (danger ? 'btn-danger' : 'btn-primary');
    document.getElementById('confirm-overlay').classList.add('open');
    const yes = document.getElementById('confirm-yes');
    const no  = document.getElementById('confirm-no');
    const close = result => {
      document.getElementById('confirm-overlay').classList.remove('open');
      yes.replaceWith(yes.cloneNode(true));
      no.replaceWith(no.cloneNode(true));
      resolve(result);
    };
    document.getElementById('confirm-yes').addEventListener('click', () => close(true));
    document.getElementById('confirm-no').addEventListener('click',  () => close(false));
  });
}

export function highlight(text, q) {
  if (!q) return esc(text);
  const idx = text.toLowerCase().indexOf(q.toLowerCase());
  if (idx === -1) return esc(text);
  return esc(text.slice(0,idx)) + '<em>' + esc(text.slice(idx,idx+q.length)) + '</em>' + esc(text.slice(idx+q.length));
}

export function initChatter(entityPath, getEditId, {
  panelEl, inputEl, fileInputEl, sendEl, addNoteBtn, composeEl, fileNameEl, cancelBtn, feedEl, deleteFnName
}) {
  function renderFeed(notes) {
    if (!notes.length) { feedEl.innerHTML = '<div class="chatter-empty">Noch keine Einträge.</div>'; return; }
    feedEl.innerHTML = [...notes].reverse().map(n => {
      const fileHtml = n.file_name
        ? `<a class="chatter-file" href="${API_BASE}/uploads/${n.file_path}" target="_blank" rel="noopener">📎 ${esc(n.file_name)}</a>`
        : '';
      const textHtml = n.content ? `<div class="chatter-text">${esc(n.content)}</div>` : '';
      const eId = n[entityPath.replace(/\//g,'_')+'_id'] || getEditId();
      return `<div class="chatter-entry" data-note-id="${n.id}">
        <div class="chatter-meta">${fmtDate(n.created_at)}</div>
        ${textHtml}${fileHtml}
        <button class="chatter-del" title="Löschen" onclick="${deleteFnName}(${eId||'null'},${n.id})">✕</button>
      </div>`;
    }).join('');
  }

  async function load(id) {
    if (!id) { renderFeed([]); return; }
    try { renderFeed(await get(`/${entityPath}/${id}/notes`)); } catch { renderFeed([]); }
  }

  window[deleteFnName] = async function(eid, noteId) {
    if (!confirm('Eintrag löschen?')) return;
    await fetch(`${API_BASE}/${entityPath}/${eid}/notes/${noteId}`, {method:'DELETE'});
    load(getEditId());
  };

  addNoteBtn.addEventListener('click', () => {
    composeEl.style.display = 'flex';
    inputEl.focus();
    addNoteBtn.style.display = 'none';
  });

  cancelBtn.addEventListener('click', () => {
    composeEl.style.display = 'none';
    inputEl.value = '';
    fileInputEl.value = '';
    fileNameEl.textContent = '';
    addNoteBtn.style.display = '';
  });

  fileInputEl.addEventListener('change', function() {
    fileNameEl.textContent = this.files[0] ? this.files[0].name : '';
  });

  sendEl.addEventListener('click', async () => {
    const eid = getEditId();
    if (!eid) return toast('Bitte zuerst einen Eintrag öffnen');
    const content = inputEl.value.trim();
    const file = fileInputEl.files[0];
    if (!content && !file) return toast('Bitte Text oder Datei eingeben');
    const fd = new FormData();
    if (content) fd.append('content', content);
    if (file) fd.append('file', file);
    try {
      const res = await fetch(`${API_BASE}/${entityPath}/${eid}/notes`, {method:'POST', body:fd});
      if (!res.ok) throw new Error();
      composeEl.style.display = 'none';
      inputEl.value = '';
      fileInputEl.value = '';
      fileNameEl.textContent = '';
      addNoteBtn.style.display = '';
      load(eid);
    } catch { toast('Fehler beim Speichern'); }
  });

  inputEl.addEventListener('keydown', e => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) sendEl.click();
  });

  return { load, renderFeed };
}

export class PageManager {
  constructor(cfg) {
    this.cfg = cfg;
    this.data = [];
    this.viewMode = 'kanban';
    this.kanbanGroup = cfg.defaultGroup || (cfg.groupByOptions[0]?.key);
    this.activeChips = [];
    this.selectedIds = new Set();
    this.sortCol = null;
    this.sortDir = null;
    this.colDragSrc = null;
    this._ddActiveIdx = -1;
    this._selectedField = null;
    this.colSettings = this._loadColSettings();
    this._chatter = null;
  }

  // ── COL SETTINGS ──
  _loadColSettings() {
    const key = `apppp_${this.cfg.entity}_col_settings`;
    const s = JSON.parse(localStorage.getItem(key) || '{}');
    const cols = this.cfg.columns;
    const defaultOrder = cols.map(c => c.key);
    const storedOrder = s.order || defaultOrder;
    const merged = [...storedOrder, ...defaultOrder.filter(k => !storedOrder.includes(k))];
    return {
      widths:  Object.fromEntries(cols.map(c => [c.key, (s.widths||{})[c.key] ?? c.width ?? 150])),
      visible: Object.fromEntries(cols.map(c => [c.key, s.visible ? (c.key in s.visible ? s.visible[c.key] : (c.defaultOn !== false)) : (c.defaultOn !== false)])),
      order:   merged,
    };
  }

  _saveColSettings() {
    localStorage.setItem(`apppp_${this.cfg.entity}_col_settings`, JSON.stringify(this.colSettings));
  }

  _orderedCols() {
    return this.colSettings.order
      .map(k => this.cfg.columns.find(c => c.key === k))
      .filter(c => c && this.colSettings.visible[c.key]);
  }

  // ── INIT ──
  async init() {
    this.data = await get(this.cfg.apiPath);
    this._bindToolbar();
    this._bindSearch();
    this._bindDetail();
    this._initChatter();
    this.renderPage();
  }

  renderPage() {
    if (this.viewMode === 'kanban') this._renderKanban();
    else { this._renderListHeaders(); this._renderListBody(); }
  }

  // ── FILTERED DATA ──
  _filtered() {
    return this.data.filter(item => {
      for (const chip of this.activeChips) {
        if (!this.cfg.filterItem(item, chip)) return false;
      }
      return true;
    });
  }

  _sorted(data) {
    if (!this.sortCol) return data;
    return [...data].sort((a,b) => {
      const va = this.cfg.sortValue ? this.cfg.sortValue(a, this.sortCol) : String(a[this.sortCol]||'').toLowerCase();
      const vb = this.cfg.sortValue ? this.cfg.sortValue(b, this.sortCol) : String(b[this.sortCol]||'').toLowerCase();
      if (va < vb) return this.sortDir === 'asc' ? -1 : 1;
      if (va > vb) return this.sortDir === 'asc' ? 1 : -1;
      return 0;
    });
  }

  // ── KANBAN ──
  _renderKanban() {
    const el = document.getElementById(this.cfg.kanbanElId);
    const data = this._filtered();
    const groupOpt = this.cfg.groupByOptions.find(g => g.key === this.kanbanGroup);
    const buckets = groupOpt ? groupOpt.getBuckets(data, this) : [];
    el.innerHTML = '';
    if (!buckets.length) {
      el.innerHTML = '<div style="color:var(--muted);padding:32px">Keine Einträge gefunden.</div>';
      return;
    }
    buckets.forEach(b => {
      const col = document.createElement('div');
      col.className = this.cfg.kanbanColClass || 'column';
      col.dataset.groupkey = b.key;
      col.innerHTML = `<div class="column-header" style="border-bottom-color:${b.color}">
        <h3 style="color:${b.color}">${esc(b.label.toUpperCase())}</h3>
        <span class="count">${b.items.length}</span>
      </div>
      <div class="cards" style="min-height:80px">${b.items.map(item => this.cfg.renderCard(item, this)).join('')}</div>`;
      el.appendChild(col);
    });

    if (this.cfg.useMouseDrag) {
      this._bindMouseDragCards(el, buckets);
    } else {
      this._bindHtml5DragCards(el, buckets);
    }
  }

  _bindHtml5DragCards(el, buckets) {
    let draggedId = null;
    el.querySelectorAll('[data-card-id]').forEach(card => {
      card.setAttribute('draggable', true);
      card.addEventListener('click', () => this.openDetail(+card.dataset.cardId));
      card.addEventListener('dragstart', e => {
        draggedId = +card.dataset.cardId;
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', String(draggedId));
        setTimeout(() => card.classList.add('dragging'), 0);
      });
      card.addEventListener('dragend', () => {
        card.classList.remove('dragging');
        draggedId = null;
        el.querySelectorAll('.cards').forEach(c => c.classList.remove('drag-over'));
      });
    });
    el.querySelectorAll('.cards').forEach((cardsEl, bi) => {
      const bucket = buckets[bi];
      const groupOpt = this.cfg.groupByOptions.find(g => g.key === this.kanbanGroup);
      if (!groupOpt?.onDrop) return;
      cardsEl.addEventListener('dragover', e => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; cardsEl.classList.add('drag-over'); });
      cardsEl.addEventListener('dragleave', e => { if (!cardsEl.contains(e.relatedTarget)) cardsEl.classList.remove('drag-over'); });
      cardsEl.addEventListener('drop', async e => {
        e.preventDefault();
        cardsEl.classList.remove('drag-over');
        if (!draggedId) return;
        const item = this.data.find(i => i.id === draggedId);
        if (!item) return;
        await groupOpt.onDrop(item, bucket.key);
        this.data = await get(this.cfg.apiPath);
        this.renderPage();
        toast(`Verschoben → ${bucket.label}`);
      });
    });
  }

  _bindMouseDragCards(el, buckets) {
    const ghost = document.getElementById(this.cfg.ghostElId);
    let dragging = null;
    el.querySelectorAll('[data-card-id]').forEach(card => {
      card.addEventListener('mousedown', e => {
        if (e.button !== 0) return;
        const sx = e.clientX, sy = e.clientY;
        let started = false;
        const onMove = ev => {
          if (!started && (Math.abs(ev.clientX-sx)>5 || Math.abs(ev.clientY-sy)>5)) {
            started = true;
            card.classList.add('uc-dragging');
            ghost.innerHTML = card.innerHTML;
            ghost.style.width = card.offsetWidth + 'px';
            ghost.style.display = 'block';
            dragging = { id: +card.dataset.cardId };
          }
          if (started) {
            ghost.style.left = (ev.clientX - card.offsetWidth/2) + 'px';
            ghost.style.top  = (ev.clientY - 30) + 'px';
            el.querySelectorAll('[data-groupkey]').forEach(col => {
              const r = col.getBoundingClientRect();
              col.classList.toggle('drag-over-col',
                ev.clientX>=r.left && ev.clientX<=r.right && ev.clientY>=r.top && ev.clientY<=r.bottom);
            });
          }
        };
        const onUp = async ev => {
          window.removeEventListener('mousemove', onMove);
          window.removeEventListener('mouseup', onUp);
          if (!started) { this.openDetail(+card.dataset.cardId); return; }
          card.classList.remove('uc-dragging');
          ghost.style.display = 'none';
          const targetCol = [...el.querySelectorAll('[data-groupkey]')].find(col => {
            const r = col.getBoundingClientRect();
            return ev.clientX>=r.left && ev.clientX<=r.right && ev.clientY>=r.top && ev.clientY<=r.bottom;
          });
          el.querySelectorAll('[data-groupkey]').forEach(c => c.classList.remove('drag-over-col'));
          if (targetCol && dragging) {
            const newVal = targetCol.dataset.groupkey;
            const item = this.data.find(i => i.id === dragging.id);
            const groupOpt = this.cfg.groupByOptions.find(g => g.key === this.kanbanGroup);
            if (item && groupOpt?.onDrop) {
              await groupOpt.onDrop(item, newVal);
              this.data = await get(this.cfg.apiPath);
              toast('Verschoben → ' + (newVal === '__none__' ? '—' : newVal));
              this.renderPage();
            }
          }
          dragging = null;
        };
        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onUp);
      });
    });
  }

  // ── LIST HEADERS ──
  _renderListHeaders() {
    const head = document.getElementById(this.cfg.listHeadId);
    head.querySelectorAll('th[data-col]').forEach(el => el.remove());
    if (this.cfg.buildLeadHeaders) {
      this.cfg.buildLeadHeaders(head, this);
    }
    const visCols = this._orderedCols();
    visCols.forEach(col => {
      const th = document.createElement('th');
      th.dataset.col = col.key;
      th.style.width = (this.colSettings.widths[col.key] || 150) + 'px';
      th.style.position = 'relative';
      th.draggable = true;
      if (this.sortCol === col.key) th.classList.add(this.sortDir === 'asc' ? 'sort-asc' : 'sort-desc');
      th.innerHTML = `<span class="th-label">${col.label.toUpperCase()}</span><div class="col-resizer"></div>`;
      th.querySelector('.th-label').addEventListener('click', () => {
        if (this.sortCol === col.key) {
          if (this.sortDir === 'asc') this.sortDir = 'desc';
          else { this.sortCol = null; this.sortDir = null; }
        } else { this.sortCol = col.key; this.sortDir = 'asc'; }
        this._renderListHeaders();
        this._renderListBody();
      });
      const resizer = th.querySelector('.col-resizer');
      resizer.addEventListener('mousedown', e => {
        e.preventDefault(); e.stopPropagation();
        resizer.classList.add('active');
        const startX = e.clientX, startW = this.colSettings.widths[col.key] || 150;
        const onMove = ev => { const nw = Math.max(60, startW + ev.clientX - startX); this.colSettings.widths[col.key] = nw; th.style.width = nw + 'px'; };
        const onUp   = () => { resizer.classList.remove('active'); this._saveColSettings(); window.removeEventListener('mousemove',onMove); window.removeEventListener('mouseup',onUp); };
        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onUp);
      });
      th.addEventListener('dragstart', e => { this.colDragSrc = col.key; e.dataTransfer.effectAllowed = 'move'; th.classList.add('col-dragging'); });
      th.addEventListener('dragend', () => { th.classList.remove('col-dragging'); head.querySelectorAll('th[data-col]').forEach(el => el.classList.remove('col-drag-over')); });
      th.addEventListener('dragover', e => {
        if (!this.colDragSrc || this.colDragSrc === col.key) return;
        e.preventDefault(); e.dataTransfer.dropEffect = 'move';
        head.querySelectorAll('th[data-col]').forEach(el => el.classList.remove('col-drag-over'));
        th.classList.add('col-drag-over');
      });
      th.addEventListener('dragleave', () => th.classList.remove('col-drag-over'));
      th.addEventListener('drop', e => {
        e.preventDefault();
        if (!this.colDragSrc || this.colDragSrc === col.key) return;
        const order = this.colSettings.order;
        const fi = order.indexOf(this.colDragSrc), ti = order.indexOf(col.key);
        order.splice(fi, 1); order.splice(ti, 0, this.colDragSrc);
        this.colDragSrc = null;
        this._saveColSettings(); this._renderListHeaders(); this._renderListBody();
      });
      head.appendChild(th);
    });
    const selAll = head.querySelector('input[type=checkbox][data-sel-all]') || head.querySelector('th.th-sel input[type=checkbox]');
    if (selAll) {
      const newSelAll = selAll.cloneNode(true);
      selAll.parentNode.replaceChild(newSelAll, selAll);
      newSelAll.addEventListener('change', () => {
        if (newSelAll.checked) this._sorted(this._filtered()).forEach(i => this.selectedIds.add(i.id));
        else this.selectedIds.clear();
        this._renderListBody();
      });
    }
  }

  // ── LIST BODY ──
  _renderListBody() {
    const data = this._sorted(this._filtered());
    const visCols = this._orderedCols();
    const tbody = document.getElementById(this.cfg.listBodyId);
    tbody.innerHTML = data.map(item => {
      const sel = this.selectedIds.has(item.id);
      const cells = visCols.map(col => {
        const inner = this.cfg.cellRenderer(item, col, this);
        const isEditable = (this.cfg.editableFields||[]).includes(col.key);
        const cls = isEditable ? ' class="td-editable-pm"' : '';
        const dat = isEditable ? ` data-field="${col.key}" data-item-id="${item.id}"` : '';
        return `<td${cls}${dat} data-col="${col.key}">${inner}</td>`;
      }).join('');
      return `<tr data-item-id="${item.id}"${sel ? ' class="row-selected"':''}>
        <td class="td-sel-pm"><input type="checkbox" data-item-id="${item.id}"${sel?' checked':''}/></td>
        ${this.cfg.extraLeadCells ? this.cfg.extraLeadCells(item, this) : ''}
        ${cells}
      </tr>`;
    }).join('');

    tbody.querySelectorAll('td.td-sel-pm input').forEach(cb => {
      const id = +cb.dataset.itemId;
      cb.addEventListener('change', e => {
        e.stopPropagation();
        if (cb.checked) this.selectedIds.add(id); else this.selectedIds.delete(id);
        cb.closest('tr').classList.toggle('row-selected', cb.checked);
        const selAll = document.getElementById(this.cfg.listHeadId)?.querySelector('input[type=checkbox]');
        if (selAll) selAll.checked = this.selectedIds.size === data.length && data.length > 0;
      });
    });

    tbody.querySelectorAll('td.td-editable-pm').forEach(td => {
      td.addEventListener('click', e => {
        e.stopPropagation();
        if (td.querySelector('input,select')) return;
        const field  = td.dataset.field;
        const itemId = +td.dataset.itemId;
        const item   = this.data.find(i => i.id === itemId);
        if (!item) return;
        if (this.selectedIds.has(itemId)) {
          this._activateInlineEdit(td, item, field);
        } else {
          this.openDetail(itemId);
        }
      });
    });

    tbody.querySelectorAll('tr[data-item-id]').forEach(tr => {
      tr.addEventListener('click', e => {
        if (e.target.closest('td.td-editable-pm') || e.target.closest('td.td-sel-pm') || e.target.closest('td.td-extra-pm')) return;
        this.openDetail(+tr.dataset.itemId);
      });
    });

    const selAll = document.getElementById(this.cfg.listHeadId)?.querySelector('input[type=checkbox]');
    if (selAll) selAll.checked = data.length > 0 && this.selectedIds.size === data.length;
  }

  _activateInlineEdit(td, item, field) {
    const enumVals = (this.cfg.enumFields||{})[field];
    if (field === 'user_id' || field === 'user') {
      const sel = document.createElement('select');
      sel.className = 'inline-edit-select';
      sel.innerHTML = `<option value="">— Niemand —</option>` +
        users.map(u => `<option value="${u.id}"${item.user_id === u.id ? ' selected':''}>${esc(u.name)}</option>`).join('');
      td.textContent = ''; td.appendChild(sel); sel.focus();
      let _s = false;
      const save = async () => { if (_s) return; _s = true; await this._saveField(item.id, 'user_id', sel.value ? +sel.value : null); };
      sel.addEventListener('change', save); sel.addEventListener('blur', save);
    } else if (enumVals) {
      const sel = document.createElement('select');
      sel.className = 'inline-edit-select';
      sel.innerHTML = enumVals.map(v => `<option${v === (item[field]||'') ? ' selected':''}>${esc(v)}</option>`).join('');
      td.textContent = ''; td.appendChild(sel); sel.focus();
      let _s = false;
      const save = async () => { if (_s) return; _s = true; await this._saveField(item.id, field, sel.value); };
      sel.addEventListener('change', save); sel.addEventListener('blur', save);
    } else {
      const inp = document.createElement('input');
      inp.className = 'inline-edit-input';
      inp.value = item[field] || '';
      td.textContent = ''; td.appendChild(inp); inp.focus(); inp.select();
      let _s = false;
      const save = async () => { if (_s) return; _s = true; await this._saveField(item.id, field, inp.value.trim()); };
      inp.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); save(); } if (e.key === 'Escape') this._renderListBody(); });
      inp.addEventListener('blur', save);
    }
  }

  async _saveField(itemId, field, value) {
    if (this.selectedIds.size > 1 && this.selectedIds.has(itemId)) {
      const col = this.cfg.columns.find(c => c.key === field);
      const ok = await showConfirm(
        `„${col?.label || field}" für alle ${this.selectedIds.size} ausgewählten Einträge auf diesen Wert setzen?`,
        { title: 'MASSENBEARBEITUNG', yesLabel: 'Für alle übernehmen' }
      );
      if (!ok) { this._renderListBody(); return; }
      await Promise.all([...this.selectedIds].map(async sid => {
        const i = this.data.find(x => x.id === sid);
        if (!i) return;
        const updated = this.cfg.computeBeforeSave ? this.cfg.computeBeforeSave({...i,[field]:value},field) : {...i,[field]:value||null};
        await put(`${this.cfg.apiPath}/${sid}`, updated);
      }));
    } else {
      const i = this.data.find(x => x.id === itemId);
      if (!i) return;
      const updated = this.cfg.computeBeforeSave ? this.cfg.computeBeforeSave({...i,[field]:value},field) : {...i,[field]:value||null};
      await put(`${this.cfg.apiPath}/${itemId}`, updated);
    }
    this.data = await get(this.cfg.apiPath);
    this._renderListBody();
    this._renderKanban();
  }

  // ── COL VIS POPUP ──
  _buildColVisPopup() {
    const popup = document.getElementById(this.cfg.colVisPopupId);
    popup.innerHTML = '<div class="vis-label">SPALTEN</div>';
    this.cfg.columns.forEach(col => {
      const opt = document.createElement('label');
      opt.className = 'vis-option';
      opt.innerHTML = `<input type="checkbox" ${this.colSettings.visible[col.key]?'checked':''}>${col.label}`;
      opt.addEventListener('click', e => e.stopPropagation());
      opt.querySelector('input').addEventListener('change', e => {
        this.colSettings.visible[col.key] = e.target.checked;
        this._saveColSettings();
        this._renderListHeaders();
        this._renderListBody();
      });
      popup.appendChild(opt);
    });
  }

  _positionColVisPopup() {
    const btn  = document.getElementById(this.cfg.colVisToggleId);
    const popup = document.getElementById(this.cfg.colVisPopupId);
    const rect = btn.getBoundingClientRect();
    popup.style.top   = (rect.bottom + 6) + 'px';
    popup.style.left  = 'auto';
    popup.style.right = (window.innerWidth - rect.right) + 'px';
  }

  // ── TOOLBAR ──
  _bindToolbar() {
    const cfg = this.cfg;
    const kanbanBtn    = document.getElementById(cfg.kanbanBtnId);
    const listBtn      = document.getElementById(cfg.listBtnId);
    const kanbanWrap   = document.getElementById(cfg.kanbanWrapId);
    const listWrap     = document.getElementById(cfg.listWrapId);
    const sortToggle   = document.getElementById(cfg.sortToggleId);
    const sortMenu     = document.getElementById(cfg.sortMenuId);
    const colVisToggle = document.getElementById(cfg.colVisToggleId);
    const colVisPopup  = document.getElementById(cfg.colVisPopupId);
    const kanbanEl     = document.getElementById(cfg.kanbanElId);
    const listViewEl   = document.getElementById(cfg.listViewElId);

    sortToggle.style.display = 'flex';
    kanbanWrap.classList.add('active');

    kanbanBtn.addEventListener('click', () => {
      this.viewMode = 'kanban';
      kanbanEl.style.display = 'flex';
      listViewEl.style.display = 'none';
      kanbanBtn.classList.add('active'); listBtn.classList.remove('active');
      kanbanWrap.classList.add('active'); listWrap.classList.remove('active');
      sortToggle.style.display = 'flex'; colVisToggle.style.display = 'none';
      this._renderKanban();
    });

    listBtn.addEventListener('click', () => {
      this.viewMode = 'list';
      kanbanEl.style.display = 'none';
      listViewEl.style.display = 'block';
      kanbanBtn.classList.remove('active'); listBtn.classList.add('active');
      kanbanWrap.classList.remove('active'); listWrap.classList.add('active');
      sortToggle.style.display = 'none'; colVisToggle.style.display = 'flex';
      this._renderListHeaders(); this._renderListBody();
    });

    sortToggle.addEventListener('click', e => { e.stopPropagation(); sortMenu.classList.toggle('open'); });
    document.querySelectorAll(`#${cfg.sortMenuId} [data-group]`).forEach(el => {
      el.addEventListener('click', e => {
        e.stopPropagation();
        if (cfg.sortMenuItemClick && cfg.sortMenuItemClick(el, sortMenu, this)) return;
        this.kanbanGroup = el.dataset.group;
        sortMenu.querySelectorAll('[data-group]').forEach(o => o.classList.remove('active'));
        el.classList.add('active');
        sortMenu.classList.remove('open');
        this._renderKanban();
      });
    });
    document.addEventListener('click', () => sortMenu.classList.remove('open'));

    colVisToggle.addEventListener('click', e => {
      e.stopPropagation();
      this._buildColVisPopup();
      this._positionColVisPopup();
      colVisPopup.classList.toggle('open');
    });
    document.addEventListener('click', () => colVisPopup.classList.remove('open'));
    window.addEventListener('resize', () => {
      if (colVisPopup.classList.contains('open')) this._positionColVisPopup();
    });

    document.getElementById(cfg.newBtnId).addEventListener('click', () => this.openNew());
  }

  // ── SEARCH ──
  _bindSearch() {
    const cfg = this.cfg;
    const wrapEl  = document.getElementById(cfg.searchWrapId);
    const input   = document.getElementById(cfg.searchInputId);
    const ddEl    = document.getElementById(cfg.searchDropdownId);
    const chipsEl = document.getElementById(cfg.searchChipsId);

    const closeDropdown = () => { ddEl.classList.remove('open'); this._ddActiveIdx = -1; };

    const updatePlaceholder = () => {
      if (this._selectedField) {
        const f = cfg.searchFields.find(f => f.key === this._selectedField);
        input.placeholder = (f ? f.label : this._selectedField) + ' eingeben…';
      } else {
        input.placeholder = cfg.searchPlaceholder || 'Suchen…';
      }
    };

    const renderChips = () => {
      chipsEl.innerHTML = '';
      this.activeChips.forEach((chip, i) => {
        const f = cfg.searchFields.find(f => f.key === chip.type) || {};
        const div = document.createElement('div');
        div.className = 'search-chip';
        div.innerHTML = `<span class="chip-label">${f.label||chip.type}:</span><span>${chip.label}</span><span class="chip-remove">×</span>`;
        div.querySelector('.chip-remove').addEventListener('click', e => {
          e.stopPropagation();
          this.activeChips.splice(i, 1);
          renderChips(); this.renderPage();
        });
        chipsEl.appendChild(div);
      });
    };

    const addChip = chip => {
      if (this.activeChips.some(c => c.type === chip.type && c.value === chip.value)) return;
      this.activeChips.push(chip);
      input.value = '';
      this._selectedField = null;
      updatePlaceholder(); renderChips(); closeDropdown(); this.renderPage();
    };

    const buildFieldDropdown = () => {
      ddEl.innerHTML = ''; ddEl._items = [];
      const sec = document.createElement('div'); sec.className = 'sd-section';
      const lbl = document.createElement('div'); lbl.className = 'sd-section-label'; lbl.textContent = 'Filtern nach';
      sec.appendChild(lbl);
      cfg.searchFields.forEach(f => {
        const row = document.createElement('div');
        row.className = 'sd-item';
        row.innerHTML = `<span style="font-size:1rem">${f.icon||''}</span><span class="sd-val">${f.label}</span><span class="sd-cat">›</span>`;
        row.addEventListener('mousedown', e => {
          e.preventDefault();
          this._selectedField = f.key;
          const q = input.value.trim();
          if (q && cfg.resolveChip) { const c = cfg.resolveChip(f.key, q, this); if (c) { addChip(c); return; } }
          updatePlaceholder(); closeDropdown(); input.focus();
        });
        sec.appendChild(row);
        ddEl._items.push({ el: row, isField: true, fieldKey: f.key });
      });
      ddEl.appendChild(sec); this._ddActiveIdx = -1; ddEl.classList.add('open');
    };

    const buildValueDropdown = q => {
      ddEl.innerHTML = ''; ddEl._items = [];
      const f = cfg.searchFields.find(f => f.key === this._selectedField);
      const back = document.createElement('div');
      back.className = 'sd-item';
      back.innerHTML = `<span style="opacity:0.5">←</span><span class="sd-cat">${f ? f.label : ''}</span>`;
      back.addEventListener('mousedown', e => {
        e.preventDefault(); this._selectedField = null; input.value = ''; updatePlaceholder(); buildFieldDropdown(); input.focus();
      });
      ddEl.appendChild(back);
      const sec = document.createElement('div'); sec.className = 'sd-section';
      const items = cfg.getSearchValues ? cfg.getSearchValues(this._selectedField, q, this) : [];
      if (!items.length) {
        const empty = document.createElement('div'); empty.className = 'sd-item';
        empty.innerHTML = '<span class="sd-cat">Keine Treffer</span>'; sec.appendChild(empty);
      }
      items.forEach(item => {
        const row = document.createElement('div'); row.className = 'sd-item';
        row.innerHTML = `<span class="sd-val">${item.display || esc(item.label)}</span>`;
        row.addEventListener('mousedown', e => { e.preventDefault(); addChip(item); });
        sec.appendChild(row); ddEl._items.push({ el: row, chip: item });
      });
      ddEl.appendChild(sec); this._ddActiveIdx = -1; ddEl.classList.add('open');
    };

    input.addEventListener('input', e => {
      if (this._selectedField) buildValueDropdown(e.target.value);
      else buildFieldDropdown();
    });
    input.addEventListener('focus', () => {
      if (this._selectedField) buildValueDropdown(input.value);
      else buildFieldDropdown();
    });
    input.addEventListener('keydown', e => {
      const items = ddEl._items || [];
      if (e.key === 'ArrowDown') { e.preventDefault(); this._ddActiveIdx = Math.min(this._ddActiveIdx+1, items.length-1); items.forEach((it,i) => it.el.classList.toggle('active', i===this._ddActiveIdx)); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); this._ddActiveIdx = Math.max(this._ddActiveIdx-1, 0); items.forEach((it,i) => it.el.classList.toggle('active', i===this._ddActiveIdx)); }
      else if (e.key === 'Enter') {
        e.preventDefault();
        const q = input.value.trim();
        if (this._selectedField) {
          if (this._ddActiveIdx >= 0 && items[this._ddActiveIdx]?.chip) addChip(items[this._ddActiveIdx].chip);
          else if (items.length > 0 && items[0].chip) addChip(items[0].chip);
          else if (q && cfg.resolveChip) { const c = cfg.resolveChip(this._selectedField, q, this); if (c) addChip(c); }
        } else if (this._ddActiveIdx >= 0 && items[this._ddActiveIdx]?.isField) {
          const fk = items[this._ddActiveIdx].fieldKey;
          if (q && cfg.resolveChip) { const c = cfg.resolveChip(fk, q, this); if (c) { addChip(c); return; } }
          this._selectedField = fk; updatePlaceholder(); closeDropdown();
        } else if (q) {
          addChip({ type: 'text', label: q, value: q });
        }
      } else if (e.key === 'Escape') {
        if (this._selectedField) { this._selectedField = null; updatePlaceholder(); buildFieldDropdown(); }
        else closeDropdown();
      } else if (e.key === 'Backspace' && input.value === '') {
        if (this._selectedField) { this._selectedField = null; updatePlaceholder(); buildFieldDropdown(); }
        else if (this.activeChips.length > 0) { this.activeChips.splice(-1, 1); renderChips(); this.renderPage(); }
      }
    });
    wrapEl.addEventListener('click', () => input.focus());
    document.addEventListener('click', e => {
      if (!wrapEl.contains(e.target)) { closeDropdown(); this._selectedField = null; updatePlaceholder(); }
    });
  }

  // ── DETAIL ──
  _bindDetail() {
    const cfg = this.cfg;
    document.getElementById(cfg.bcBackId).addEventListener('click', () => this.closeDetail());
    document.getElementById(cfg.cancelBtnId).addEventListener('click', () => this.closeDetail());
    document.getElementById(cfg.saveBtnId).addEventListener('click', () => this._saveDetail());
    document.getElementById(cfg.deleteBtnId).addEventListener('click', () => this._deleteDetail());
  }

  _showDetailPanel(label) {
    const cfg = this.cfg;
    document.getElementById(cfg.listPageElId).style.display = 'none';
    document.getElementById(cfg.detailElId).classList.add('visible');
    document.getElementById(cfg.breadcrumbElId).classList.add('visible');
    document.getElementById(cfg.bcCurrentId).textContent = label;
  }

  closeDetail() {
    const cfg = this.cfg;
    document.getElementById(cfg.detailElId).classList.remove('visible');
    document.getElementById(cfg.breadcrumbElId).classList.remove('visible');
    document.getElementById(cfg.listPageElId).style.display = '';
    this.renderPage();
  }

  openNew() {
    this._editId = null;
    this.cfg.renderDetail(null, this);
    document.getElementById(this.cfg.deleteBtnId).style.display = 'none';
    if (this._chatter) {
      document.getElementById(this.cfg.chatter.composeElId).style.display = 'none';
      document.getElementById(this.cfg.chatter.addNoteBtnId).style.display = '';
      document.getElementById(this.cfg.chatter.feedElId).innerHTML = '<div class="chatter-empty">Noch keine Einträge.</div>';
    }
    this._showDetailPanel(this.cfg.newLabel || 'NEU');
  }

  openDetail(id) {
    const item = this.data.find(i => i.id === id);
    if (!item) return;
    this._editId = id;
    this.cfg.renderDetail(item, this);
    document.getElementById(this.cfg.deleteBtnId).style.display = 'inline-block';
    if (this._chatter) {
      document.getElementById(this.cfg.chatter.composeElId).style.display = 'none';
      document.getElementById(this.cfg.chatter.addNoteBtnId).style.display = '';
      this._chatter.load(id);
    }
    this._showDetailPanel(this.cfg.getTitle(item));
  }

  async _saveDetail() {
    const formData = this.cfg.collectForm(this);
    if (!formData) return;
    try {
      if (this._editId) {
        await put(`${this.cfg.apiPath}/${this._editId}`, formData);
        toast(this.cfg.saveToast || 'Gespeichert');
      } else {
        await post(this.cfg.apiPath, formData);
        toast(this.cfg.createToast || 'Erstellt');
      }
      this.closeDetail();
      this.data = await get(this.cfg.apiPath);
      if (this.cfg.onAfterSave) await this.cfg.onAfterSave(this);
      this.renderPage();
    } catch { toast('Fehler beim Speichern'); }
  }

  async _deleteDetail() {
    if (!this._editId) return;
    const ok = await showConfirm(
      this.cfg.deleteConfirmMsg || 'Wirklich löschen?',
      { title: this.cfg.deleteConfirmTitle || 'LÖSCHEN', yesLabel: 'Löschen', danger: true }
    );
    if (!ok) return;
    await del(`${this.cfg.apiPath}/${this._editId}`);
    this.closeDetail();
    this.data = await get(this.cfg.apiPath);
    if (this.cfg.onAfterDelete) await this.cfg.onAfterDelete(this);
    this.renderPage();
    toast(this.cfg.deleteToast || 'Gelöscht');
  }

  // ── CHATTER INIT ──
  _initChatter() {
    if (!this.cfg.chatter) return;
    const c = this.cfg.chatter;
    const getEditId = () => this._editId;
    this._chatter = initChatter(this.cfg.entity, getEditId, {
      panelEl:     document.getElementById(c.panelElId),
      inputEl:     document.getElementById(c.inputElId),
      fileInputEl: document.getElementById(c.fileInputElId),
      sendEl:      document.getElementById(c.sendElId),
      addNoteBtn:  document.getElementById(c.addNoteBtnId),
      composeEl:   document.getElementById(c.composeElId),
      fileNameEl:  document.getElementById(c.fileNameElId),
      cancelBtn:   document.getElementById(c.cancelBtnId),
      feedEl:      document.getElementById(c.feedElId),
      deleteFnName: c.deleteFnName,
    });
  }
}
