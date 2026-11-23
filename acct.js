import { initializeApp, getApps } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import { getAuth, onAuthStateChanged, signOut } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js";

const app = getApps()[0] || initializeApp({
  apiKey: "AIzaSyAurWdE99jLpAX0Gvi93DcX4jOXE2ls8Ig",
  authDomain: "onboardingsa-23692.firebaseapp.com",
  projectId: "onboardingsa-23692",
  storageBucket: "onboardingsa-23692.firebasestorage.app",
  messagingSenderId: "988104656716",
  appId: "1:988104656716:web:14f7e5be18304640a431e9"
});
const auth = getAuth(app);

const css = `
.acct-wrap{position:relative;display:inline-flex;align-items:center;vertical-align:middle}
.acct-lighthdr header .nav{align-items:center}
.acct-wrap a.acct-pill{display:inline-flex;align-items:center;gap:8px;border:1.5px solid currentColor;border-radius:999px;padding:6px 15px;font:600 14.5px Inter,system-ui,sans-serif;line-height:1.2;text-decoration:none;white-space:nowrap;cursor:pointer;background:transparent}
.acct-wrap a.acct-pill.in{padding:3px 12px 3px 3px}
.acct-dark a.acct-pill,.acct-dark a.acct-pill:hover{color:#fff}.acct-dark a.acct-pill:hover{background:rgba(255,255,255,.1)}
.acct-light a.acct-pill,.acct-light a.acct-pill:hover{color:#12294D}.acct-light a.acct-pill:hover{background:#F0F4FB}
.acct-ini{width:28px;height:28px;border-radius:50%;background:#E8A33D;color:#12294D;font:700 12px Inter,system-ui,sans-serif;display:inline-flex;align-items:center;justify-content:center;flex:none}
.acct-name{max-width:130px;overflow:hidden;text-overflow:ellipsis}
.acct-short{display:none}
.acct-menu{position:absolute;right:0;top:calc(100% + 8px);background:#fff;border:1px solid #E4E9F1;border-radius:10px;box-shadow:0 12px 30px rgba(18,41,77,.18);padding:6px;min-width:170px;z-index:60;display:flex;flex-direction:column}
.acct-menu[hidden]{display:none}
.acct-wrap .acct-menu a,.acct-wrap .acct-menu button{display:block;margin:0;padding:10px 12px;border-radius:7px;color:#12294D;font:500 14.5px Inter,system-ui,sans-serif;text-align:left;text-decoration:none;background:none;border:0;cursor:pointer;white-space:nowrap}
.acct-wrap .acct-menu a:hover,.acct-wrap .acct-menu button:hover{background:#F0F4FB;color:#12294D}
@media(max-width:480px){
  .acct-wrap a.acct-pill{font-size:13.5px;padding:5px 11px;gap:6px}
  .acct-wrap a.acct-pill.in{padding:2px 10px 2px 2px}
  .acct-ini{width:26px;height:26px;font-size:11px}
  .acct-long,.acct-caret{display:none}.acct-short{display:inline}
  .acct-name{max-width:76px}
  .acct-lighthdr .nav>a[href$="about.html"]{display:none}
  .acct-lighthdr .brand>svg{height:26px}
}`;
document.head.appendChild(Object.assign(document.createElement("style"), { textContent: css }));

const ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/></svg>';
const CARET = '<svg class="acct-caret" width="10" height="6" viewBox="0 0 10 6" aria-hidden="true"><path d="M1 1l4 4 4-4" stroke="currentColor" stroke-width="1.6" fill="none"/></svg>';
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function dark(el) {
  for (let n = el; n && n !== document.documentElement; n = n.parentElement) {
    const m = getComputedStyle(n).backgroundColor.match(/[\d.]+/g);
    if (m && (m.length < 4 || +m[3] > 0)) return (0.299 * m[0] + 0.587 * m[1] + 0.114 * m[2]) < 128;
  }
  return false;
}

const header = document.querySelector("header");
const links = [...document.querySelectorAll('header a[href$="account.html"]')];
const wraps = links.map(a => {
  const w = document.createElement("span");
  const isDark = dark(header || a);
  w.className = "acct-wrap " + (isDark ? "acct-dark" : "acct-light");
  if (!isDark) document.documentElement.classList.add("acct-lighthdr");
  a.replaceWith(w);
  a.removeAttribute("style"); a.removeAttribute("title"); a.className = (a.className + " acct-pill").trim();
  w.appendChild(a);
  const menu = document.createElement("div"); menu.className = "acct-menu"; menu.hidden = true;
  const h = a.getAttribute("href");
  menu.innerHTML = `<a href="${h}">Jobs for you</a><a href="${h}#profile">My profile</a><button type="button">Sign out</button>`;
  menu.querySelectorAll("a").forEach(x => x.addEventListener("click", () => { menu.hidden = true; }));
  menu.querySelector("button").onclick = async () => { menu.hidden = true; try { localStorage.removeItem("osa_acct"); } catch (e) {} await signOut(auth); };
  w.appendChild(menu);
  a.addEventListener("click", e => { if (a.classList.contains("in")) { e.preventDefault(); menu.hidden = !menu.hidden; } });
  return { a, menu };
});
document.addEventListener("click", e => wraps.forEach(({ a, menu }) => { if (!a.parentElement.contains(e.target)) menu.hidden = true; }));

function render(who) {
  wraps.forEach(({ a, menu }) => {
    if (who) {
      a.classList.add("in");
      a.setAttribute("aria-label", "My account: " + who.first);
      a.innerHTML = `<span class="acct-ini">${esc(who.ini)}</span><span class="acct-name">${esc(who.first)}</span>${CARET}`;
    } else {
      a.classList.remove("in"); menu.hidden = true;
      a.setAttribute("aria-label", "Sign in or sign up");
      a.innerHTML = `${ICON}<span class="acct-long">Sign in / Sign up</span><span class="acct-short">Sign in</span>`;
    }
  });
}
function whoOf(u) {
  const name = (u.displayName || "").trim();
  const parts = name ? name.split(/\s+/) : [u.email.split("@")[0]];
  const first = parts[0];
  const ini = (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
  return { first: first.charAt(0).toUpperCase() + first.slice(1), ini };
}
let cached = null;
try { cached = JSON.parse(localStorage.getItem("osa_acct") || "null"); } catch (e) {}
render(cached);
function update(u) {
  const who = u ? whoOf(u) : null;
  try { who ? localStorage.setItem("osa_acct", JSON.stringify(who)) : localStorage.removeItem("osa_acct"); } catch (e) {}
  render(who);
}
onAuthStateChanged(auth, update);
window.addEventListener("osa-name", () => update(auth.currentUser));
