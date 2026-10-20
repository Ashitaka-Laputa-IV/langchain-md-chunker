// Demo UI for the chunk store. Plain ES modules, no build step.
// The server only serves chunk metadata, so the pane on the right always
// renders the real source file and highlights [start, end).

const state = {
  chunks: [],
  byId: new Map(),
  manifest: {},
  docs: {},
  activeId: null,
  docCache: new Map(),
  requestToken: 0,
};

const el = {
  stats: document.getElementById("stats"),
  search: document.getElementById("search"),
  list: document.getElementById("chunk-list"),
  listCount: document.getElementById("list-count"),
  empty: document.getElementById("list-empty"),
  sourceTitle: document.getElementById("source-title"),
  sourceMeta: document.getElementById("source-meta"),
  sourceBody: document.getElementById("source-body"),
  toast: document.getElementById("toast"),
};

async function fetchJSON(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${url} -> HTTP ${response.status}`);
  }
  return response.json();
}

async function boot() {
  try {
    const [manifest, payload] = await Promise.all([
      fetchJSON("/api/manifest"),
      fetchJSON("/api/chunks"),
    ]);
    state.manifest = manifest;
    state.docs = manifest.docs || {};
    state.chunks = payload.chunks.map((chunk) => ({
      ...chunk,
      haystack: `${chunk.doc}\n${(chunk.headings || []).join(" ")}\n${chunk.preview}`.toLowerCase(),
    }));
    for (const chunk of state.chunks) {
      state.byId.set(chunk.id, chunk);
    }
    renderStats();
    renderList(state.chunks);

    const initial = decodeURIComponent(location.hash.slice(1));
    if (initial && state.byId.has(initial)) {
      await openChunk(initial);
    } else if (state.chunks.length) {
      await openChunk(state.chunks[0].id);
    }
  } catch (error) {
    showToast(`加载失败：${error.message}`);
  }
}

function renderStats() {
  const docCount = state.manifest.doc_count ?? Object.keys(state.docs).length;
  const chunkCount = state.manifest.chunk_count ?? state.chunks.length;
  const avg = state.manifest.avg_chars ?? 0;
  el.stats.textContent = `${docCount} 篇文档 · ${chunkCount} 个 chunk · 平均 ${avg} 字符`;
}

function createRow(chunk, index) {
  const item = document.createElement("li");
  item.className = "chunk";
  item.dataset.id = chunk.id;

  const badge = document.createElement("button");
  badge.type = "button";
  badge.className = "chunk-index";
  badge.textContent = `[${index}]`;
  badge.title = `字符偏移 ${chunk.start}–${chunk.end}`;

  const main = document.createElement("div");
  main.className = "chunk-main";

  const meta = document.createElement("div");
  meta.className = "chunk-meta";
  const doc = document.createElement("span");
  doc.className = "doc";
  doc.textContent = chunk.doc;
  meta.append(doc);
  if (chunk.context) {
    const crumb = document.createElement("span");
    crumb.className = "crumb";
    crumb.textContent = chunk.context;
    meta.append(crumb);
  }

  const preview = document.createElement("p");
  preview.className = "chunk-preview";
  preview.textContent = chunk.preview;

  main.append(meta, preview);
  item.append(badge, main);
  return item;
}

function renderList(list) {
  const fragment = document.createDocumentFragment();
  list.forEach((chunk, index) => fragment.append(createRow(chunk, index + 1)));
  el.list.replaceChildren(fragment);
  el.listCount.textContent = `${list.length} 个 chunk`;
  el.empty.hidden = list.length > 0;
}

function markActive() {
  for (const item of el.list.children) {
    item.classList.toggle("active", item.dataset.id === state.activeId);
  }
}

async function loadDoc(doc) {
  if (!state.docCache.has(doc)) {
    const response = await fetch(`/api/doc?path=${encodeURIComponent(doc)}`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    state.docCache.set(doc, await response.text());
  }
  return state.docCache.get(doc);
}

async function openChunk(id) {
  const chunk = state.byId.get(id);
  if (!chunk) return;

  state.activeId = id;
  markActive();
  history.replaceState(null, "", `#${id}`);

  const item = el.list.querySelector(`li[data-id="${id}"]`);
  if (item) {
    item.scrollIntoView({ block: "nearest" });
  }

  const token = ++state.requestToken;
  try {
    const text = await loadDoc(chunk.doc);
    if (token !== state.requestToken) return;
    renderSource(chunk, text);
  } catch (error) {
    showToast(`读取源文件失败：${error.message}`);
  }
}

function renderSource(chunk, text) {
  // Offsets are Unicode code points, JS strings are UTF-16 code units.
  const chars = Array.from(text);
  const before = chars.slice(0, chunk.start).join("");
  const selected = chars.slice(chunk.start, chunk.end).join("");
  const after = chars.slice(chunk.end).join("");

  const mark = document.createElement("mark");
  mark.className = "chunk-highlight";
  mark.textContent = selected;

  el.sourceBody.replaceChildren(
    document.createTextNode(before),
    mark,
    document.createTextNode(after),
  );

  el.sourceTitle.textContent = chunk.doc;
  el.sourceMeta.replaceChildren();
  addMeta(`字符 ${chunk.start}–${chunk.end}`);
  addMeta(`行 ${chunk.start_line}–${chunk.end_line}`);
  addMeta(`${chunk.chars} 字符`);
  if (chunk.context) addMeta(chunk.context);

  const link = document.createElement("a");
  link.href = `/api/doc?path=${encodeURIComponent(chunk.doc)}`;
  link.target = "_blank";
  link.rel = "noopener";
  link.textContent = "原始文件";
  el.sourceMeta.append(link);

  requestAnimationFrame(() => mark.scrollIntoView({ block: "center" }));
}

function addMeta(text) {
  const span = document.createElement("span");
  span.textContent = text;
  el.sourceMeta.append(span);
}

let toastTimer;
function showToast(message) {
  el.toast.textContent = message;
  el.toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.toast.hidden = true;
  }, 4000);
}

let searchTimer;
el.search.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    const query = el.search.value.trim().toLowerCase();
    const filtered = query
      ? state.chunks.filter((chunk) => chunk.haystack.includes(query))
      : state.chunks;
    renderList(filtered);
    markActive();
    el.list.scrollTop = 0;
  }, 120);
});

el.list.addEventListener("click", (event) => {
  const item = event.target.closest("li[data-id]");
  if (item) openChunk(item.dataset.id);
});

window.addEventListener("hashchange", () => {
  const id = decodeURIComponent(location.hash.slice(1));
  if (id && id !== state.activeId && state.byId.has(id)) openChunk(id);
});

boot();
