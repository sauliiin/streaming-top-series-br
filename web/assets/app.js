// Streammy frontend: renders the daily JSON feeds published by the sync job.
// No dependencies. All external text is inserted with textContent (no HTML injection).

const FEEDS_BASE = (document.querySelector('meta[name="feeds-base"]')?.content || "data/").replace(/\/?$/, "/");
const FEEDS = { filmes: `${FEEDS_BASE}movies.json`, series: `${FEEDS_BASE}series.json` };
const PROVIDER_ORDER = ["netflix", "hbo", "prime"];
const SKELETON_CARDS = 8;

const CRITERIA = {
  filmes:
    "Os 20 lançamentos mais recentes de cada serviço · nota IMDb ≥ 5,0 · sem comédias · data do lançamento digital no Brasil ou da estreia.",
  series:
    "As 20 séries com episódios mais recentes de cada serviço (janela de 14 dias, ampliada até completar 20) · nota IMDb ≥ 6,0 · sem reality shows.",
};

const MOVIE_LABELS = { digital: "Lançamento digital", premiere: "Estreia" };

const dateFmt = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
const dateTimeFmt = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "long",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "America/Sao_Paulo",
});
const scoreFmt = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const votesFmt = new Intl.NumberFormat("pt-BR", { notation: "compact" });

const state = { kind: "filmes", provider: "all" };
const cache = new Map();

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function parseDate(iso) {
  // "YYYY-MM-DD" is a calendar date: build it at noon to dodge timezone shifts.
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d, 12);
}

function readHash() {
  const [path, query = ""] = location.hash.replace(/^#\/?/, "").split("?");
  const params = new URLSearchParams(query);
  state.kind = path === "series" ? "series" : "filmes";
  const provider = params.get("p");
  state.provider = PROVIDER_ORDER.includes(provider) ? provider : "all";
}

function writeHash() {
  const query = state.provider === "all" ? "" : `?p=${state.provider}`;
  const next = `#/${state.kind}${query}`;
  if (location.hash !== next) history.replaceState(null, "", next);
}

async function loadFeed(kind) {
  if (!cache.has(kind)) {
    cache.set(
      kind,
      fetch(FEEDS[kind], { cache: "no-cache" }).then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      }),
    );
  }
  try {
    return await cache.get(kind);
  } catch (error) {
    cache.delete(kind); // allow a retry on the next interaction
    throw error;
  }
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

function renderSkeleton(panel) {
  panel.replaceChildren();
  const section = el("section", "provider");
  const list = el("ul", "grid");
  for (let i = 0; i < SKELETON_CARDS; i += 1) {
    const card = el("li", "card skeleton");
    card.append(el("div", "poster"), el("div", "card-body"));
    list.append(card);
  }
  section.append(list);
  panel.append(section);
}

function renderCard(item, kind) {
  const node = $("#card-template").content.firstElementChild.cloneNode(true);
  const link = $(".card-link", node);
  link.href = item.links.imdb || item.links.tmdb;
  link.setAttribute("aria-label", `${item.rank}º, ${item.title}`);

  const img = $("img", node);
  const fallback = $(".poster-fallback", node);
  fallback.textContent = item.title;
  if (item.poster) {
    img.addEventListener("load", () => img.classList.add("loaded"), { once: true });
    img.addEventListener("error", () => img.remove(), { once: true });
    img.src = item.poster;
    img.alt = `Pôster de ${item.title}`;
  } else {
    img.remove();
  }

  $(".rank", node).textContent = `#${item.rank}`;
  $(".card-title", node).textContent = item.title;
  $(".card-date", node).textContent = item.date ? dateFmt.format(parseDate(item.date)) : "";
  $(".card-label", node).textContent = kind === "filmes" ? MOVIE_LABELS[item.label] || "" : item.label || "";

  const score = $(".score", node);
  if (item.score === null || item.score === undefined) {
    score.remove();
  } else {
    score.dataset.source = item.score_source;
    $(".score-source", node).textContent = item.score_source === "imdb" ? "IMDb" : "TMDB";
    $(".score-value", node).textContent = scoreFmt.format(item.score);
    score.title = `${votesFmt.format(item.votes)} votos`;
  }
  return node;
}

function renderProvider(section, kind) {
  const wrapper = el("section", "provider");
  wrapper.dataset.provider = section.key;
  wrapper.setAttribute("aria-labelledby", `h-${kind}-${section.key}`);

  const head = el("header", "provider-head");
  const title = el("h2", null, section.name);
  title.id = `h-${kind}-${section.key}`;
  head.append(title);

  let subtitle = `${section.items.length} títulos`;
  if (section.window_days) subtitle += ` · últimos ${section.window_days} dias`;
  head.append(el("span", "provider-sub", subtitle));
  if (section.stale) {
    head.append(el("span", "badge-stale", `Dados de ${dateFmt.format(parseDate(section.updated))}`));
  }

  const list = el("ul", "grid");
  section.items.forEach((item) => list.append(renderCard(item, kind)));
  if (!section.items.length) {
    wrapper.append(head, el("p", "notice", "Nenhum título atende aos critérios hoje."));
  } else {
    wrapper.append(head, list);
  }
  return wrapper;
}

function renderCriteria(feed) {
  const criteria = $("#criteria");
  criteria.replaceChildren(CRITERIA[state.kind]);
  if (feed.list_url) {
    const link = el("a", "list-link", `Lista ${feed.list_name} no MDBList ↗`);
    link.href = feed.list_url;
    link.target = "_blank";
    link.rel = "noopener";
    criteria.append(" ", link);
  }
}

function renderUpdated(feed) {
  const updated = $("#updated");
  const stale = feed.providers.some((p) => p.stale);
  updated.dataset.state = stale ? "stale" : "fresh";
  updated.textContent = `Atualizado em ${dateTimeFmt.format(new Date(feed.generated_at))}`;
}

async function render() {
  writeHash();
  const panel = $("#panel");

  $$(".segmented [role=tab]").forEach((tab) => {
    const selected = tab.dataset.kind === state.kind;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
  });
  panel.setAttribute("aria-labelledby", `tab-${state.kind}`);
  $$(".chip").forEach((chip) => chip.setAttribute("aria-pressed", String(chip.dataset.provider === state.provider)));
  $("#criteria").textContent = CRITERIA[state.kind];
  document.title = `${state.kind === "filmes" ? "Filmes" : "Séries"} · Streammy`;

  const requested = { ...state };
  if (!cache.has(state.kind)) renderSkeleton(panel);

  let feed;
  try {
    feed = await loadFeed(state.kind);
  } catch (error) {
    console.error(error);
    panel.replaceChildren(el("p", "notice", "Não foi possível carregar o ranking agora. Tente novamente em instantes."));
    $("#updated").textContent = "Sem conexão com os dados";
    return;
  }
  if (requested.kind !== state.kind || requested.provider !== state.provider) return; // a newer render won

  renderUpdated(feed);
  renderCriteria(feed);
  const sections = [...feed.providers]
    .sort((a, b) => PROVIDER_ORDER.indexOf(a.key) - PROVIDER_ORDER.indexOf(b.key))
    .filter((section) => state.provider === "all" || section.key === state.provider);
  panel.replaceChildren(...sections.map((section) => renderProvider(section, state.kind)));
}

function bind() {
  const tabs = $$(".segmented [role=tab]");
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => {
      state.kind = tab.dataset.kind;
      render();
    });
    tab.addEventListener("keydown", (event) => {
      if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
      const next = tabs[(index + (event.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
      next.focus();
      next.click();
    });
  });
  $$(".chip").forEach((chip) =>
    chip.addEventListener("click", () => {
      state.provider = chip.dataset.provider;
      render();
    }),
  );
  window.addEventListener("hashchange", () => {
    readHash();
    render();
  });
}

readHash();
bind();
render();
// Warm the other feed so switching tabs is instant.
loadFeed(state.kind === "filmes" ? "series" : "filmes").catch(() => {});
