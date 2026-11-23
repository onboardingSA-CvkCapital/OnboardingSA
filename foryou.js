import { initializeApp, getApps } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import { getAuth, onAuthStateChanged } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js";
import { getFirestore, doc, getDoc } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-firestore.js";

const app = getApps()[0] || initializeApp({
  apiKey: "AIzaSyAurWdE99jLpAX0Gvi93DcX4jOXE2ls8Ig",
  authDomain: "onboardingsa-23692.firebaseapp.com",
  projectId: "onboardingsa-23692",
  storageBucket: "onboardingsa-23692.firebasestorage.app",
  messagingSenderId: "988104656716",
  appId: "1:988104656716:web:14f7e5be18304640a431e9"
});
const auth = getAuth(app), db = getFirestore(app);

document.head.appendChild(Object.assign(document.createElement("style"), { textContent: `
.fy-tabs{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;border-bottom:1px solid var(--line);margin:0 0 16px;scroll-margin-top:80px}
.fy-tabs .tabs{display:flex;gap:26px}
.fy-tabs button{background:none;border:0;border-bottom:3px solid transparent;margin-bottom:-1px;padding:10px 0 12px;font:600 17px Poppins,system-ui,sans-serif;color:var(--muted);cursor:pointer}
.fy-tabs button b{font:600 13px Inter,system-ui,sans-serif;background:var(--tint,#F0F4FB);color:var(--navy);border-radius:999px;padding:2px 8px;margin-left:6px;vertical-align:2px}
.fy-tabs button.on{color:var(--navy);border-bottom-color:var(--gold,#E8A33D)}
.fy-edit{display:inline-flex;align-items:center;gap:6px;font-size:13.5px;font-weight:500;color:var(--muted);text-decoration:none;white-space:nowrap;padding-bottom:14px}
.fy-edit:hover{color:var(--navy);text-decoration:underline}
.fy-mode .filters{display:none}
.fy-go{display:inline-block;margin-top:14px;background:var(--navy);color:#fff;border-radius:8px;padding:10px 18px;font-weight:600;font-size:14.5px;text-decoration:none}
@media(max-width:560px){.fy-tabs{flex-wrap:wrap}.fy-tabs .tabs{gap:18px}.fy-tabs button{font-size:15.5px}.fy-edit{padding-bottom:0;margin:-6px 0 10px}}
`}));

const norm = s => String(s || "").toLowerCase().replace(/[^a-z0-9+#]+/g, " ").trim();
function fits(j, p, today) {
  if (j.closing_date && j.closing_date < today) return false;
  const t = " " + norm(j.job_title) + " ";
  const hit = (p.roles || []).some(r => {
    const w = norm(r).split(" ").filter(x => x.length > 1);
    return w.length && w.every(x => t.includes(" " + x + " ") || t.includes(" " + x + "s "));
  });
  if (!hit) return false;
  if (p.province && p.relocate !== "Yes, anywhere in South Africa") {
    const jp = norm(j.province);
    if (jp && !jp.includes("national") && !jp.includes("various") && jp !== norm(p.province)) return false;
  }
  return true;
}
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function card(j) {
  const g = window;
  const dl = g.daysLeft ? g.daysLeft(j.closing_date) : null, soon = dl !== null && dl <= 7;
  const fd = d => g.fmtDate ? g.fmtDate(d) : d;
  const closeTxt = j.closing_date ? `Closes ${fd(j.closing_date)}${soon ? ` · ${dl < 0 ? "closed" : dl === 0 ? "closes today" : dl + (dl === 1 ? " day left" : " days left")}` : ""}` : "Open until filled";
  const av = g.avatarHTML ? g.avatarHTML(j) : `<div class="avatar">${esc((j.employer || "?")[0])}</div>`;
  const loc = g.locLine ? g.locLine(j) : [j.location, j.province].filter(Boolean).join(", ");
  return `<a class="jobcard" href="jobs/${String(j.id).replace(/[^A-Za-z0-9_-]/g, "-")}.html" aria-label="${esc(j.job_title)} at ${esc(j.employer)}"><div class="card-head">${av}<div class="card-head-txt"><h3>${esc(j.job_title)}</h3><div class="emp">${esc(j.employer)}</div><div class="loc">${esc(loc)}</div></div></div><div class="chips">${j.employment_type ? `<span class="chip">${esc(j.employment_type)}</span>` : ""}${j.salary ? `<span class="chip">${esc(j.salary)}</span>` : ""}<span class="chip ${soon ? "close-soon" : ""}">${esc(closeTxt)}</span></div></a>`;
}
const PEN = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>';
const $ = id => document.getElementById(id);
const main = document.querySelector("main .wrap"), filters = main && main.querySelector(".filters");
let bar = null, mode = "all", profile = null, matches = [], savedMsg = false, busy = false;

function allJobs() { try { return JOBS; } catch (e) { return null; } }
function today() { return new Date().toISOString().slice(0, 10); }
function compute() {
  const all = allJobs() || [];
  matches = (profile && profile.roles && profile.roles.length) ? all.filter(j => fits(j, profile, today())) : [];
  matches.sort((a, b) => String(a.closing_date || "9").localeCompare(String(b.closing_date || "9")));
}
function tabs() {
  if (!bar) {
    bar = document.createElement("div"); bar.className = "fy-tabs"; bar.id = "for-you";
    main.insertBefore(bar, filters || main.firstChild);
    bar.addEventListener("click", e => { const b = e.target.closest("button[data-m]"); if (b) setMode(b.dataset.m, true); });
  }
  const all = allJobs();
  const hasRoles = profile && profile.roles && profile.roles.length;
  bar.innerHTML = `<div class="tabs"><button type="button" data-m="fy" class="${mode === "fy" ? "on" : ""}">Jobs for you</button><button type="button" data-m="all" class="${mode === "all" ? "on" : ""}">All jobs</button></div><a class="fy-edit" href="account.html#profile">${PEN}Change preferences</a>`;
}
function showFy() {
  if (!allJobs()) return;
  busy = true;
  const hasRoles = profile.roles && profile.roles.length;
  if (hasRoles && matches.length) {
    $("list").innerHTML = matches.map(card).join("");
    $("count").innerHTML = savedMsg ? "Profile saved." : "";
    $("pager").innerHTML = "";
  } else {
    $("list").innerHTML = hasRoles
      ? `<div class="empty"><h3>No open jobs match your job titles right now</h3><p>${profile.alerts ? "We'll email you when one is posted." : "Add more job titles to see more jobs."}</p><a class="fy-go" href="account.html#profile">Change preferences</a></div>`
      : `<div class="empty"><h3>Choose the jobs you want</h3><p>Pick your job titles and they'll show here.</p><a class="fy-go" href="account.html#profile">Set my preferences</a></div>`;
    $("count").innerHTML = savedMsg ? "Profile saved." : "";
    $("pager").innerHTML = "";
  }
  setTimeout(() => { busy = false; }, 0);
}
function setMode(m, user) {
  mode = m;
  document.body.classList.toggle("fy-mode", m === "fy");
  tabs();
  if (m === "fy") showFy();
  else if (user) { busy = true; apply(); setTimeout(() => { busy = false; }, 0); }
}
// anything the visitor does with search or filters means all jobs
document.addEventListener("click", e => { if (mode === "fy" && e.target.closest("#searchBtn,#clearBtn")) setMode("all"); }, true);
document.addEventListener("change", e => { if (mode === "fy" && e.target.closest(".filters")) setMode("all"); }, true);
document.addEventListener("keydown", e => { if (mode === "fy" && e.key === "Enter" && e.target.closest("#q,#qloc")) setMode("all"); }, true);
// the page renders all jobs once its data loads; show this person's jobs instead
new MutationObserver(() => {
  if (busy || !profile) return;
  compute(); tabs();
  if (mode === "fy") showFy();
}).observe($("count"), { childList: true, characterData: true, subtree: true });

onAuthStateChanged(auth, async u => {
  if (!u || !main) { profile = null; if (bar) { bar.remove(); bar = null; } document.body.classList.remove("fy-mode"); mode = "all"; return; }
  let p = {};
  try { const s = await getDoc(doc(db, "profiles", u.uid)); p = s.exists() ? s.data() : {}; } catch (e) { return; }
  profile = p;
  try { savedMsg = sessionStorage.getItem("osa_saved") === "1"; sessionStorage.removeItem("osa_saved"); } catch (e) {}
  compute();
  setMode("fy");
  if (location.hash === "#for-you" || savedMsg) bar.scrollIntoView();
});
