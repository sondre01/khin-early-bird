// Khin Early Bird - Interactive Dashboard JS

// If opened via VS Code Live Server (port 5500), route API requests to the Python backend on 8000
const API_BASE = (window.location.port === '5500' || window.location.port === '5501' || window.location.port === '5502') 
    ? 'http://127.0.0.1:8000' 
    : '';

let currentFilterJobType = 'all';
let currentModalJobId = null;
let sseConnection = null;
let statsLoaded = false;
let jobsLoaded = false;
let profileLoaded = false;

// URL Sanitizer & Platform Resolver (Prevents 404s like "We can't find this page")
function getCleanApplyUrl(job) {
    const raw = (job.apply_url || '').trim();
    const source = (job.source || '').toLowerCase();
    const cleanCompany = (job.company || '').replace(/[()[\]{}]/g, '').trim();
    const cleanTitle = (job.title || '').replace(/[()[\]{}]/g, '').trim();
    const query = encodeURIComponent(`${cleanCompany} ${cleanTitle}`);

    if (source.includes('indeed') || raw.includes('indeed.com')) {
        const jkMatch = raw.match(/[?&]jk=([a-fA-F0-9]{16})\b/);
        if (jkMatch) return `https://ph.indeed.com/viewjob?jk=${jkMatch[1]}`;
        return `https://ph.indeed.com/jobs?q=${query}&l=Philippines`;
    }
    if (source.includes('jobstreet') || raw.includes('jobstreet.com')) {
        const idMatch = raw.match(/\/job(?:s)?\/(\d{6,12})\b/);
        if (idMatch) return `https://ph.jobstreet.com/job/${idMatch[1]}`;
        return `https://ph.jobstreet.com/jobs?keywords=${query}`;
    }
    if (source.includes('linkedin') || raw.includes('linkedin.com')) {
        const viewMatch = raw.match(/\/jobs\/view\/(?:[a-zA-Z0-9\-]+-)?(\d{8,14})\b/);
        if (viewMatch) return `https://ph.linkedin.com/jobs/view/${viewMatch[1]}`;
        if (raw.includes('linkedin.com/jobs/view')) return raw.split('?')[0];
        return `https://www.linkedin.com/jobs/search/?keywords=${query}&location=Philippines`;
    }
    if (raw && raw.startsWith('http') && !raw.endsWith('#')) return raw;
    return `https://www.google.com/search?q=${query}+apply+Philippines`;
}

function getGoogleJobsUrl(job) {
    const cleanCompany = (job.company || '').replace(/[()[\]{}]/g, '').trim();
    const cleanTitle = (job.title || '').replace(/[()[\]{}]/g, '').trim();
    return `https://www.google.com/search?q=${encodeURIComponent(cleanCompany + ' ' + cleanTitle + ' apply Philippines')}`;
}

function getLinkedInSearchUrl(job) {
    const cleanCompany = (job.company || '').replace(/[()[\]{}]/g, '').trim();
    const cleanTitle = (job.title || '').replace(/[()[\]{}]/g, '').trim();
    return `https://www.linkedin.com/jobs/search/?keywords=${encodeURIComponent(cleanCompany + ' ' + cleanTitle)}&location=Philippines`;
}

function initApp() {
    loadStats();
    fetchJobs();
    loadSettings();
    pollPipelineStatus();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initApp);
} else {
    initApp();
}

// Tab Navigation
function switchTab(tabId) {
    document.querySelectorAll('.tab-pane').forEach(el => el.classList.add('hidden'));
    const target = document.getElementById(`tab-${tabId}`);
    if (target) target.classList.remove('hidden');

    document.querySelectorAll('.nav-tab').forEach(btn => {
        btn.classList.remove('bg-white', 'text-black', 'shadow-xs');
        btn.classList.add('text-zinc-400');
    });

    const activeNav = document.getElementById(`nav-${tabId}`);
    if (activeNav) {
        activeNav.classList.add('bg-white', 'text-black', 'shadow-xs');
        activeNav.classList.remove('text-zinc-400');
    }

    // Only load if not yet loaded; prevents harsh refetches & flickering when toggling tabs
    if (tabId === 'dashboard' && !statsLoaded) loadStats();
    if (tabId === 'jobs' && !jobsLoaded) fetchJobs();
    if (tabId === 'profile' && !profileLoaded) loadProfile();
}

// Stats & Overview
async function loadStats() {
    try {
        const res = await fetch(`${API_BASE}/api/stats`);
        const data = await res.json();
        statsLoaded = true;

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
                <div class="space-y-1.5">
                    <div class="flex justify-between text-xs font-medium text-zinc-300">
                        <span>${label}</span>
                        <span class="text-zinc-200 font-mono text-[11px]">${count} roles</span>
                    </div>
                    <div class="w-full bg-zinc-800/80 rounded-full h-1.5 overflow-hidden">
                        <div class="bg-zinc-200 h-1.5 rounded-full" style="width: ${pct}%"></div>
                    </div>
                </div>`;
            }
            breakdownContainer.innerHTML = html || '<p class="text-xs text-zinc-500">No role records yet.</p>';
        }

        // Load Top Jobs preview for dashboard
        loadTopJobsPreview();
    } catch (e) {
        console.error('Error loading stats:', e);
    }
}

async function loadTopJobsPreview() {
    try {
        const container = document.getElementById('dashboard-top-jobs');
        if (!container) return;

        const res = await fetch(`${API_BASE}/api/jobs?limit=6&min_score=80&location=ncr`);
        const data = await res.json();

        if (!data.jobs || data.jobs.length === 0) {
            container.innerHTML = `<div class="col-span-3 text-center py-6 text-xs text-zinc-500">No jobs scored above 80% yet. Run the scraper to discover opportunities.</div>`;
            return;
        }

        container.innerHTML = data.jobs.map(j => renderJobCard(j)).join('');
        if (window.lucide) {
            lucide.createIcons({ root: container });
        }
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
    const location = document.getElementById('filter-location') ? document.getElementById('filter-location').value : 'ncr';
    const sortBy = document.getElementById('filter-sort') ? document.getElementById('filter-sort').value : 'recent';
    const hideApplied = document.getElementById('toggle-hide-applied') ? document.getElementById('toggle-hide-applied').checked : false;
    const posted = document.getElementById('filter-posted') ? document.getElementById('filter-posted').value : 'all';
    const search = document.getElementById('search-input').value.trim();

    let url = `${API_BASE}/api/jobs?job_type=${encodeURIComponent(currentFilterJobType)}&sort_by=${encodeURIComponent(sortBy)}`;
    if (category !== 'all') url += `&role_category=${encodeURIComponent(category)}`;
    if (source !== 'all') url += `&source=${encodeURIComponent(source)}`;
    if (location && location !== 'all') url += `&location=${encodeURIComponent(location)}`;
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
        jobsLoaded = true;
        const container = document.getElementById('jobs-container');
        const emptyState = document.getElementById('jobs-empty');

        if (!data.jobs || data.jobs.length === 0) {
            container.innerHTML = '';
            emptyState.classList.remove('hidden');
        } else {
            emptyState.classList.add('hidden');
            container.innerHTML = data.jobs.map(j => renderJobCard(j)).join('');
        }
        if (window.lucide && container) {
            lucide.createIcons({ root: container });
        }
    } catch (e) {
        console.error('Error fetching jobs:', e);
    }
}

function renderJobCard(job) {
    const score = job.match_score || 0;
    const isHigh = score >= 80;
    const isMod = score >= 60;

    // Minimalist score badge: crisp white for high match, clean neutral grey for moderate
    const scoreBadge = isHigh 
        ? `<span class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-white text-black shadow-xs tracking-tight">${score}% Fit</span>`
        : (isMod 
            ? `<span class="px-2.5 py-0.5 rounded-full text-xs font-medium bg-zinc-800 text-zinc-200 border border-zinc-700">${score}% Fit</span>`
            : `<span class="px-2.5 py-0.5 rounded-full text-xs font-medium bg-zinc-900 text-zinc-500 border border-zinc-800">${score}%</span>`);

    const isIntern = job.job_type === 'Internship';
    const typeBadge = isIntern 
        ? `<span class="px-2 py-0.5 rounded text-[10px] font-mono bg-zinc-900 text-zinc-400 border border-zinc-800">Internship</span>`
        : `<span class="px-2 py-0.5 rounded text-[10px] font-mono bg-zinc-800 text-zinc-200 border border-zinc-700/80">Regular</span>`;

    const freshGradBadge = (job.is_explicit_fresh_grad || isIntern)
        ? `<span class="px-2 py-0.5 rounded text-[10px] font-mono bg-emerald-950/70 text-emerald-300 border border-emerald-800/80">🎓 0 Exp / Fresh Grad</span>`
        : `<span class="px-2 py-0.5 rounded text-[10px] font-mono bg-zinc-900 text-zinc-400 border border-zinc-800">Entry Tier</span>`;

    const roleName = (job.role_category || '').replace('_', ' ').toUpperCase();

    const skills = (job.matched_skills || []).slice(0, 3).map(s => 
        `<span class="px-2 py-0.5 rounded bg-zinc-900 text-zinc-300 text-[10px] border border-zinc-800/80 font-mono">${s}</span>`
    ).join('');

    const statusBadge = job.status === 'applied' 
        ? `<span class="px-2 py-0.5 rounded bg-zinc-800 text-zinc-200 text-[10px] font-mono border border-zinc-700">✓ Applied</span>`
        : (job.status === 'saved' ? `<span class="px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 text-[10px] font-mono border border-zinc-700">★ Saved</span>` 
        : (job.status === 'dismissed' ? `<span class="px-2 py-0.5 rounded bg-zinc-900 text-zinc-500 text-[10px] font-mono border border-zinc-800 line-through">Hidden</span>` : ''));

    const hideOrRestoreBtn = job.status === 'dismissed'
        ? `<button onclick="restoreJob(event, '${job.id}')" title="Restore Opportunity" class="p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-800 transition"><i data-lucide="rotate-ccw" class="w-4 h-4"></i></button>`
        : `<button onclick="dismissJob(event, '${job.id}')" title="Hide / Cancel Out" class="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 transition"><i data-lucide="eye-off" class="w-4 h-4"></i></button>`;

    const vPassed = job.validators_passed !== undefined ? job.validators_passed : 0;
    const consensusBadge = vPassed >= 2 
        ? `<span class="px-1.5 py-0.5 rounded text-[10px] font-mono text-zinc-400 border border-zinc-800">${vPassed}/3 Verified</span>`
        : '';

    return `
    <div id="job-card-${job.id}" class="bg-[#121316] rounded-2xl border border-zinc-800/90 hover:border-zinc-600/70 p-5 shadow-sm hover:shadow-lg transition-all duration-200 flex flex-col justify-between group">
        <div class="space-y-3">
            <div class="flex items-start justify-between gap-2">
                <div class="flex flex-wrap items-center gap-1.5">
                    <span class="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-zinc-800/80 text-zinc-300 border border-zinc-700/60">${job.source}</span>
                    ${typeBadge}
                    ${freshGradBadge}
                    <span class="px-2 py-0.5 rounded text-[10px] font-medium text-zinc-400 border border-zinc-800">${roleName}</span>
                    ${consensusBadge}
                    ${statusBadge}
                </div>
                <div class="flex items-center space-x-1">
                    ${scoreBadge}
                    <button onclick="markApplied(event, '${job.id}')" title="${job.status === 'applied' ? 'Already Applied' : 'Mark as Applied'}" class="p-1.5 rounded-lg ${job.status === 'applied' ? 'text-white bg-zinc-800' : 'text-zinc-500 hover:text-white hover:bg-zinc-800'} transition">
                        <i data-lucide="check-circle" class="w-4 h-4"></i>
                    </button>
                    ${hideOrRestoreBtn}
                </div>
            </div>

            <div>
                <h3 class="font-semibold text-sm text-zinc-100 group-hover:text-white transition line-clamp-2 leading-snug">${job.title}</h3>
                <p class="text-xs text-zinc-400 mt-1 flex items-center gap-1.5 flex-wrap">
                    <span class="font-medium text-zinc-300">${job.company}</span>
                    <span class="text-zinc-600">&bull;</span>
                    <span>${job.location}</span>
                    <span class="text-zinc-600">&bull;</span>
                    <span class="text-zinc-400 font-mono text-[11px]">${job.work_type}</span>
                </p>

                <!-- Minimalist Metadata Row -->
                <div class="flex items-center gap-2 mt-2.5 text-[10px] font-mono text-zinc-400 bg-zinc-900/60 border border-zinc-800/80 px-2.5 py-1 rounded-lg">
                    <span>AI: ${job.gemini_score || 0}%</span>
                    <span class="text-zinc-700">&bull;</span>
                    <span>ML: ${job.ml_score || 0}%</span>
                    <span class="text-zinc-700">&bull;</span>
                    <span>${job.posted_date || 'Recently'}</span>
                </div>
            </div>

            <!-- Skills Chips -->
            <div class="flex flex-wrap gap-1 pt-0.5">
                ${skills}
            </div>

            <!-- Match Reason Snippet -->
            ${job.match_reasons && job.match_reasons.length ? `
                <div class="p-2.5 rounded-xl bg-zinc-900/50 text-[11px] text-zinc-400 border border-zinc-850/80 line-clamp-2 leading-relaxed">
                    ${job.match_reasons[0]}
                </div>
            ` : ''}
        </div>

        <div class="pt-4 border-t border-zinc-800/80 mt-4 flex items-center justify-between">
            <button onclick="openJobModal('${job.id}')" class="text-xs font-medium text-zinc-400 hover:text-white transition flex items-center gap-1">
                <span>View Details</span>
                <span>&rarr;</span>
            </button>
            <div class="flex items-center space-x-1.5">
                <a href="${getGoogleJobsUrl(job)}" target="_blank" rel="noopener noreferrer" title="Search on Google Jobs" class="text-zinc-500 hover:text-zinc-300 p-1.5 rounded-lg hover:bg-zinc-800 transition text-[11px] font-mono">
                    Google
                </a>
                <a href="${getCleanApplyUrl(job)}" target="_blank" rel="noopener noreferrer" class="bg-white hover:bg-zinc-200 text-black text-xs font-semibold px-3 py-1.5 rounded-lg transition shadow-xs flex items-center gap-1">
                    <span>Apply</span>
                    <span>&rarr;</span>
                </a>
            </div>
        </div>
    </div>
    `;
}

// Segregation Filter Buttons
function setJobTypeFilter(type) {
    currentFilterJobType = type;
    document.querySelectorAll('.seg-btn').forEach(b => {
        b.classList.remove('bg-white', 'text-black', 'shadow-xs');
        b.classList.add('text-zinc-400');
    });

    const activeMap = {
        'all': 'btn-seg-all',
        'Internship': 'btn-seg-intern',
        'Regular': 'btn-seg-regular'
    };
    const activeBtn = document.getElementById(activeMap[type]);
    if (activeBtn) {
        activeBtn.classList.add('bg-white', 'text-black', 'shadow-xs');
        activeBtn.classList.remove('text-zinc-400');
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
        
        // Sanitize outbound apply and search URLs
        document.getElementById('modal-apply-link').href = getCleanApplyUrl(job);
        if (document.getElementById('modal-google-jobs-link')) {
            document.getElementById('modal-google-jobs-link').href = getGoogleJobsUrl(job);
        }
        if (document.getElementById('modal-linkedin-link')) {
            document.getElementById('modal-linkedin-link').href = getLinkedInSearchUrl(job);
        }

        // Tri-Validator Consensus Panel
        const details = job.validator_details || {};
        const vGemini = details.gemini || {};
        const vMl = details.ml_vector || {};
        const vPref = details.preference || {};

        if (document.getElementById('modal-validators-consensus')) {
            const passed = job.validators_passed !== undefined ? job.validators_passed : 0;
            const badgeClass = passed === 3 
                ? 'bg-zinc-800 text-zinc-100 border-zinc-700' 
                : (passed === 2 ? 'bg-zinc-850 text-zinc-300 border-zinc-800' : 'bg-zinc-900 text-zinc-500 border-zinc-850');
            document.getElementById('modal-validators-consensus').className = `px-2.5 py-0.5 rounded-full text-[10px] font-mono border ${badgeClass}`;
            document.getElementById('modal-validators-consensus').innerText = `${passed}/3 Validators Verified`;
        }

        if (document.getElementById('modal-v-gemini-score')) {
            const gScore = job.gemini_score || vGemini.score || 0;
            document.getElementById('modal-v-gemini-score').innerText = `${gScore}%`;
            document.getElementById('modal-v-gemini-status').innerText = (gScore >= 70 || vGemini.passed) ? 'Approved' : 'Marginal';
        }
        if (document.getElementById('modal-v-ml-score')) {
            const mScore = job.ml_score || vMl.score || 0;
            document.getElementById('modal-v-ml-score').innerText = `${mScore}%`;
            document.getElementById('modal-v-ml-status').innerText = (mScore >= 65 || vMl.passed) ? 'Approved' : 'Marginal';
        }
        if (document.getElementById('modal-v-pref-score')) {
            const pScore = job.preference_score || vPref.score || 0;
            document.getElementById('modal-v-pref-score').innerText = `${pScore}%`;
            document.getElementById('modal-v-pref-status').innerText = (pScore >= 70 || vPref.passed) ? 'Approved' : 'Flagged';
        }

        // Checks and red flags
        const checksEl = document.getElementById('modal-validator-checks');
        if (checksEl) {
            const checksList = vPref.checks_passed || [];
            const redFlags = vPref.red_flags || [];
            let html = '';
            if (checksList.length > 0) {
                html += checksList.map(c => `<div class="flex items-center gap-1.5 text-zinc-300"><span>✓</span><span>${c}</span></div>`).join('');
            }
            if (redFlags.length > 0) {
                html += redFlags.map(r => `<div class="flex items-center gap-1.5 text-zinc-400"><span>⚠</span><span>${r}</span></div>`).join('');
            }
            if (vMl.cosine_similarity) {
                html += `<div class="flex items-center gap-1.5 text-zinc-400"><span>≈</span><span>Vector TF-IDF Cosine Similarity: ${(vMl.cosine_similarity * 100).toFixed(1)}%</span></div>`;
            }
            checksEl.innerHTML = html || '<div class="text-zinc-500">All 3 automated validators evaluated this role.</div>';
        }

        // Reasons
        const reasonsEl = document.getElementById('modal-reasons');
        reasonsEl.innerHTML = (job.match_reasons || []).map(r => `<li>${r}</li>`).join('') || '<li>Matched via profile qualification criteria.</li>';

        // Matched Skills
        const matchedEl = document.getElementById('modal-matched-skills');
        matchedEl.innerHTML = (job.matched_skills || []).map(s => 
            `<span class="px-2 py-0.5 rounded bg-zinc-800 text-zinc-200 text-[10px] font-mono border border-zinc-700/80">${s}</span>`
        ).join('') || '<span class="text-zinc-500">Standard Computer Engineering skillset</span>';

        // Missing Skills
        const missingEl = document.getElementById('modal-missing-skills');
        missingEl.innerHTML = (job.missing_skills || []).map(s => 
            `<span class="px-2 py-0.5 rounded bg-zinc-900 text-zinc-400 text-[10px] font-mono border border-zinc-800">${s}</span>`
        ).join('') || '<span class="text-zinc-500">None identified</span>';

        const modal = document.getElementById('job-modal');
        modal.classList.remove('hidden');
        modal.classList.add('flex');
        if (window.lucide) {
            lucide.createIcons({ root: modal });
        }
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

        // Supabase Settings & Status
        const supabaseUrlInput = document.getElementById('input-supabase-url');
        if (supabaseUrlInput && data.supabase_url) {
            supabaseUrlInput.value = data.supabase_url;
        }
        const supabaseKeyInput = document.getElementById('input-supabase-key');
        if (supabaseKeyInput && data.has_supabase_key) {
            supabaseKeyInput.placeholder = '●●●●●●●●●●●●●●●● (Configured)';
        }

        const supabaseBadge = document.getElementById('supabase-status-badge');
        if (supabaseBadge) {
            if (data.is_supabase_configured) {
                supabaseBadge.className = 'px-2.5 py-0.5 rounded-full text-[10px] font-mono border bg-emerald-950/60 text-emerald-400 border-emerald-800/80';
                supabaseBadge.innerText = '● Connected';
            } else {
                supabaseBadge.className = 'px-2.5 py-0.5 rounded-full text-[10px] font-mono border bg-zinc-900 text-zinc-400 border-zinc-800';
                supabaseBadge.innerText = '○ Offline (SQLite)';
            }
        }
    } catch (e) {
        console.error('Error loading settings:', e);
    }
}

async function saveSettings() {
    const geminiKey = document.getElementById('input-gemini-key').value.trim();
    const smtpPass = document.getElementById('input-smtp-password').value.trim();
    const scheduleTime = document.getElementById('input-schedule-time').value.trim();
    const supabaseUrl = document.getElementById('input-supabase-url')?.value.trim();
    const supabaseKey = document.getElementById('input-supabase-key')?.value.trim();
    const statusMsg = document.getElementById('settings-status-msg');

    statusMsg.innerText = 'Saving configuration...';

    const payload = {};
    if (geminiKey) payload.gemini_api_key = geminiKey;
    if (smtpPass) payload.smtp_password = smtpPass;
    if (scheduleTime) payload.daily_run_time = scheduleTime;
    if (supabaseUrl) payload.supabase_url = supabaseUrl;
    if (supabaseKey) payload.supabase_key = supabaseKey;

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

async function syncLocalToSupabase() {
    const btn = document.getElementById('btn-sync-supabase');
    const msg = document.getElementById('supabase-sync-msg');
    if (!btn || !msg) return;

    btn.disabled = true;
    btn.classList.add('opacity-70');
    msg.className = 'text-xs text-zinc-400';
    msg.innerText = 'Syncing local database to Supabase cloud...';

    try {
        const res = await fetch(`${API_BASE}/api/supabase/sync`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            msg.className = 'text-xs text-emerald-400';
            msg.innerText = `✓ Synced: ${data.jobs_synced} jobs, ${data.evals_synced} evaluations uploaded!`;
            loadStats();
            fetchJobs();
            loadSettings();
        } else {
            msg.className = 'text-xs text-rose-400';
            msg.innerText = `✗ Sync failed: ${data.message || 'Unknown error'}`;
        }
    } catch (e) {
        msg.className = 'text-xs text-rose-400';
        msg.innerText = `✗ Sync error: ${e.message}`;
    } finally {
        btn.disabled = false;
        btn.classList.remove('opacity-70');
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
        profileLoaded = true;
        if (data.structured) {
            document.getElementById('profile-name').innerText = data.structured.name;
        }
    } catch (e) {
        console.error('Error loading profile:', e);
    }
}
