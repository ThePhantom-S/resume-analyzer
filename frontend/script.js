/***********************
 * GLOBAL STATE - MUST BE AT THE TOP
 ***********************/
let analysisHistoryCache = []; 
let currentAnalysisId = null;
let skillChartInstance = null;

/***********************
 * FIREBASE & CONFIG SETUP
 ***********************/
// The variable 'firebaseConfig' is now expected to be provided by config.js 
// which must be loaded in the HTML BEFORE this script.

let auth;
try {
    // We check if firebaseConfig exists (loaded from config.js)
    if (typeof firebaseConfig !== 'undefined') {
        if (!firebase.apps.length) {
            firebase.initializeApp(firebaseConfig);
        }
        auth = firebase.auth();
    } else {
        console.error("CRITICAL: firebaseConfig is missing! Check config.js loading order.");
    }
} catch (e) {
    console.error("Firebase setup failed:", e);
}

function initializeFirebase() {
    if (typeof firebaseConfig !== 'undefined') {
        if (!firebase.apps.length) {
            firebase.initializeApp(firebaseConfig);
        }
        auth = firebase.auth();
        console.log("Neural Link: Firebase Initialized.");
        return true;
    } else {
        console.error("CRITICAL: firebaseConfig not found globally.");
        return false;
    }
}

/***********************
 * AUTHENTICATION
 ***********************/
async function login() {
    try {
        const provider = new firebase.auth.GoogleAuthProvider();
        const result = await auth.signInWithPopup(provider);
        const token = await result.user.getIdToken(true);
        localStorage.setItem("idToken", token);
        localStorage.setItem("userEmail", result.user.email);
        window.location.href = "dashboard.html";
    } catch (err) {
        alert("Login failed: " + err.message);
    }
}

/**
 * 1. Unified Token & Auth Fetcher
 * Forces a fresh token from the source to prevent 401 rejections.
 */
async function getVerifiedSession() {
    return new Promise((resolve, reject) => {
        // Guard against auth not being initialized
        if (!auth) {
            console.error("Auth object is missing.");
            return resolve(null);
        }

        const unsubscribe = auth.onAuthStateChanged(async (user) => {
            unsubscribe();
            if (user) {
                try {
                    const token = await user.getIdToken(true);
                    localStorage.setItem("idToken", token);
                    resolve({ user, token });
                } catch (e) {
                    resolve(null);
                }
            } else {
                resolve(null);
            }
        });
    });
}


async function logout() {
    await auth.signOut();
    localStorage.clear();
    window.location.replace("index.html");
}

/***********************
 * RADAR CHART CORE LOGIC
 ***********************/
async function fetchAndSyncProgress() {
    // Optimization: get token via verified session logic rather than localStorage
    const session = await getVerifiedSession();
    if (!session) return;

    const analysisId = localStorage.getItem('currentAnalysisId');
    if (!analysisId) return;

    try {
        const res = await fetch(`http://127.0.0.1:8000/get-progress/${analysisId}`, {
            headers: { 'Authorization': 'Bearer ' + session.token }
        });
        const progressData = await res.json();
        renderSpiderChart(progressData);
    } catch (e) {
        console.error("Radar sync failed:", e);
    }
}

function renderSpiderChart(progressData) {
    const canvas = document.getElementById('skillChart');
    if (!canvas) return; 
    const ctx = canvas.getContext('2d');
    
    const labels = ["Foundations", "Tooling", "Architecture", "Projects", "Interviews"];
    const dataValues = [0, 0, 0, 0, 0];

    progressData.forEach(p => {
        const dayNum = parseInt(p.day_label.replace(/\D/g, "")) || 0;
        const score = p.is_completed ? (p.skill_score || 5) : 0;
        
        if (dayNum <= 6) dataValues[0] += score;
        else if (dayNum <= 12) dataValues[1] += score;
        else if (dayNum <= 18) dataValues[2] += score;
        else if (dayNum <= 24) dataValues[3] += score;
        else dataValues[4] += score;
    });

    if (skillChartInstance) skillChartInstance.destroy();
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';

    skillChartInstance = new Chart(ctx, {
        type: 'radar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Competency Mapping',
                data: dataValues,
                backgroundColor: 'rgba(99, 102, 241, 0.2)',
                borderColor: '#6366f1',
                borderWidth: 2,
                pointBackgroundColor: '#6366f1'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: { 
                r: { 
                    min: 0,
                    max: 35,
                    ticks: { display: false },
                    grid: { color: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)' },
                    pointLabels: { 
                        color: isDark ? '#94a3b8' : '#64748b', 
                        font: { family: 'Plus Jakarta Sans', weight: '700', size: 11 } 
                    }
                } 
            },
            plugins: { legend: { display: false } }
        }
    });
}

/***********************
 * HISTORY & MASTERY TRACKING
 ***********************/
async function loadHistory() {
    try {
        const session = await getVerifiedSession(); // Fix for 401: Get fresh token
        if (!session) return;
        const token = session.token;

        const res = await fetch('http://127.0.0.1:8000/learning-records', {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        
        analysisHistoryCache = await res.json();
        const list = document.getElementById('historyList');
        if (!list) return;

        if (analysisHistoryCache && analysisHistoryCache.length > 0) {
            let html = "";
            for (const [index, r] of analysisHistoryCache.entries()) {
                const roleName = r.target_role || "Career Analysis";
                const date = new Date(r.created_at).toLocaleDateString();
                html += `
                    <div class="history-node" onclick="handleHistoryClick(${index})">
                        <div style="display:flex; justify-content:space-between; align-items:start; gap: 10px;">
                            <span class="role-title">${roleName}</span>
                            <button class="delete-record-btn" onclick="event.stopPropagation(); deleteRecord('${r.id}')">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18m-2 0v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6m3 0V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path></svg>
                            </button>
                        </div>
                        <div style="font-size:0.6rem; color:var(--text-muted); margin-top:8px; font-weight:600;">
                            ${date} • <span style="color:var(--primary)">${r.readiness_score}% Fit</span>
                        </div>
                    </div>`;
            }
            list.innerHTML = html;
        } else {
            list.innerHTML = `<p style="text-align:center; color:var(--text-muted); padding:20px;">No records.</p>`;
        }
    } catch (e) {
        console.error("History tracking error:", e);
    }
}

function handleHistoryClick(index) {
    const record = analysisHistoryCache[index];
    if (record) {
        localStorage.setItem('currentAnalysisId', record.id);
        localStorage.setItem('currentRoadmap', JSON.stringify(record.preparation_plans || {}));
        localStorage.setItem('currentRole', record.target_role);

        if (window.location.pathname.includes("roadmap")) {
            window.location.reload();
        } else {
            loadRecordToUI(record);
        }
    }
}

/***********************
 * UI RENDERING HELPERS
 ***********************/
async function loadRecordToUI(record) {
    if (!record) return;
    currentAnalysisId = record.id;

    const els = {
        upload: document.getElementById('upload-section'),
        results: document.getElementById('results'),
        score: document.getElementById('scoreDisplay'),
        title: document.getElementById('currentRoleTitle'),
        eligible: document.getElementById('eligibleRolesList'),
        salaryEntry: document.getElementById('salaryEntry'),
        salaryMid: document.getElementById('salaryMid'),
        salarySenior: document.getElementById('salarySenior')
    };

    if (els.upload) els.upload.classList.add('hidden');
    if (els.results) els.results.classList.remove('hidden');
    if (els.score) els.score.innerText = (record.readiness_score || 0) + '%';
    if (els.title) els.title.innerText = (record.target_role || "NEURAL_MISSION").toUpperCase();

    if (els.eligible) {
        let roles = record.eligible_roles;
        if (typeof roles === 'string') {
            try { roles = JSON.parse(roles); } catch (e) { roles = []; }
        }
        if (Array.isArray(roles) && roles.length > 0) {
            els.eligible.innerHTML = roles.map(role => `<div class="track-pill"><span style="color:var(--accent)">✦</span> ${role}</div>`).join('');
        } else {
            els.eligible.innerHTML = `<span style="font-size:0.8rem;">Primary track only.</span>`;
        }
    }

    const sal = record.salary_tiers || { entry: "0", mid: "0", senior: "0" };
    if (els.salaryEntry) els.salaryEntry.innerText = '₹' + (sal.entry || "0");
    if (els.salaryMid) els.salaryMid.innerText = '₹' + (sal.mid || "0");
    if (els.salarySenior) els.salarySenior.innerText = '₹' + (sal.senior || "0");

    fillList('skillsList', record.skills || []);
    fillList('missingList', record.missing_skills || []);

    if (typeof fetchAndSyncProgress === 'function') {
        await fetchAndSyncProgress();
    }
}

function fillList(id, items) {
    const container = document.getElementById(id);
    if (container) container.innerHTML = items.length ? items.map(i => `<span class="badge">${i}</span>`).join('') : "No data.";
}

/***********************
 * INITIALIZATION & DELETION
 ***********************/
async function deleteRecord(recordId) {
    if (!confirm("Erase this record permanently?")) return;
    try {
        const session = await getVerifiedSession();
        if (!session) return;
        const res = await fetch(`http://127.0.0.1:8000/delete-record/${recordId}`, {
            method: 'DELETE',
            headers: { 'Authorization': 'Bearer ' + session.token }
        });
        if (res.ok) {
            if (localStorage.getItem('currentAnalysisId') === recordId) {
                localStorage.removeItem('currentAnalysisId');
                window.location.pathname.includes("roadmap") ? window.location.href = "dashboard.html" : showUploadPage();
            }
            loadHistory();
        }
    } catch (err) {
        console.error("Deletion Error:", err);
    }
}

function showUploadPage() {
    document.getElementById('upload-section')?.classList.remove('hidden');
    document.getElementById('results')?.classList.add('hidden');
}

/**
 * COMPONENT INJECTION ENGINE
 */
async function injectCommonComponents() {
    const components = [
        { id: 'navbar-placeholder', file: 'navbar.html' },
        { id: 'footer-placeholder', file: 'footer.html' }
    ];

    for (const comp of components) {
        const container = document.getElementById(comp.id);
        if (!container) continue;

        try {
            const response = await fetch(comp.file);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const html = await response.text();
            container.innerHTML = html;
            
            const scripts = container.querySelectorAll('script');
            scripts.forEach(oldScript => {
                const newScript = document.createElement('script');
                newScript.text = oldScript.text;
                document.body.appendChild(newScript);
            });

            if (comp.id === 'navbar-placeholder') updateActiveNavItem();
        } catch (err) {
            console.error(`Failed to inject ${comp.file}:`, err);
        }
    }
}

function updateActiveNavItem() {
    const path = window.location.pathname;
    const links = document.querySelectorAll('.nav-link');
    links.forEach(link => {
        if (link.getAttribute('href') && path.includes(link.getAttribute('href'))) {
            link.classList.add('active');
        }
    });
}

/**
 * 2. Sequential Data Sync
 * Loads history and progress in a controlled order to avoid WinError 10055.
 */
async function syncNeuralInterface() {
    const session = await getVerifiedSession(); // Sequential handshake
    
    if (!session) {
        if (!window.location.pathname.includes("index.html")) {
            window.location.replace("index.html");
        }
        return;
    }

    console.log("Neural Link Verified. Syncing Supabase Data...");

    await injectCommonComponents();
    await loadHistory();

    if (window.location.pathname.includes("roadmap.html")) {
        await fetchAndSyncProgress();
    }
}

// Single Entry Point for the entire application
document.addEventListener('DOMContentLoaded', syncNeuralInterface);