// Sportive Scout game page: renders window.SCOUT (made by website/build_game.py).
(function () {
  const D = window.SCOUT;
  const view = document.getElementById("view");
  const teamsByName = Object.fromEntries(D.teams.map(t => [t.name, t]));
  const US = teamsByName[D.us], THEM = teamsByName[D.them];
  const gamesById = Object.fromEntries(D.games.map(g => [g.id, g]));
  const momentsById = Object.fromEntries(D.moments.map(m => [m.id, m]));
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (v, f) => v === null || v === undefined ? "–" : f.replace(/\{:\.(\d)f\}/, (_, d) => Number(v).toFixed(+d));
  const slug = name => encodeURIComponent(name);
  const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  let pending = [];   // charts to draw after the view is in the page

  document.title = `${D.title} · Sportive Scout`;
  document.getElementById("foot-note").textContent =
    `Every number comes from logged game film. Updated ${D.updated}.`;

  // ---------- navigation ----------
  const TABS = [
    ["overview", "Overview"], [`team/${slug(D.us)}`, D.us], [`team/${slug(D.them)}`, D.them],
    ["matchup", "Matchup"], ["moments", "Moments"], ["games", "Games"], ["data", "Data"], ["upload", "Upload film"],
  ];
  const tabs = document.getElementById("tabs");
  tabs.innerHTML = TABS.map(([h, label]) => `<a href="#${h}" data-h="${h}">${esc(label)}</a>`).join("");

  function route() {
    const hash = decodeURIComponent(location.hash.slice(1)) || "overview";
    const [page, arg] = hash.split("/");
    pending = [];
    if (page === "team" && teamsByName[arg]) view.innerHTML = teamPage(teamsByName[arg]);
    else if (page === "matchup") view.innerHTML = matchupPage();
    else if (page === "moments") view.innerHTML = momentsPage(arg);
    else if (page === "games") view.innerHTML = gamesPage();
    else if (page === "data") view.innerHTML = dataPage();
    else if (page === "upload") view.innerHTML = uploadPage();
    else view.innerHTML = overviewPage();
    for (const a of tabs.querySelectorAll("a")) {
      const h = decodeURIComponent(a.dataset.h);
      a.classList.toggle("on", h === hash || (page === "team" && h === `team/${arg}`) || (hash === "overview" && h === "overview"));
    }
    drawCharts();
    if (page === "moments") wireMoments();
    window.scrollTo(0, 0);
  }
  window.addEventListener("hashchange", route);

  // ---------- small pieces ----------
  const card = (label, title, body, cls = "") =>
    `<section class="card ${cls}"><div class="card-head"><div class="eyebrow">${esc(label)}</div><h2>${esc(title)}</h2></div>${body}</section>`;
  const splitBar = (a, b, ca = "var(--us)", cb = "var(--them)") => {
    if (a == null || b == null) return `<div class="split"><span style="flex:1;background:var(--line)"></span></div>`;
    const t = (a + b) || 1;
    return `<div class="split"><span style="flex:${a / t};background:${ca}"></span><span style="flex:${b / t};background:${cb}"></span></div>`;
  };
  const chips = items => `<div class="chips">${items.map(([t, c]) => `<span class="chip ${c || ""}">${esc(t)}</span>`).join("")}</div>`;
  const facts = rows => `<table class="facts">${rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join("")}</table>`;

  function chartBox(fig, height) {
    const id = "c" + Math.random().toString(36).slice(2, 9);
    pending.push([id, fig, height]);
    return `<div class="chart" id="${id}"></div>`;
  }

  function drawCharts() {
    const dark = matchMedia("(prefers-color-scheme: dark)").matches;
    for (const [id, fig, height] of pending) {
      const el = document.getElementById(id);
      if (!el || !fig) continue;
      const layout = Object.assign({}, fig.layout, { autosize: true, height: height || fig.layout.height });
      if (dark) {
        Object.assign(layout, { paper_bgcolor: "rgba(0,0,0,0)", font: Object.assign({}, layout.font, { color: css("--muted") }) });
      }
      Plotly.newPlot(el, fig.data, layout, { displayModeBar: false, responsive: true });
      el.on && el.on("plotly_click", ev => {
        const cd = ev.points && ev.points[0] && ev.points[0].customdata;
        if (cd && cd[5] && cd[6] != null) openMomentAt(cd[5], cd[6]);
      });
    }
  }

  function insightList(items, kind) {
    if (!items.length) return `<p class="muted">Nothing clear enough yet.</p>`;
    return items.map(f => `
      <div class="insight ${kind}">
        <div class="stat">${esc(f.stat)}</div>
        <div><div class="label">${esc(f.label)}</div><div class="basis">${esc(f.basis)}</div></div>
        ${f.moments.length ? `<button class="play" data-moments="${esc(f.moments.join(","))}">▶ ${f.moments.length} on film</button>` : "<span></span>"}
      </div>`).join("");
  }

  function gameChips(t) {
    return chips(t.games.map(g => [`vs ${g.vs}${g.score ? `: finished ${g.score}` : ""} · ${t.kpis.minutes} min`])
      .concat(t.notes.filter(n => !n.startsWith("vs ")).map(n => [n, "warn"])));
  }

  // ---------- pages ----------
  function overviewPage() {
    const u = US, t = THEM;
    const duel = (label, a, b, f) => `
      <div class="card duel"><div class="eyebrow" style="text-transform:none;letter-spacing:0">${esc(label)}</div>
        <div class="pair"><span class="num" style="color:var(--us)">${fmt(a, f)}</span><span class="num" style="color:var(--them)">${fmt(b, f)}</span></div>
        ${splitBar(a, b)}</div>`;
    const rows = D.h2h.map(([name, a, b, f, better]) => {
      const lead = (x, y) => better === null || x == null || y == null ? false : better ? x > y : x < y;
      return `<div class="row"><span class="v ${lead(a, b) ? "lead" : ""}" style="--c:var(--us)">${fmt(a, f)}</span>
        <span class="n">${esc(name)}</span><span class="v r ${lead(b, a) ? "lead" : ""}" style="--c:var(--them)">${fmt(b, f)}</span>${splitBar(a, b)}</div>`;
    }).join("");
    const standout = t.strengths.slice(0, 2).map(f => ["good", f]).concat(t.weaknesses.slice(0, 2).map(f => ["bad", f]));
    const goals = D.teams.slice(0, 2).flatMap(team => team.goals.map(g => ({ team, g })));
    return `
      <div class="head"><div class="eyebrow">Matchup</div>
        <h1><span class="dot" style="background:var(--us)"></span>${esc(u.name)}<span class="vs">vs</span><span class="dot" style="background:var(--them)"></span>${esc(t.name)}</h1>
        ${chips(D.teams.slice(0, 2).flatMap(x => x.games.map(g => [`${x.name} · vs ${g.vs} ${g.score || ""} · ${x.kpis.minutes} min`])))}
      </div>
      <div class="grid g4">
        ${duel("Possession", u.kpis.possession, t.kpis.possession, "{:.0f}%")}
        ${duel("Goals per 90", u.goals_90, t.goals_90, "{:.1f}")}
        ${duel("Shots per 90", u.rates.shots_90, t.rates.shots_90, "{:.1f}")}
        ${duel("Shots conceded per 90", u.rates.shots_against_90, t.rates.shots_against_90, "{:.1f}")}
      </div>
      <div class="grid g2">
        ${card("Head to head", "Per 90 minutes, from each team's own game",
          `<div class="legend"><span><span class="team-dot" style="background:var(--us)"></span>${esc(u.name)}</span><span>${esc(t.name)}<span class="team-dot" style="background:var(--them);margin:0 0 0 7px"></span></span></div><div class="rows">${rows}</div>`)}
        <div>
          ${card(t.name, "What stands out", standout.length ? standout.map(([k, f]) => insightList([f], k)).join("") : `<p class="muted">Nothing clear enough yet.</p>`)}
          <p class="note"><a href="#team/${slug(t.name)}">All ${esc(t.name)} insights</a> · <a href="#team/${slug(u.name)}">All ${esc(u.name)} insights</a></p>
        </div>
      </div>
      <div class="grid g2">
        ${card(t.name, "Possession by 5 minutes", chartBox(t.charts.momentum) + `<p class="note">Above the line: more of the ball. Dots are shots (top taken, bottom conceded), stars are goals.</p>`)}
        ${card(u.name, "Possession by 5 minutes", chartBox(u.charts.momentum))}
      </div>
      ${card("Goals", "Every goal in the analyzed film", goalsTable(goals))}`;
  }

  function goalsTable(goals) {
    if (!goals.length) return `<p class="muted">None logged.</p>`;
    return `<div class="table-wrap"><table class="list"><tr><th>Team</th><th>Game</th><th>Minute</th><th>Film time</th><th></th></tr>
      ${goals.map(({ team, g }) => `<tr class="${g.moment ? "click" : ""}" ${g.moment ? `data-moment="${esc(g.moment)}"` : ""}>
        <td><span class="team-dot" style="background:${team.name === D.us ? "var(--us)" : "var(--them)"}"></span>${esc(team.name)}</td>
        <td>${esc((gamesById[g.game] || {}).title || "")}</td><td>${esc(g.minute)}</td><td>${esc(g.film)}</td>
        <td>${g.moment ? `<button class="play" data-moments="${esc(g.moment)}">▶ Watch</button>` : `<span class="muted">no clip</span>`}</td></tr>`).join("")}
    </table></div>`;
  }

  function teamPage(t) {
    const k = t.kpis;
    const role = t.role === "In the film" ? `Opponent in the ${t.games[0] ? esc(t.games[0].vs) : ""} film` : t.role;
    const kpi = (label, v) => `<div class="card kpi"><div class="label">${esc(label)}</div><div class="num">${esc(v)}</div></div>`;
    return `
      <div class="head"><div class="eyebrow">${role}</div>
        <h1><span class="dot" style="background:${t.color}"></span>${esc(t.name)}</h1>${gameChips(t)}</div>
      <div class="grid g6">
        ${kpi("Possession", k.possession == null ? "–" : Math.round(k.possession) + "%")}${kpi("Shots", k.shots)}
        ${kpi("Goals", k.goals)}${kpi("Conceded", k.conceded)}${kpi("Minutes", k.minutes)}${kpi("Confidence", k.confidence.toFixed(2))}
      </div>
      <div class="grid g2">
        ${card("Strengths", `${t.strengths.length} found`, insightList(t.strengths, "good"))}
        ${card("Weaknesses", `${t.weaknesses.length} found`, insightList(t.weaknesses, "bad"))}
      </div>
      ${card("Momentum", "Possession by 5 minutes", chartBox(t.charts.momentum))}
      <div class="grid g2">
        ${card("With the ball", "Where they have the ball", chartBox(t.charts.heat_in))}
        ${card("Without the ball", "Where the opponent has the ball", chartBox(t.charts.heat_out))}
      </div>
      <div class="grid g2">
        ${card("Shots", "Click a shot to watch it", chartBox(t.charts.shots_for))}
        ${card("Shots conceded", "Click a shot to watch it", chartBox(t.charts.shots_against))}
      </div>
      <div class="grid g3">
        ${card("Final third", "Possession by side", chartBox(t.charts.sides, 260))}
        ${card("Defending", "Block, share of defending frames", chartBox(t.charts.blocks, 260))}
        ${card("Turnovers", "Where they lose the ball", chartBox(t.charts.turnovers, 260))}
      </div>
      <div class="grid g3">
        ${card("Usual setup", "Shape and style", facts(t.setup))}
        ${card("Set pieces", "Logged in the analyzed film", facts(Object.entries(t.set_pieces)))}
        ${card("Jersey numbers", "Seen most often near the ball", chartBox(t.charts.players, 260) + `<p class="note">Numbers read near the ball, for both teams.</p>`)}
      </div>
      ${card("Goals", "Minute and film time", goalsTable(t.goals.map(g => ({ team: t, g }))))}`;
  }

  function matchupPage() {
    const u = US, t = THEM;
    const pairs = D.pairs.length
      ? D.pairs.map(p => `<div class="insight"><div class="stat" style="font-size:15px">↔</div><div><div class="label">${esc(p.title)}</div><div class="basis">${esc(p.matches.join(" · "))}</div></div><span></span></div>`).join("")
      : `<p class="muted">No direct overlaps between the two teams' patterns in this film. Compare the setups below.</p>`;
    const setPieceRows = Object.keys(u.set_pieces).map(k => `<tr><td>${esc(k)}</td><td>${esc(u.set_pieces[k])}</td><td>${esc(t.set_pieces[k])}</td></tr>`).join("");
    return `
      <div class="head"><div class="eyebrow">Matchup</div><h1>${esc(u.name)} vs ${esc(t.name)}</h1></div>
      ${card("Where it lines up", "Their numbers next to ours on the same thing", pairs)}
      <div class="grid g2">
        ${card(t.name, "Strengths", insightList(t.strengths, "good"))}
        ${card(t.name, "Weaknesses", insightList(t.weaknesses, "bad"))}
      </div>
      <div class="grid g2">
        ${card(t.name, "Usual setup", facts(t.setup))}
        ${card(u.name, "Usual setup", facts(u.setup))}
      </div>
      ${card("Set pieces", "Logged in the analyzed film", `<div class="table-wrap"><table class="list"><tr><th></th><th>${esc(u.name)}</th><th>${esc(t.name)}</th></tr>${setPieceRows}</table></div>`)}`;
  }

  function momentsPage() {
    const opt = (v, label) => `<option value="${esc(v)}">${esc(label)}</option>`;
    const types = [...new Set(D.moments.map(m => m.type))].sort();
    return `
      <div class="head"><div class="eyebrow">Moments</div><h1>Every logged moment</h1>
        <p class="muted" style="margin:0">Click a row to see the frame and play the clip.</p></div>
      <div class="filters">
        <select id="f-game">${opt("", "All games")}${D.games.map(g => opt(g.id, g.title)).join("")}</select>
        <select id="f-team">${opt("", "Both teams")}${D.teams.map(t => opt(t.name, t.name)).join("")}</select>
        <select id="f-type">${opt("", "All events")}${types.map(t => opt(t, t)).join("")}</select>
        <label class="toggle"><input type="checkbox" id="f-goals"> Goals only</label>
        <label class="toggle"><input type="checkbox" id="f-clips"> With a clip</label>
        <span class="count" id="f-count"></span>
      </div>
      <div class="card" style="padding:0"><div class="table-wrap"><table class="list" id="m-table"></table></div></div>`;
  }

  let shown = [];
  function wireMoments() {
    const get = id => document.getElementById(id);
    const draw = () => {
      const g = get("f-game").value, t = get("f-team").value, ty = get("f-type").value;
      shown = D.moments.filter(m => (!g || m.game === g) && (!t || m.team === t) && (!ty || m.type === ty)
        && (!get("f-goals").checked || m.goal) && (!get("f-clips").checked || m.clip));
      get("f-count").textContent = `${shown.length} moments`;
      get("m-table").innerHTML = `<tr><th>Game</th><th>Team</th><th>Event</th><th>Detail</th><th>Half</th><th>Minute</th><th>Film time</th><th></th></tr>` +
        shown.map(m => `<tr class="click" data-moment="${esc(m.id)}">
          <td>${esc((gamesById[m.game] || {}).title || m.game)}</td>
          <td><span class="team-dot" style="background:${(teamsByName[m.team] || {}).color || "var(--faint)"}"></span>${esc(m.team)}</td>
          <td>${m.goal ? `<span class="tag goal">Goal</span>` : `<span class="tag">${esc(m.type)}</span>`}</td>
          <td>${esc(m.detail)}</td><td>${m.half || ""}</td><td>${m.minute ? m.minute + "'" : "time unknown"}</td><td>${esc(m.film)}</td>
          <td>${m.clip ? "▶ clip" : m.frame ? "frame" : ""}</td></tr>`).join("");
    };
    ["f-game", "f-team", "f-type", "f-goals", "f-clips"].forEach(id => get(id).addEventListener("change", draw));
    draw();
  }

  function gamesPage() {
    return `<div class="head"><div class="eyebrow">Games</div><h1>The analyzed film</h1></div>
      <div class="grid g2">${D.games.map(g => card(g.score ? `Final score ${g.score}` : "Game", g.title, `
        ${facts([["Minutes analyzed", g.minutes ?? "–"], ["Moments logged", D.moments.filter(m => m.game === g.id).length],
                 ["Clips", D.moments.filter(m => m.game === g.id && m.clip).length]])}
        <p class="muted">${esc(g.notes)}</p>
        <div class="chips"><a class="btn" href="#team/${slug(g.analyzed)}">${esc(g.analyzed)}</a>
          <a class="btn" href="#team/${slug(g.other)}">${esc(g.other)}</a>
          <a class="btn" href="#moments" onclick="sessionStorage.setItem('scoutGame','${esc(g.id)}')">Moments</a></div>`)).join("")}</div>`;
  }

  function dataPage() {
    const files = [["data/moments.csv", "Every logged moment (team, event, detail, half, minute, film time)"],
      ["data/frames.csv", "Every analyzed frame (possession, ball zone, blocks, shirt numbers, confidence, note)"],
      ...D.games.map(g => [`data/${g.id}.json`, `Raw log for ${g.title}`])];
    return `<div class="head"><div class="eyebrow">Data</div><h1>Download the data</h1></div>
      ${card("Files", "Open in Excel, Google Sheets or any tool",
        `<table class="facts">${files.map(([f, d]) => `<tr><td>${esc(d)}</td><td><a href="${f}" download>${esc(f.split("/")[1])}</a></td></tr>`).join("")}</table>
         <p class="note">Ball zones are 6 columns along the pitch (6 = the end that team attacks) by 4 rows across it (1 = their left touchline).</p>`)}`;
  }

  function uploadPage() {
    return `<div class="head"><div class="eyebrow">Upload film</div><h1>Analyze your own games</h1></div>
      <section class="card soon"><h2>Coming soon</h2>
        <p class="muted">Upload a game video, name the two teams and get this whole report back, clips included, in a few minutes.</p>
        <p><button class="btn primary" disabled>Upload a video</button></p>
        <p class="note">Until then, the app runs on your computer: <a href="https://github.com/Euryalus-Kay/Sportive-Scout#setup-once">setup steps</a>.</p></section>`;
  }

  // ---------- moment viewer ----------
  const modal = document.getElementById("modal");
  let queue = [], at = 0;
  function openMoments(ids, start = 0) {
    queue = ids.map(id => momentsById[id]).filter(Boolean);
    if (!queue.length) return;
    at = start;
    showMoment();
    modal.hidden = false;
  }
  function openMomentAt(gameId, seconds) {
    const near = D.moments.filter(m => m.game === gameId && m.seconds != null)
      .sort((a, b) => Math.abs(a.seconds - seconds) - Math.abs(b.seconds - seconds))[0];
    if (near && Math.abs(near.seconds - seconds) <= 3) openMoments([near.id]);
  }
  function showMoment() {
    const m = queue[at];
    const game = gamesById[m.game] || {};
    document.getElementById("modal-eyebrow").textContent = `${game.title || ""} · ${m.minute ? m.minute + "'" : "time unknown"} · film ${m.film}`;
    document.getElementById("modal-title").textContent = `${m.goal ? "Goal" : m.type}${m.detail ? ": " + m.detail : ""} · ${m.team}`;
    document.getElementById("modal-media").innerHTML =
      (m.clip ? `<video src="${esc(m.clip)}" controls autoplay muted playsinline preload="metadata"></video>` : "") +
      (m.frame ? `<img src="${esc(m.frame)}" alt="Frame at ${esc(m.film)}" loading="lazy" style="${m.clip ? "margin-top:10px" : ""}">` : "") +
      (!m.clip && !m.frame ? `<p class="empty">No frame saved for this moment.</p>` : "");
    document.getElementById("modal-count").textContent = queue.length > 1 ? `${at + 1} of ${queue.length}` : "";
    document.getElementById("modal-prev").disabled = at === 0;
    document.getElementById("modal-next").disabled = at >= queue.length - 1;
  }
  function closeModal() { modal.hidden = true; document.getElementById("modal-media").innerHTML = ""; }
  document.getElementById("modal-close").onclick = closeModal;
  document.getElementById("modal-prev").onclick = () => { if (at > 0) { at--; showMoment(); } };
  document.getElementById("modal-next").onclick = () => { if (at < queue.length - 1) { at++; showMoment(); } };
  modal.addEventListener("click", e => { if (e.target === modal) closeModal(); });
  document.addEventListener("keydown", e => {
    if (modal.hidden) return;
    if (e.key === "Escape") closeModal();
    if (e.key === "ArrowRight") document.getElementById("modal-next").click();
    if (e.key === "ArrowLeft") document.getElementById("modal-prev").click();
  });
  view.addEventListener("click", e => {
    const btn = e.target.closest("[data-moments]");
    if (btn) { e.stopPropagation(); openMoments(btn.dataset.moments.split(",")); return; }
    const row = e.target.closest("tr[data-moment]");
    if (row) {
      const ids = shown.length && location.hash.startsWith("#moments") ? shown.map(m => m.id) : [row.dataset.moment];
      openMoments(ids, Math.max(0, ids.indexOf(row.dataset.moment)));
    }
  });

  route();
  const game = sessionStorage.getItem("scoutGame");
  if (game && location.hash.startsWith("#moments")) {
    sessionStorage.removeItem("scoutGame");
    const sel = document.getElementById("f-game");
    if (sel) { sel.value = game; sel.dispatchEvent(new Event("change")); }
  }
  window.addEventListener("hashchange", () => {
    const g = sessionStorage.getItem("scoutGame");
    const sel = document.getElementById("f-game");
    if (g && sel) { sessionStorage.removeItem("scoutGame"); sel.value = g; sel.dispatchEvent(new Event("change")); }
  });
})();
