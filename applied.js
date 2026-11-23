import { initializeApp, getApps } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import { getAuth } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js";
import { getFirestore, doc, setDoc, serverTimestamp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-firestore.js";

const app = getApps()[0] || initializeApp({
  apiKey: "AIzaSyAurWdE99jLpAX0Gvi93DcX4jOXE2ls8Ig",
  authDomain: "onboardingsa-23692.firebaseapp.com",
  projectId: "onboardingsa-23692",
  storageBucket: "onboardingsa-23692.firebasestorage.app",
  messagingSenderId: "988104656716",
  appId: "1:988104656716:web:14f7e5be18304640a431e9"
});
const auth = getAuth(app), db = getFirestore(app);
const id = decodeURIComponent(location.pathname.split("/").pop().replace(/\.html$/, ""));
document.querySelectorAll("a.apply").forEach(a => a.addEventListener("click", () => {
  const u = auth.currentUser;
  if (!u || !id) return;
  setDoc(doc(db, "profiles", u.uid), { applied: { [id]: serverTimestamp() } }, { merge: true }).catch(() => {});
}));
