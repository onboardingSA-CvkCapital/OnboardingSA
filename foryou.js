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
.jobcard.fy,.jobcard.ap{position:relative}
.jobcard.fy .card-head,.jobcard.ap .card-head{margin-top:14px}
.jobcard.fy{border:2px solid #E8A33D}
.jobcard.ap{border:2px solid #1F9D55}
.fytag{position:absolute;top:-1px;right:18px;font:700 12px Inter,system-ui,sans-serif;padding:4px 10px;border-radius:0 0 8px 8px;z-index:1}
.fytag.f{background:#E8A33D;color:#12294D}
.fytag.a{background:#1F9D55;color:#fff}
`}));

const norm = s => String(s || "").toLowerCase().replace(/[^a-z0-9+#]+/g, " ").trim();
const safe = id => String(id).replace(/[^A-Za-z0-9_-]/g, "-");
function fits(j, p) {
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

let profile = null;
const isMine = j => !!profile && fits(j, profile);
const isApplied = j => !!(profile && profile.applied && profile.applied[safe(j.id)]);

window.fyFirst = list => {
  if (!profile) return list;
  const mine = [], rest = [];
  list.forEach(j => (isMine(j) ? mine : rest).push(j));
  return mine.concat(rest);
};
window.fyMark = j => {
  if (isApplied(j)) return { cls: " ap", tag: '<span class="fytag a">✓ Applied</span>' };
  if (isMine(j)) return { cls: " fy", tag: '<span class="fytag f">For you</span>' };
  return { cls: "", tag: "" };
};
function refresh() { try { if (typeof JOBS !== "undefined" && JOBS && JOBS.length && typeof apply === "function") apply(); } catch (e) {} }

onAuthStateChanged(auth, async u => {
  if (!u) { if (profile) { profile = null; refresh(); } return; }
  try { const s = await getDoc(doc(db, "profiles", u.uid)); profile = s.exists() ? s.data() : {}; } catch (e) { return; }
  refresh();
});
