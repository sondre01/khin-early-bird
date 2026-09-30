// Khin Early Bird - Interactive Dashboard JS

// If opened via VS Code Live Server (port 5500), route API requests to the Python backend on 8000
const API_BASE = (window.location.port === '5500' || window.location.port === '5501' || window.location.port === '5502') 
    ? 'http://127.0.0.1:8000' 
    : '';

let currentFilterJobType = 'all';
let currentModalJobId = null;
let sseConnection = null;

document.addEventListener('DOMContentLoaded', () => {
    loadStats();
    fetchJobs();
    loadSettings();
    pollPipelineStatus();
});

// Tab Navigation
function switchTab(tabId) {
    document.querySelectorAll('.tab-pane').forEach(el => el.classList.add('hidden'));
    const target = document.getElementById(`tab-${tabId}`);
    if (target) target.classList.remove('hidden');

    document.querySelectorAll('.nav-tab').forEach(btn => {
        btn.classList.remove('bg-blue-600', 'text-white');
        btn.classList.add('text-slate-300');
    });

    const activeNav = document.getElementById(`nav-${tabId}`);
    if (activeNav) {
        activeNav.classList.add('bg-blue-600', 'text-white');
        activeNav.classList.remove('text-slate-300');
    }

    if (tabId === 'dashboard') loadStats();
    if (tabId === 'jobs') fetchJobs();
    if (tabId === 'profile') loadProfile();
    
    if (window.lucide) lucide.createIcons();
}

// Stats & Overview
async function loadStats() {
    try {
        const res = await fetch(`${API_BASE}/api/stats`);
        const data = await res.json();

        document.getElementById('stat-total-jobs').innerText = data.total_jobs || 0;
        document.getElementById('stat-high-matches').innerText = data.high_match_jobs || 0;
        document.getElementById('stat-internships').innerText = data.internships || 0;
        document.getElementById('stat-regular-jobs').innerText = data.regular_jobs || 0;

        // Source counts
        if (data.source_distribution) {
            document.getElementById('src-cnt-linkedin').innerText = `${data.source_distribution['LinkedIn'] || 0} Jobs`;
            document.getElementById('src-cnt-jobstreet').innerText = `${data.source_distribution['Jobstreet'] || 0} Jobs`;
            document.getElementById('src-cnt-indeed').innerText = `${data.source_distribution['Indeed'] || 0} Jobs`;
        }

        // Role Breakdown
        const breakdownContainer = document.getElementById('role-breakdown-list');
        if (breakdownContainer && data.role_distribution) {
            const roleLabels = {
                "software_engineering": "Software Engineering",
                "web_development": "Web Development",
                "it_tech_support": "IT Tech Support & Operations",
                "data_analytics": "Data Analytics",
                "data_engineering": "Data Engineering",
                "data_science": "Data Science & AI",
                "qa_testing": "QA & Software Testing"
            };

            let html = '';
            const maxVal = Math.max(...Object.values(data.role_distribution), 1);
            for (const [key, count] of Object.entries(data.role_distribution)) {
                const label = roleLabels[key] || key.replace('_', ' ').toUpperCase();
                const pct = Math.round((count / maxVal) * 100);
                html += `
                <div class="space-y-1">
                    <div class="flex justify-between text-xs font-semibold text-slate-700">
                        <span>${label}</span>
                        <span class="text-blue-600">${count} opportunities</span>
                    </div>
                    <div class="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
                        <div class="bg-blue-600 h-2 rounded-full" style="width: ${pct}%"></div>
                    </div>
                </div>`;
            }
            breakdownContainer.innerHTML = html || '<p class="text-xs text-slate-400">No role records yet.</p>';
        }

        // Load Top Jobs preview for dashboard
        loadTopJobsPreview();
    } catch (e) {
        console.error('Error loading stats:', e);
    }
}

async function loadTopJobsPreview() {
    try {
        const res = await fetch(`${API_BASE}/api/jobs?limit=6&min_score=80`);
        const data = await res.json();
        const container = document.getElementById('dashboard-top-jobs');
        if (!container) return;

        if (!data.jobs || data.jobs.length === 0) {
            container.innerHTML = `<div class="col-span-3 text-center py-6 text-xs text-slate-400">No jobs scored above 80% yet. Run the scraper to discover opportunities.</div>`;
            return;
        }

        container.innerHTML = data.jobs.map(j => renderJobCard(j)).join('');
        if (window.lucide) lucide.createIcons();
    } catch (e) {
        console.error('Error loading top jobs preview:', e);
    }
}

// Jobs Query & Rendering
async function fetchJobs() {
    const category = document.getElementById('filter-category').value;
    const source = document.getElementById('filter-source').value;
    const score = document.getElementById('filter-score').value;
    const status = document.getElementById('filter-status').value;
    const sortBy = document.getElementById('filter-sort') ? document.getElementById('filter-sort').value : 'recent';
    const hideApplied = document.getElementById('toggle-hide-applied') ? document.getElementById('toggle-hide-applied').checked : false;
    const posted = document.getElementById('filter-posted') ? document.getElementById('filter-posted').value : 'all';
    const search = document.getElementById('search-input').value.trim();

    let url = `${API_BASE}/api/jobs?job_type=${encodeURIComponent(currentFilterJobType)}&sort_by=${encodeURIComponent(sortBy)}`;
    if (category !== 'all') url += `&role_category=${encodeURIComponent(category)}`;
    if (source !== 'all') url += `&source=${encodeURIComponent(source)}`;
    if (score === 'triple') {
        url += `&min_validators=3`;
    } else if (score === 'dual') {
        url += `&min_validators=2`;
    } else if (parseInt(score) > 0) {
        url += `&min_score=${encodeURIComponent(score)}`;
    }
    if (status !== 'all') url += `&status=${encodeURIComponent(status)}`;
    if (hideApplied) url += `&hide_applied=true`;
    if (posted !== 'all') url += `&posted_within=${encodeURIComponent(posted)}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;

    try {
        const res = await fetch(url);
        const data = await res.json();
        const container = document.getElementById('jobs-container');
        const emptyState = document.getElementById('jobs-empty');

        if (!data.jobs || data.jobs.length === 0) {
            container.innerHTML = '';
            emptyState.classList.remove('hidden');
        } else {
            emptyState.classList.add('hidden');
            container.innerHTML = data.jobs.map(j => renderJobCard(j)).join('');
        }
        if (window.lucide) lucide.createIcons();
    } catch (e) {
        console.error('Error fetching jobs:', e);
    }
}

function renderJobCard(job) {
    const score = job.match_score || 0;
    const isHigh = score >= 80;
    const isMod = score >= 60;
    const scoreColorClass = isHigh ? 'bg-emerald-500 text-white' : (isMod ? 'bg-amber-500 text-white' : 'bg-slate-400 text-white');
    const isIntern = job.job_type === 'Internship';
    const typeBadgeClass = isIntern ? 'bg-amber-100 text-amber-800 border-amber-200' : 'bg-indigo-100 text-indigo-800 border-indigo-200';
    const typeIcon = isIntern ? '🎓' : '💼';

    const roleName = (job.role_category || '').replace('_', ' ').toUpperCase();

    const skills = (job.matched_skills || []).slice(0, 3).map(s => 
        `<span class="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 text-[10px] font-semibold">${s}</span>`
    ).join('');

    const statusBadge = job.status === 'applied' 
        ? `<span class="px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 text-[10px] font-bold">Applied</span>`
        : (job.status === 'saved' ? `<span class="px-2 py-0.5 rounded bg-amber-100 text-amber-800 text-[10px] font-bold">Saved</span>` 
        : (job.status === 'dismissed' ? `<span class="px-2 py-0.5 rounded bg-rose-100 text-rose-800 text-[10px] font-bold">Hidden</span>` : ''));

    // Action button depending on status
    const hideOrRestoreBtn = job.status === 'dismissed'
        ? `<button onclick="restoreJob(event, '${job.id}')" title="Restore / Unhide Application" class="p-1.5 rounded-lg text-emerald-600 hover:bg-emerald-50 transition"><i data-lucide="rotate-ccw" class="w-4 h-4"></i></button>`
        : `<button onclick="dismissJob(event, '${job.id}')" title="Hide / Cancel Out (No chance or rejected)" class="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition"><i data-lucide="eye-off" class="w-4 h-4"></i></button>`;

    // Recency badge calculation
    const ageDays = job.posted_age_days !== undefined ? job.posted_age_days : 999;
    const isToday = ageDays <= 0.3 || (job.posted_date || '').toLowerCase().includes('today') || (job.posted_date || '').toLowerCase().includes('hour');
    const isRecent = ageDays <= 3.0;
    const isWeek = ageDays <= 7.0;

    let recencyBadgeClass = 'bg-slate-50 text-slate-600 border-slate-200';
    let recencyIcon = '🕒';
    if (isToday) {
        recencyBadgeClass = 'bg-emerald-50 text-emerald-800 border-emerald-300 font-bold';
        recencyIcon = '⚡';
    } else if (isRecent) {
        recencyBadgeClass = 'bg-blue-50 text-blue-800 border-blue-200 font-semibold';
        recencyIcon = '✨';
    } else if (isWeek) {
        recencyBadgeClass = 'bg-purple-50 text-purple-800 border-purple-200 font-medium';
        recencyIcon = '📅';
    }

    // Consensus Badge
    let consensusBadge = '';
    const vPassed = job.validators_passed !== undefined ? job.validators_passed : 0;
    if (vPassed === 3) {
        consensusBadge = `<span class="px-2 py-0.5 rounded border text-[10px] font-black bg-emerald-100 text-emerald-800 border-emerald-300 shadow-xs" title="Triple Verified: Gemini AI, ML Vector, and Preference Engine all passed">⭐⭐⭐ 3/3 Verified</span>`;
    } else if (vPassed === 2) {
        consensusBadge = `<span class="px-2 py-0.5 rounded border text-[10px] font-bold bg-blue-100 text-blue-800 border-blue-200" title="Dual Verified: 2 of 3 validators passed">⭐⭐ 2/3 Verified</span>`;
    } else if (vPassed === 1) {
        consensusBadge = `<span class="px-2 py-0.5 rounded border text-[10px] font-semibold bg-amber-100 text-amber-800 border-amber-200" title="Borderline: Only 1 validator passed">⚠️ 1/3 Borderline</span>`;
    } else {
        consensusBadge = `<span class="px-2 py-0.5 rounded border text-[10px] font-bold bg-rose-100 text-rose-800 border-rose-200" title="Unqualified: Failed seniority or domain checks">❌ 0/3 Unqualified</span>`;
    }

    return `
    <div id="job-card-${job.id}" class="bg-white rounded-2xl border border-slate-200/90 p-5 shadow-sm hover:shadow-md transition-all duration-300 flex flex-col justify-between group">
        <div class="space-y-3">
            <div class="flex items-start justify-between gap-2">
                <div class="flex flex-wrap items-center gap-1.5">
                    <span class="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-slate-100 text-slate-700">${job.source}</span>
                    <span class="px-2 py-0.5 rounded border text-[10px] font-bold ${typeBadgeClass}">
                        ${typeIcon} ${job.job_type}
                    </span>
                    <span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-blue-50 text-blue-700">${roleName}</span>
                    ${consensusBadge}
                    ${statusBadge}
                </div>
                <div class="flex items-center space-x-1">
                    <div class="px-2.5 py-1 rounded-full text-xs font-black ${scoreColorClass} shadow-sm" title="Weighted Multi-Validator Consensus Score">
                        ${score}% Match
                    </div>
                    <!-- Quick Mark Applied -->
                    <button onclick="markApplied(event, '${job.id}')" title="${job.status === 'applied' ? 'Already Applied' : 'Mark as Applied'}" class="p-1.5 rounded-lg ${job.status === 'applied' ? 'text-emerald-600 bg-emerald-50' : 'text-slate-400 hover:text-emerald-600 hover:bg-emerald-50'} transition">
                        <i data-lucide="check-circle" class="w-4 h-4"></i>
                    </button>
                    <!-- Quick Hide / Cancel Out Symbol -->
                    ${hideOrRestoreBtn}
                </div>
            </div>

            <div>
                <h3 class="font-bold text-sm text-slate-900 group-hover:text-blue-600 transition line-clamp-2">${job.title}</h3>
                <p class="text-xs text-slate-600 mt-1 flex items-center gap-1">
                    <span>🏢 <strong>${job.company}</strong></span>
                    <span>&bull;</span>
                    <span>📍 ${job.location}</span>
                </p>

                <!-- Tri-Validator Scores Pill Row & Details -->
                <div class="flex flex-wrap items-center gap-1.5 mt-2">
                    <span class="inline-flex items-center px-1.5 py-0.5 rounded bg-purple-50 text-purple-700 font-bold text-[10px] border border-purple-200/60" title="Validator 1: Gemini AI LLM Reasoning Score">🤖 AI: ${job.gemini_score || 0}%</span>
                    <span class="inline-flex items-center px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-700 font-bold text-[10px] border border-indigo-200/60" title="Validator 2: Machine Learning Vector & Skill Overlap">🧠 ML: ${job.ml_score || 0}%</span>
                    <span class="inline-flex items-center px-1.5 py-0.5 rounded bg-teal-50 text-teal-700 font-bold text-[10px] border border-teal-200/60" title="Validator 3: Candidate Criteria & Preference Engine">⚖️ Fit: ${job.preference_score || 0}%</span>
                    <span class="text-slate-300">|</span>
                    <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border ${recencyBadgeClass} text-[10px]" title="Posted: ${job.posted_date || 'Recently'}">
                        <span>${recencyIcon}</span>
                        <strong>${job.posted_date || 'Recently'}</strong>
                    </span>
                    <span class="text-slate-400">&bull;</span>
                    <span class="text-slate-500 font-medium text-[11px]">${job.work_type}</span>
                </div>
            </div>

            <!-- Skills Chips -->
            <div class="flex flex-wrap gap-1 pt-1">
                ${skills}
            </div>

            <!-- Match Reason Snippet -->
            ${job.match_reasons && job.match_reasons.length ? `
                <div class="p-2 rounded-lg bg-slate-50 text-[11px] text-slate-600 italic border border-slate-100 line-clamp-2">
                    💡 ${job.match_reasons[0]}
                </div>
            ` : ''}
        </div>

        <div class="pt-4 border-t border-slate-100 mt-4 flex items-center justify-between">
            <button onclick="openJobModal('${job.id}')" class="text-xs font-bold text-blue-600 hover:text-blue-800 transition">
                View Match Breakdown &rarr;
            </button>
            <a href="${job.apply_url}" target="_blank" class="bg-slate-900 hover:bg-blue-600 text-white text-xs font-bold px-3 py-1.5 rounded-lg transition shadow-sm">
                Apply &rarr;
            </a>
        </div>
    </div>
    `;
}

// Segregation Filter Buttons
function setJobTypeFilter(type) {
    currentFilterJobType = type;
    document.querySelectorAll('.seg-btn').forEach(b => {
        b.classList.remove('bg-white', 'text-slate-900', 'shadow-sm');
        b.classList.add('text-slate-600');
    });

    const activeMap = {
        'all': 'btn-seg-all',
        'Internship': 'btn-seg-intern',
        'Regular': 'btn-seg-regular'
    };
    const activeBtn = document.getElementById(activeMap[type]);
    if (activeBtn) {
        activeBtn.classList.add('bg-white', 'text-slate-900', 'shadow-sm');
        activeBtn.classList.remove('text-slate-600');
    }
    fetchJobs();
}

function filterByJobType(type) {
    switchTab('jobs');
    setJobTypeFilter(type);
}

function handleSearchKey(e) {
    if (e.key === 'Enter') fetchJobs();
}

function resetFilters() {
    document.getElementById('filter-category').value = 'all';
    document.getElementById('filter-source').value = 'all';
    document.getElementById('filter-score').value = '0';
    document.getElementById('filter-status').value = 'all';
    if (document.getElementById('filter-posted')) document.getElementById('filter-posted').value = 'all';
    if (document.getElementById('toggle-hide-applied')) document.getElementById('toggle-hide-applied').checked = false;
    if (document.getElementById('filter-sort')) document.getElementById('filter-sort').value = 'recent';
    document.getElementById('search-input').value = '';
    setJobTypeFilter('all');
}

// Job Modal
async function openJobModal(jobId) {
    currentModalJobId = jobId;
    try {
        const res = await fetch(`${API_BASE}/api/jobs/${jobId}`);
        const job = await res.json();

        document.getElementById('modal-title').innerText = job.title;
        document.getElementById('modal-company').innerText = job.company;
        document.getElementById('modal-location').innerText = job.location;
        document.getElementById('modal-work-type').innerText = job.work_type;
        if (document.getElementById('modal-posted-date')) {
            document.getElementById('modal-posted-date').innerText = job.posted_date || 'Recently';
        }
        document.getElementById('modal-source').innerText = job.source;
        document.getElementById('modal-type').innerText = job.job_type;
        document.getElementById('modal-category').innerText = (job.role_category || '').replace('_', ' ').toUpperCase();
        document.getElementById('modal-match-score').innerText = `${job.match_score || 0}%`;
        document.getElementById('modal-match-level').innerText = job.match_level || 'Evaluated';
        document.getElementById('modal-description').innerText = job.description || 'No description provided.';
        document.getElementById('modal-apply-link').href = job.apply_url || '#';

        // Tri-Validator Consensus Panel
        const details = job.validator_details || {};
        const vGemini = details.gemini || {};
        const vMl = details.ml_vector || {};
        const vPref = details.preference || {};

        if (document.getElementById('modal-validators-consensus')) {
            const passed = job.validators_passed !== undefined ? job.validators_passed : 0;
            const badgeClass = passed === 3 ? 'bg-emerald-100 text-emerald-800 border-emerald-300' : (passed === 2 ? 'bg-blue-100 text-blue-800 border-blue-200' : 'bg-slate-100 text-slate-700');
            document.getElementById('modal-validators-consensus').className = `px-2 py-0.5 rounded-full text-[10px] font-black border ${badgeClass}`;
            document.getElementById('modal-validators-consensus').innerText = `${passed}/3 Validators Verified`;
        }

        if (document.getElementById('modal-v-gemini-score')) {
            const gScore = job.gemini_score || vGemini.score || 0;
            document.getElementById('modal-v-gemini-score').innerText = `${gScore}%`;
            document.getElementById('modal-v-gemini-status').innerText = (gScore >= 70 || vGemini.passed) ? '✅ Approved' : '⚠️ Marginal';
        }
        if (document.getElementById('modal-v-ml-score')) {
            const mScore = job.ml_score || vMl.score || 0;
            document.getElementById('modal-v-ml-score').innerText = `${mScore}%`;
            document.getElementById('modal-v-ml-status').innerText = (mScore >= 65 || vMl.passed) ? '✅ Approved' : '⚠️ Marginal';
        }
        if (document.getElementById('modal-v-pref-score')) {
            const pScore = job.preference_score || vPref.score || 0;
            document.getElementById('modal-v-pref-score').innerText = `${pScore}%`;
            document.getElementById('modal-v-pref-status').innerText = (pScore >= 70 || vPref.passed) ? '✅ Approved' : '❌ Flagged';
        }

        // Checks and red flags
        const checksEl = document.getElementById('modal-validator-checks');
        if (checksEl) {
            const checksList = vPref.checks_passed || [];
            const redFlags = vPref.red_flags || [];
            let html = '';
            if (checksList.length > 0) {
                html += checksList.map(c => `<div class="flex items-center gap-1.5 text-emerald-700 font-medium"><span>✓</span><span>${c}</span></div>`).join('');
            }
            if (redFlags.length > 0) {
                html += redFlags.map(r => `<div class="flex items-center gap-1.5 text-rose-600 font-semibold"><span>⚠</span><span>${r}</span></div>`).join('');
            }
            if (vMl.cosine_similarity) {
                html += `<div class="flex items-center gap-1.5 text-indigo-600"><span>≈</span><span>Vector TF-IDF Cosine Similarity: ${(vMl.cosine_similarity * 100).toFixed(1)}%</span></div>`;
            }
            checksEl.innerHTML = html || '<div class="text-slate-400">All 3 automated validators evaluated this role.</div>';
        }

        // Reasons
        const reasonsEl = document.getElementById('modal-reasons');
        reasonsEl.innerHTML = (job.match_reasons || []).map(r => `<li>${r}</li>`).join('') || '<li>Matched via profile qualification criteria.</li>';

        // Matched Skills
        const matchedEl = document.getElementById('modal-matched-skills');
        matchedEl.innerHTML = (job.matched_skills || []).map(s => 
            `<span class="px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 text-[10px] font-bold">${s}</span>`
        ).join('') || '<span class="text-slate-400">Standard Computer Engineering skillset</span>';

        // Missing Skills
        const missingEl = document.getElementById('modal-missing-skills');
        missingEl.innerHTML = (job.missing_skills || []).map(s => 
            `<span class="px-2 py-0.5 rounded bg-amber-100 text-amber-800 text-[10px] font-bold">${s}</span>`
        ).join('') || '<span class="text-slate-400">None identified</span>';

        const modal = document.getElementById('job-modal');
        modal.classList.remove('hidden');
        modal.classList.add('flex');
        if (window.lucide) lucide.createIcons();
    } catch (e) {
        console.error('Error opening job modal:', e);
    }
}

function closeJobModal() {
    const modal = document.getElementById('job-modal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
}

async function toggleJobStatus(jobId, status) {
    try {
        await fetch(`${API_BASE}/api/jobs/${jobId}/status`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({status})
        });
        closeJobModal();
        fetchJobs();
        loadStats();
    } catch (e) {
        console.error('Error updating status:', e);
    }
}

async function markApplied(e, jobId) {
    if (e) e.stopPropagation();
    try {
        await fetch(`${API_BASE}/api/jobs/${jobId}/status`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({status: 'applied'})
        });
        fetchJobs();
        loadStats();
    } catch (err) {
        console.error('Error marking applied:', err);
    }
}

async function dismissJob(e, jobId) {
    if (e) e.stopPropagation();
    const card = document.getElementById(`job-card-${jobId}`);
    if (card) {
        card.style.transition = 'all 0.3s ease';
        card.style.opacity = '0';
        card.style.transform = 'scale(0.95)';
    }
    try {
        await fetch(`${API_BASE}/api/jobs/${jobId}/status`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({status: 'dismissed'})
        });
        setTimeout(() => {
            fetchJobs();
            loadStats();
        }, 300);
    } catch (err) {
        console.error('Error dismissing job:', err);
    }
}

async function restoreJob(e, jobId) {
    if (e) e.stopPropagation();
    try {
        await fetch(`${API_BASE}/api/jobs/${jobId}/status`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({status: 'new'})
        });
        fetchJobs();
        loadStats();
    } catch (err) {
        console.error('Error restoring job:', err);
    }
}

// Pipeline Execution & Streaming
async function triggerPipelineRun() {
    const btn = document.getElementById('btn-run-pipeline');
    btn.disabled = true;
    btn.classList.add('opacity-75');

    try {
        const res = await fetch(`${API_BASE}/api/pipeline/run`, {method: 'POST'});
        const data = await res.json();
        
        switchTab('phases');
        startSSEStream();
    } catch (e) {
        console.error('Error triggering pipeline:', e);
        btn.disabled = false;
        btn.classList.remove('opacity-75');
    }
}

function startSSEStream() {
    if (sseConnection) {
        sseConnection.close();
    }

    const consoleLog = document.getElementById('live-console-log');
    const progressBar = document.getElementById('pipeline-progress-bar');
    const percentLabel = document.getElementById('pipeline-percent-label');
    const statusTitle = document.getElementById('pipeline-status-title');
    const statusDesc = document.getElementById('pipeline-status-desc');
    const spinner = document.getElementById('pipeline-spinner');

    spinner.classList.remove('hidden');

    sseConnection = new EventSource(`${API_BASE}/api/pipeline/stream`);

    sseConnection.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);

            progressBar.style.width = `${data.percent}%`;
            percentLabel.innerText = `${data.percent}%`;
            statusTitle.innerText = `Pipeline: Phase ${data.phase_id} - ${data.phase_name}`;
            statusDesc.innerText = data.message;

            // Highlight phase cards
            document.querySelectorAll('.phase-card').forEach((card, idx) => {
                if (idx + 1 === data.phase_id && data.is_running) {
                    card.classList.add('phase-pulse', 'border-blue-500', 'bg-blue-50/50');
                } else {
                    card.classList.remove('phase-pulse', 'border-blue-500', 'bg-blue-50/50');
                }
            });

            // Append logs
            if (data.new_logs && data.new_logs.length) {
                data.new_logs.forEach(line => {
                    const div = document.createElement('div');
                    div.innerText = line;
                    consoleLog.appendChild(div);
                });
                consoleLog.scrollTop = consoleLog.scrollHeight;
            }

            if (!data.is_running && data.percent === 100) {
                spinner.classList.add('hidden');
                document.getElementById('btn-run-pipeline').disabled = false;
                document.getElementById('btn-run-pipeline').classList.remove('opacity-75');
                sseConnection.close();
                loadStats();
                fetchJobs();
            }
        } catch (err) {
            console.error('SSE parse error:', err);
        }
    };

    sseConnection.onerror = () => {
        spinner.classList.add('hidden');
        document.getElementById('btn-run-pipeline').disabled = false;
        document.getElementById('btn-run-pipeline').classList.remove('opacity-75');
        if (sseConnection) sseConnection.close();
    };
}

async function pollPipelineStatus() {
    try {
        const res = await fetch(`${API_BASE}/api/pipeline/status`);
        const data = await res.json();
        if (data.is_running) {
            startSSEStream();
        }
    } catch (e) {
        console.error('Error polling status:', e);
    }
}

function clearConsoleLog() {
    document.getElementById('live-console-log').innerHTML = '<div class="text-slate-600">// Live log cleared.</div>';
}

// Settings & Profile
async function loadSettings() {
    try {
        const res = await fetch(`${API_BASE}/api/settings`);
        const data = await res.json();

        document.getElementById('header-schedule-time').innerText = `${data.daily_run_time} AM`;
        document.getElementById('input-schedule-time').value = data.daily_run_time || '08:00';
        document.getElementById('input-user-email').value = data.user_email || 'gamboa.khinandrei@gmail.com';
        
        if (data.has_gemini_key) {
            document.getElementById('input-gemini-key').placeholder = '●●●●●●●●●●●●●●●● (Configured)';
        }
        if (data.has_smtp_password) {
            document.getElementById('input-smtp-password').placeholder = '●●●●●●●●●●●●●●●● (Configured)';
        }
    } catch (e) {
        console.error('Error loading settings:', e);
    }
}

async function saveSettings() {
    const geminiKey = document.getElementById('input-gemini-key').value.trim();
    const smtpPass = document.getElementById('input-smtp-password').value.trim();
    const scheduleTime = document.getElementById('input-schedule-time').value.trim();
    const statusMsg = document.getElementById('settings-status-msg');

    statusMsg.innerText = 'Saving configuration...';

    const payload = {};
    if (geminiKey) payload.gemini_api_key = geminiKey;
    if (smtpPass) payload.smtp_password = smtpPass;
    if (scheduleTime) payload.daily_run_time = scheduleTime;

    try {
        const res = await fetch(`${API_BASE}/api/settings`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        statusMsg.innerText = data.message || 'Settings updated!';
        statusMsg.classList.add('text-emerald-600');
        loadSettings();
    } catch (e) {
        statusMsg.innerText = 'Error saving settings.';
        statusMsg.classList.add('text-rose-600');
    }
}

async function testEmailNotification() {
    alert('Dispatching test verification email to gamboa.khinandrei@gmail.com...');
    try {
        const res = await fetch(`${API_BASE}/api/email/test`, {method: 'POST'});
        const data = await res.json();
        alert(data.message);
    } catch (e) {
        alert('Failed to send test email: ' + e);
    }
}

function previewEmailDigest() {
    window.open(`${API_BASE}/api/preview/digest`, '_blank');
}

function togglePasswordVisibility(inputId) {
    const input = document.getElementById(inputId);
    input.type = input.type === 'password' ? 'text' : 'password';
}

async function loadProfile() {
    try {
        const res = await fetch(`${API_BASE}/api/profile`);
        const data = await res.json();
        if (data.structured) {
            document.getElementById('profile-name').innerText = data.structured.name;
        }
    } catch (e) {
        console.error('Error loading profile:', e);
    }
}
