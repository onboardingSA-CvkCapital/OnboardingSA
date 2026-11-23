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
.fy-band{background:var(--bg,#F4F6FA);border-bottom:1px solid var(--line)}
.fy{padding:28px 0 32px;scroll-margin-top:80px}
.fy-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:4px}
.fy-head h2{font-family:Poppins,system-ui,sans-serif;font-weight:700;font-size:24px;color:var(--navy);margin:0}
.fy-edit{display:inline-flex;align-items:center;gap:6px;font-size:13.5px;font-weight:500;color:var(--muted);text-decoration:none;white-space:nowrap}
.fy-edit:hover{color:var(--navy);text-decoration:underline}
.fy .count a{color:var(--navy);font-weight:600}
.fy-empty{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;background:#fff;border:1px solid var(--line);border-radius:14px;padding:18px 20px;margin-top:10px}
.fy-empty p{margin:0;color:var(--text)}
.fy-btn{background:var(--navy);color:#fff;border-radius:8px;padding:10px 18px;font-weight:600;font-size:14.5px;text-decoration:none;white-space:nowrap}
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
  return `<a class="jobcard" href="jobs/${String(j.id).replace(/[^A-Za-z0-9_-]/g, "-")}.html" aria-label="${esc(j.job_title)} at ${esc(j.employer)}">
    <div class="card-head">${av}<div class="card-head-txt"><h3>${esc(j.job_title)}</h3><div class="emp">${esc(j.employer)}</div><div class="loc">${esc(loc)}</div></div></div>
    <div class="chips">${j.employment_type ? `<span class="chip">${esc(j.employment_type)}</span>` : ""}${j.salary ? `<span class="chip">${esc(j.salary)}</span>` : ""}<span class="chip ${soon ? "close-soon" : ""}">${esc(closeTxt)}</span></div></a>`;
}
const PEN = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>';

let band = null, sec = null;
function place() {
  const hero = document.querySelector(".search-band");
  if (!hero) return null;
  if (!band) {
    band = document.createElement("section"); band.className = "fy-band";
    const w = document.createElement("div"); w.className = "wrap";
    sec = document.createElement("div"); sec.className = "fy"; sec.id = "for-you";
    w.appendChild(sec); band.appendChild(w); hero.parentNode.insertBefore(band, hero);
  }
  return sec;
}
function clear() { if (band) { band.remove(); band = sec = null; } }

let JOBS = null;
onAuthStateChanged(auth, async u => {
  if (!u) { clear(); return; }
  let p = {};
  try { const s = await getDoc(doc(db, "profiles", u.uid)); p = s.exists() ? s.data() : {}; } catch (e) { return; }
  const s = place(); if (!s) return;
  let saved = false; try { saved = sessionStorage.getItem("osa_saved") === "1"; sessionStorage.removeItem("osa_saved"); } catch (e) {}
  const head = `<div class="fy-head"><h2>Jobs for you</h2><a class="fy-edit" href="account.html#profile">${PEN}Change preferences</a></div>`;
  if (!p.roles || !p.roles.length) {
    s.innerHTML = head.replace(/<a class="fy-edit".*?<\/a>/, "") + `<div class="fy-empty"><p>Choose the jobs you want and they'll show here.</p><a class="fy-btn" href="account.html#profile">Set my preferences</a></div>`;
  } else {
    if (!JOBS) { try { JOBS = await (await fetch("jobs-lite.json")).json(); } catch (e) { JOBS = []; } }
    const today = new Date().toISOString().slice(0, 10);
    const m = JOBS.filter(j => fits(j, p, today)).sort((a, b) => String(a.closing_date || "9").localeCompare(String(b.closing_date || "9")));
    const n = m.length;
    const line = (saved ? "Profile saved. " : "") + (n === 1 ? "<b>1</b> open job matches your profile" : `<b>${n}</b> open jobs match your profile`);
    s.innerHTML = head + `<p class="count">${line}${n > 6 ? ` · <a href="#" id="fyMore">Show all</a>` : ""}</p>` +
      (n ? `<div class="list" id="fyList">${m.slice(0, 6).map(card).join("")}</div>` : `<div class="fy-empty"><p>No open jobs match your job titles right now.${p.alerts ? " We'll email you when one is posted." : ""}</p><a class="fy-btn" href="account.html#profile">Change preferences</a></div>`);
    const more = s.querySelector("#fyMore");
    if (more) more.onclick = e => { e.preventDefault(); s.querySelector("#fyList").innerHTML = m.map(card).join(""); more.remove(); };
  }
});
