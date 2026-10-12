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
let currentStatusView = 'active';

function showToast(msg) {
    let toast = document.getElementById('app-toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'app-toast';
        toast.className = 'fixed bottom-5 right-5 z-50 bg-[#16171B] border border-zinc-700 text-zinc-100 text-xs px-4 py-2.5 rounded-xl shadow-2xl flex items-center space-x-2 transition-all duration-300 opacity-0 transform translate-y-2 pointer-events-none';
        document.body.appendChild(toast);
    }
    toast.innerText = msg;
    toast.classList.remove('opacity-0', 'translate-y-2');
    toast.classList.add('opacity-100', 'translate-y-0');
    setTimeout(() => {
        toast.classList.remove('opacity-100', 'translate-y-0');
        toast.classList.add('opacity-0', 'translate-y-2');
    }, 2800);
}

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

const FILTER_STORAGE_KEY = 'khin_earlybird_filters_v2';
const TAB_STORAGE_KEY = 'khin_earlybird_active_tab';

function syncJobTypeButtons(type) {
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
}

function saveFilterState() {
    try {
        const state = {
            jobType: currentFilterJobType || 'all',
            statusView: currentStatusView || 'active',
            search: document.getElementById('search-input')?.value || '',
            category: document.getElementById('filter-category')?.value || 'all',
            source: document.getElementById('filter-source')?.value || 'all',
            location: document.getElementById('filter-location')?.value || 'ncr',
            score: document.getElementById('filter-score')?.value || '0',
            status: document.getElementById('filter-status')?.value || 'all',
            hideApplied: document.getElementById('toggle-hide-applied') ? document.getElementById('toggle-hide-applied').checked : true,
            posted: document.getElementById('filter-posted')?.value || 'all',
            sort: document.getElementById('filter-sort')?.value || 'recent'
        };
        localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(state));
    } catch (e) {
        console.warn('Could not save filter state to localStorage:', e);
    }
}

function restoreFilterState() {
    try {
        const raw = localStorage.getItem(FILTER_STORAGE_KEY);
        if (!raw) return;
        const state = JSON.parse(raw);
        if (!state || typeof state !== 'object') return;

        // 1. Segregation Job Type
        if (state.jobType) {
            currentFilterJobType = state.jobType;
            syncJobTypeButtons(state.jobType);
        }

        // 2. Feed Status View
        if (state.statusView) {
            currentStatusView = state.statusView;
            syncStatusViewButtons(state.statusView);
            const hintEl = document.getElementById('feed-status-hint');
            if (hintEl) {
                const hintMap = {
                    'active': 'Showing unapplied opportunities (applied roles automatically archived)',
                    'applied': 'Your application history (roles you have applied to)',
                    'saved': 'Your bookmarked opportunities',
                    'all': 'Showing all listings including applied and saved'
                };
                if (hintMap[state.statusView]) hintEl.innerText = hintMap[state.statusView];
            }
        }

        // 3. Dropdowns & Inputs
        if (state.search !== undefined && document.getElementById('search-input')) {
            document.getElementById('search-input').value = state.search;
        }
        if (state.category && document.getElementById('filter-category')) {
            document.getElementById('filter-category').value = state.category;
        }
        if (state.source && document.getElementById('filter-source')) {
            document.getElementById('filter-source').value = state.source;
        }
        if (state.location && document.getElementById('filter-location')) {
            document.getElementById('filter-location').value = state.location;
        }
        if (state.score && document.getElementById('filter-score')) {
            document.getElementById('filter-score').value = state.score;
        }
        if (state.status && document.getElementById('filter-status')) {
            document.getElementById('filter-status').value = state.status;
        }
        if (state.hideApplied !== undefined && document.getElementById('toggle-hide-applied')) {
            document.getElementById('toggle-hide-applied').checked = Boolean(state.hideApplied);
        }
        if (state.posted && document.getElementById('filter-posted')) {
            document.getElementById('filter-posted').value = state.posted;
        }
        if (state.sort && document.getElementById('filter-sort')) {
            document.getElementById('filter-sort').value = state.sort;
        }
    } catch (e) {
        console.warn('Could not restore filter state from localStorage:', e);
    }
}

function setupFilterAutoSave() {
    const filterIds = [
        'filter-category',
        'filter-source',
        'filter-location',
        'filter-score',
        'filter-status',
        'filter-posted',
        'filter-sort',
        'toggle-hide-applied'
    ];
    filterIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('change', () => {
                saveFilterState();
            });
        }
    });

    const searchEl = document.getElementById('search-input');
    if (searchEl) {
        searchEl.addEventListener('input', () => {
            saveFilterState();
        });
    }
}

function initApp() {
    const savedTab = localStorage.getItem(TAB_STORAGE_KEY);
    if (savedTab && savedTab !== 'dashboard') {
        switchTab(savedTab);
    }

    checkAuthState();
    restoreFilterState();
    setupFilterAutoSave();
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

    try {
        localStorage.setItem(TAB_STORAGE_KEY, tabId);
    } catch (e) {}

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

        if (document.getElementById('badge-applied-count')) {
            document.getElementById('badge-applied-count').innerText = data.applied_jobs || 0;
        }

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

        const res = await fetch(`${API_BASE}/api/jobs?limit=6&min_score=80&location=ncr&hide_applied=true`);
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
    saveFilterState();

    const category = document.getElementById('filter-category')?.value || 'all';
    const source = document.getElementById('filter-source')?.value || 'all';
    const score = document.getElementById('filter-score')?.value || '0';
    const status = document.getElementById('filter-status')?.value || 'all';
    const location = document.getElementById('filter-location') ? document.getElementById('filter-location').value : 'ncr';
    const sortBy = document.getElementById('filter-sort') ? document.getElementById('filter-sort').value : 'recent';
    const hideApplied = document.getElementById('toggle-hide-applied') ? document.getElementById('toggle-hide-applied').checked : true;
    const posted = document.getElementById('filter-posted') ? document.getElementById('filter-posted').value : 'all';
    const search = (document.getElementById('search-input')?.value || '').trim();

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
    if (status === 'applied') {
        url += `&status=applied`;
    } else {
        if (status !== 'all') url += `&status=${encodeURIComponent(status)}`;
        if (hideApplied) url += `&hide_applied=true`;
    }
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
        ? `<span class="px-2 py-0.5 rounded bg-emerald-950/70 text-emerald-300 text-[10px] font-mono border border-emerald-800/80">✓ Applied</span>`
        : (job.status === 'saved' ? `<span class="px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 text-[10px] font-mono border border-zinc-700">★ Saved</span>` 
        : (job.status === 'dismissed' ? `<span class="px-2 py-0.5 rounded bg-zinc-900 text-zinc-500 text-[10px] font-mono border border-zinc-800 line-through">Hidden</span>` : ''));

    const hideOrRestoreBtn = job.status === 'dismissed'
        ? `<button onclick="restoreJob(event, '${job.id}')" title="Restore Opportunity" class="p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-800 transition"><i data-lucide="rotate-ccw" class="w-4 h-4"></i></button>`
        : `<button onclick="dismissJob(event, '${job.id}')" title="Hide / Cancel Out" class="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 transition"><i data-lucide="eye-off" class="w-4 h-4"></i></button>`;

    const appliedCheckBtn = job.status === 'applied'
        ? `<button onclick="unmarkApplied(event, '${job.id}')" title="Applied. Click to undo and restore to Active feed." class="p-1.5 rounded-lg text-emerald-400 bg-emerald-950/70 border border-emerald-800/80 transition"><i data-lucide="check-circle-2" class="w-4 h-4"></i></button>`
        : `<button onclick="handleApplyClick(event, '${job.id}')" title="Mark as Applied" class="p-1.5 rounded-lg text-zinc-500 hover:text-white hover:bg-zinc-800 transition"><i data-lucide="check-circle" class="w-4 h-4"></i></button>`;

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
                    ${appliedCheckBtn}
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
                ${job.status === 'applied' ? `
                <button onclick="unmarkApplied(event, '${job.id}')" title="Move back to Active Openings" class="text-zinc-400 hover:text-zinc-200 text-xs px-2.5 py-1.5 rounded-lg border border-zinc-800 hover:bg-zinc-800 transition">
                    Undo
                </button>
                <a href="${getCleanApplyUrl(job)}" target="_blank" rel="noopener noreferrer" class="bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 text-xs font-semibold px-3 py-1.5 rounded-lg transition shadow-xs flex items-center gap-1">
                    <span>Re-visit</span>
                    <span>&rarr;</span>
                </a>
                ` : `
                <a href="${getCleanApplyUrl(job)}" target="_blank" rel="noopener noreferrer" onclick="handleApplyClick(event, '${job.id}')" class="bg-white hover:bg-zinc-200 text-black text-xs font-semibold px-3 py-1.5 rounded-lg transition shadow-xs flex items-center gap-1">
                    <span>Apply</span>
                    <span>&rarr;</span>
                </a>
                `}
            </div>
        </div>
    </div>
    `;
}

// Feed / Status View Filter (Active Openings, Applied History, Bookmarked, All)
function setStatusView(view) {
    currentStatusView = view;
    syncStatusViewButtons(view);

    const statusDropdown = document.getElementById('filter-status');
    const hideAppliedCheckbox = document.getElementById('toggle-hide-applied');
    const hintEl = document.getElementById('feed-status-hint');

    if (view === 'active') {
        if (statusDropdown) statusDropdown.value = 'all';
        if (hideAppliedCheckbox) hideAppliedCheckbox.checked = true;
        if (hintEl) hintEl.innerText = 'Showing unapplied opportunities (applied roles automatically archived)';
    } else if (view === 'applied') {
        if (statusDropdown) statusDropdown.value = 'applied';
        if (hideAppliedCheckbox) hideAppliedCheckbox.checked = false;
        if (hintEl) hintEl.innerText = 'Your application history (roles you have applied to)';
    } else if (view === 'saved') {
        if (statusDropdown) statusDropdown.value = 'saved';
        if (hideAppliedCheckbox) hideAppliedCheckbox.checked = false;
        if (hintEl) hintEl.innerText = 'Your bookmarked opportunities';
    } else if (view === 'all') {
        if (statusDropdown) statusDropdown.value = 'all';
        if (hideAppliedCheckbox) hideAppliedCheckbox.checked = false;
        if (hintEl) hintEl.innerText = 'Showing all listings including applied and saved';
    }

    saveFilterState();
    fetchJobs();
}

function handleHideAppliedCheckboxChange() {
    const isChecked = document.getElementById('toggle-hide-applied')?.checked ?? true;
    if (!isChecked && currentStatusView === 'active') {
        currentStatusView = 'all';
        syncStatusViewButtons('all');
    } else if (isChecked && currentStatusView === 'all') {
        currentStatusView = 'active';
        syncStatusViewButtons('active');
    }
    saveFilterState();
    fetchJobs();
}

function syncStatusViewButtons(view) {
    document.querySelectorAll('.status-view-btn').forEach(b => {
        b.classList.remove('bg-white', 'text-black', 'shadow-xs');
        b.classList.add('text-zinc-400');
    });
    const activeMap = {
        'active': 'btn-view-active',
        'applied': 'btn-view-applied',
        'saved': 'btn-view-saved',
        'all': 'btn-view-all'
    };
    const activeBtn = document.getElementById(activeMap[view]);
    if (activeBtn) {
        activeBtn.classList.add('bg-white', 'text-black', 'shadow-xs');
        activeBtn.classList.remove('text-zinc-400');
    }
}

// Segregation Filter Buttons
function setJobTypeFilter(type) {
    currentFilterJobType = type;
    syncJobTypeButtons(type);
    saveFilterState();
    fetchJobs();
}

function filterByJobType(type) {
    switchTab('jobs');
    setJobTypeFilter(type);
}

let searchDebounceTimer = null;
function handleSearchKey(e) {
    if (e.key === 'Enter') {
        clearTimeout(searchDebounceTimer);
        saveFilterState();
        fetchJobs();
        return;
    }
    clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(() => {
        saveFilterState();
        fetchJobs();
    }, 400);
}

function resetFilters() {
    try {
        localStorage.removeItem(FILTER_STORAGE_KEY);
    } catch (e) {}

    if (document.getElementById('filter-category')) document.getElementById('filter-category').value = 'all';
    if (document.getElementById('filter-source')) document.getElementById('filter-source').value = 'all';
    if (document.getElementById('filter-score')) document.getElementById('filter-score').value = '0';
    if (document.getElementById('filter-status')) document.getElementById('filter-status').value = 'all';
    if (document.getElementById('filter-location')) document.getElementById('filter-location').value = 'ncr';
    if (document.getElementById('filter-posted')) document.getElementById('filter-posted').value = 'all';
    if (document.getElementById('filter-sort')) document.getElementById('filter-sort').value = 'recent';
    if (document.getElementById('search-input')) document.getElementById('search-input').value = '';
    
    currentFilterJobType = 'all';
    syncJobTypeButtons('all');

    currentStatusView = 'active';
    syncStatusViewButtons('active');

    const toggleHideApplied = document.getElementById('toggle-hide-applied');
    if (toggleHideApplied) toggleHideApplied.checked = true;

    const hintEl = document.getElementById('feed-status-hint');
    if (hintEl) hintEl.innerText = 'Showing unapplied opportunities (applied roles automatically archived)';

    saveFilterState();
    showToast('Filters reset to default');
    fetchJobs();
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

        if (document.getElementById('modal-apply-btn-text')) {
            document.getElementById('modal-apply-btn-text').innerText = (job.status === 'applied') ? 'Re-visit Posting' : 'Apply on Site';
        }

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

async function handleApplyClick(e, jobId) {
    const card = document.getElementById(`job-card-${jobId}`);
    const hideApplied = document.getElementById('toggle-hide-applied') ? document.getElementById('toggle-hide-applied').checked : true;
    const isFilteredActive = currentStatusView === 'active' || hideApplied;

    if (card && isFilteredActive) {
        card.style.transition = 'all 0.35s ease';
        card.style.opacity = '0';
        card.style.transform = 'scale(0.95)';
        setTimeout(() => {
            card.remove();
            const container = document.getElementById('jobs-container');
            if (container && container.children.length === 0) {
                const emptyState = document.getElementById('jobs-empty');
                if (emptyState) emptyState.classList.remove('hidden');
            }
        }, 350);
    }

    try {
        await fetch(`${API_BASE}/api/jobs/${jobId}/status`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({status: 'applied'})
        });
        showToast('✓ Marked as Applied & moved to Application History');
        loadStats();
        if (!isFilteredActive) {
            fetchJobs();
        }
    } catch (err) {
        console.error('Error auto-marking applied:', err);
    }
}

async function handleModalApplyClick(e) {
    if (currentModalJobId) {
        await handleApplyClick(null, currentModalJobId);
        closeJobModal();
    }
}

async function unmarkApplied(e, jobId) {
    if (e) e.stopPropagation();
    try {
        await fetch(`${API_BASE}/api/jobs/${jobId}/status`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({status: 'new'})
        });
        showToast('Restored opportunity back to Active Openings');
        fetchJobs();
        loadStats();
    } catch (err) {
        console.error('Error unmarking applied:', err);
    }
}

async function markApplied(e, jobId) {
    if (e) e.stopPropagation();
    await handleApplyClick(e, jobId);
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

// =====================================================================
// AUTHENTICATION, COVER PAGE & PREFERENCES ENGINE
// =====================================================================

const AUTH_TOKEN_KEY = 'earlybird_auth_token';
let currentUser = null;
let currentPendingEmail = '';

function getAuthHeaders() {
    const token = localStorage.getItem(AUTH_TOKEN_KEY);
    const headers = { 'Content-Type': 'application/json' };
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    return headers;
}

// 1. Cover Page Lift-up & Navigation
function liftCoverPage() {
    const overlay = document.getElementById('cover-page-overlay');
    if (overlay) {
        overlay.classList.add('lifted');
    }
    sessionStorage.setItem('cover_page_lifted', 'true');
    // If not authenticated, ensure auth portal is visible underneath
    if (!currentUser) {
        const portal = document.getElementById('auth-portal-overlay');
        if (portal) portal.classList.remove('hidden');
    }
}

function lowerCoverPage() {
    const overlay = document.getElementById('cover-page-overlay');
    if (overlay) {
        overlay.classList.remove('lifted');
        overlay.style.transition = '';
        overlay.style.transform = '';
        overlay.style.visibility = '';
        overlay.style.pointerEvents = '';
    }
    document.documentElement.classList.remove('session-active');
    sessionStorage.removeItem('cover_page_lifted');
}

function handleCoverPageClick(event) {
    if (event.target.closest('button, a, input, textarea, select')) return;
    liftCoverPage();
}

// 2. Fixated Username Live Generator
function generateFixatedUsername(fullName) {
    if (!fullName) return '';
    const cleaned = fullName.replace(/[^a-zA-Z\s]/g, '').trim();
    const parts = cleaned.split(/\s+/).filter(Boolean);
    if (!parts.length) return '';
    const first = parts[0].toLowerCase();
    const initials = parts.slice(1).map(p => p[0].toLowerCase()).join('');
    return `${first}${initials}`;
}

function handleFullNameInput(val) {
    const username = generateFixatedUsername(val);
    const badge = document.getElementById('signup-username-badge');
    if (badge) {
        badge.innerText = username ? `@${username}` : '@username';
    }
}

// 3. Auth Tabs
function switchAuthTab(tab) {
    const signinBtn = document.getElementById('auth-tab-signin');
    const signupBtn = document.getElementById('auth-tab-signup');
    const signinForm = document.getElementById('auth-form-signin');
    const signupForm = document.getElementById('auth-form-signup');

    if (tab === 'signin') {
        signinBtn.className = 'flex-1 py-1.5 rounded-lg text-black bg-white shadow-xs transition font-semibold';
        signupBtn.className = 'flex-1 py-1.5 rounded-lg text-zinc-400 hover:text-white transition font-medium';
        signinForm.classList.remove('hidden');
        signupForm.classList.add('hidden');
    } else {
        signupBtn.className = 'flex-1 py-1.5 rounded-lg text-black bg-white shadow-xs transition font-semibold';
        signinBtn.className = 'flex-1 py-1.5 rounded-lg text-zinc-400 hover:text-white transition font-medium';
        signinForm.classList.add('hidden');
        signupForm.classList.remove('hidden');
    }
}

// 4. Sign In Logic
async function handleSignIn() {
    const identifier = document.getElementById('signin-identifier')?.value.trim();
    const password = document.getElementById('signin-password')?.value.trim();
    const errorEl = document.getElementById('signin-error');
    const btn = document.getElementById('btn-submit-signin');

    if (!identifier || !password) {
        if (errorEl) {
            errorEl.innerText = 'Please enter both email/username and password.';
            errorEl.classList.remove('hidden');
        }
        return;
    }

    if (errorEl) errorEl.classList.add('hidden');
    if (btn) {
        btn.disabled = true;
        btn.innerText = 'Signing in...';
    }

    try {
        const res = await fetch(`${API_BASE}/api/auth/sign-in`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ identifier, password })
        });
        const data = await res.json();

        if (res.ok && data.success) {
            localStorage.setItem(AUTH_TOKEN_KEY, data.token);
            if (data.user && data.user.email !== 'gamboa.khinandrei@gmail.com') {
                localStorage.setItem('visitor_auth_token', data.token);
            }
            currentUser = data.user;
            updateUserHeaderUI(currentUser);
            document.getElementById('auth-portal-overlay')?.classList.add('hidden');
            document.getElementById('main-navbar')?.classList.remove('hidden');
            liftCoverPage();
            showToast(`Welcome back, ${currentUser.full_name}!`);
            loadPreferences();
        } else if (data.requires_verification) {
            currentPendingEmail = data.email;
            switchAuthTab('signup');
            showSignupStep(2);
            document.getElementById('otp-target-email').innerText = data.email;
            showToast(data.message);
        } else {
            if (errorEl) {
                errorEl.innerText = data.detail || data.message || 'Invalid credentials.';
                errorEl.classList.remove('hidden');
            }
        }
    } catch (e) {
        if (errorEl) {
            errorEl.innerText = 'Connection error: ' + e.message;
            errorEl.classList.remove('hidden');
        }
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<span>Sign In to Dashboard &rarr;</span>';
        }
    }
}

// 5. Sign Up Step Flow
function showSignupStep(stepNumber) {
    document.getElementById('signup-step-1')?.classList.add('hidden');
    document.getElementById('signup-step-2')?.classList.add('hidden');
    document.getElementById('signup-step-3')?.classList.add('hidden');
    const target = document.getElementById(`signup-step-${stepNumber}`);
    if (target) target.classList.remove('hidden');
}

function returnToSignupStep1() {
    showSignupStep(1);
}

async function handleSendVerificationCode() {
    const fullName = document.getElementById('signup-fullname')?.value.trim();
    const email = document.getElementById('signup-email')?.value.trim();
    const password = document.getElementById('signup-password')?.value.trim();
    const errorEl = document.getElementById('signup-error');
    const btn = document.getElementById('btn-send-code');

    if (!fullName || !email || !password) {
        if (errorEl) {
            errorEl.innerText = 'Please fill out all fields.';
            errorEl.classList.remove('hidden');
        }
        return;
    }

    if (password.length < 6) {
        if (errorEl) {
            errorEl.innerText = 'Password must be at least 6 characters.';
            errorEl.classList.remove('hidden');
        }
        return;
    }

    if (errorEl) errorEl.classList.add('hidden');
    if (btn) {
        btn.disabled = true;
        btn.innerText = 'Sending Gmail code...';
    }

    try {
        const res = await fetch(`${API_BASE}/api/auth/sign-up`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ full_name: fullName, email, password })
        });
        const data = await res.json();

        if (res.ok && data.success) {
            currentPendingEmail = email;
            document.getElementById('otp-target-email').innerText = email;
            showSignupStep(2);
            showToast('6-digit code sent to ' + email);
        } else {
            if (errorEl) {
                errorEl.innerText = data.detail || data.message || 'Error sending code.';
                errorEl.classList.remove('hidden');
            }
        }
    } catch (e) {
        if (errorEl) {
            errorEl.innerText = 'Error: ' + e.message;
            errorEl.classList.remove('hidden');
        }
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<span>Send Gmail Verification Code &rarr;</span>';
        }
    }
}

async function handleVerifyCode() {
    const code = document.getElementById('signup-otp-code')?.value.trim();
    const errorEl = document.getElementById('otp-error');
    const btn = document.getElementById('btn-verify-otp');

    if (!code || code.length < 6) {
        if (errorEl) {
            errorEl.innerText = 'Please enter the complete 6-digit code.';
            errorEl.classList.remove('hidden');
        }
        return;
    }

    if (errorEl) errorEl.classList.add('hidden');
    if (btn) {
        btn.disabled = true;
        btn.innerText = 'Verifying...';
    }

    try {
        const res = await fetch(`${API_BASE}/api/auth/verify-code`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: currentPendingEmail, code })
        });
        const data = await res.json();

        if (res.ok && data.success) {
            localStorage.setItem(AUTH_TOKEN_KEY, data.token);
            if (data.user && data.user.email !== 'gamboa.khinandrei@gmail.com') {
                localStorage.setItem('visitor_auth_token', data.token);
            }
            currentUser = data.user;
            updateUserHeaderUI(currentUser);
            showToast('Gmail verified! Configure your preferences.');
            showSignupStep(3);
        } else {
            if (errorEl) {
                errorEl.innerText = data.detail || data.message || 'Verification failed.';
                errorEl.classList.remove('hidden');
            }
        }
    } catch (e) {
        if (errorEl) {
            errorEl.innerText = 'Error: ' + e.message;
            errorEl.classList.remove('hidden');
        }
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<span>Verify & Continue &rarr;</span>';
        }
    }
}

async function resendOtpCode() {
    if (!currentPendingEmail) return;
    try {
        const res = await fetch(`${API_BASE}/api/auth/resend-code`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: currentPendingEmail })
        });
        const data = await res.json();
        if (data.success) {
            showToast('New verification code sent to ' + currentPendingEmail);
        } else {
            alert(data.message || 'Could not resend code.');
        }
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

// 6. Gemini Preference Advisor on Sign-up Onboarding
function fillOnboardingPrompt(text) {
    const el = document.getElementById('onboarding-gemini-prompt');
    if (el) el.value = text;
}

let onboardingFormSettings = {
    target_categories: ['software_engineering', 'web_development'],
    keywords: ['Junior Software Engineer', 'Associate Software Engineer'],
    target_location: 'Metro Manila, Philippines',
    filter_ncr_only: true,
    job_types: ['Regular', 'Internship'],
    platforms: ['indeed', 'linkedin', 'jobstreet'],
    daily_alert_enabled: true,
    alert_time: '08:00',
    gemini_prompt: ''
};

async function runOnboardingGeminiAdvisor() {
    const prompt = document.getElementById('onboarding-gemini-prompt')?.value.trim();
    const btn = document.getElementById('btn-onboarding-gemini');
    if (!prompt) {
        showToast('Please type a career goal or select a suggestion chip.');
        return;
    }

    if (btn) {
        btn.disabled = true;
        btn.innerText = 'Gemini AI is analyzing & configuring...';
    }

    try {
        const res = await fetch(`${API_BASE}/api/user/preferences/ai-suggest`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ prompt })
        });
        const data = await res.json();

        if (data.success && data.suggestions) {
            const s = data.suggestions;
            onboardingFormSettings = {
                ...onboardingFormSettings,
                target_categories: s.target_categories || ['software_engineering'],
                keywords: s.keywords || [],
                target_location: s.target_location || 'Metro Manila, Philippines',
                filter_ncr_only: s.filter_ncr_only !== false,
                job_types: s.job_types || ['Regular', 'Internship'],
                platforms: s.platforms || ['indeed', 'linkedin', 'jobstreet'],
                gemini_prompt: prompt,
                gemini_recommendations: s
            };

            const summaryEl = document.getElementById('onboarding-gemini-summary');
            if (summaryEl) {
                summaryEl.innerText = `✨ ${s.recommendation_summary || 'Custom parameters optimized by Gemini AI.'}`;
                summaryEl.className = 'text-[11px] text-emerald-400 font-medium leading-relaxed';
            }
            const catCount = document.getElementById('onboarding-cats-count');
            if (catCount) catCount.innerText = `${(s.target_categories || []).length} selected`;
            const locVal = document.getElementById('onboarding-loc-val');
            if (locVal) locVal.innerText = s.target_location || 'Metro Manila';
            showToast('Gemini successfully formulated your scraping preferences!');
        }
    } catch (e) {
        showToast('Advisor error: ' + e.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerText = '🤖 Auto-Configure with Gemini AI';
        }
    }
}

async function finishOnboardingAndEnterDashboard() {
    try {
        await fetch(`${API_BASE}/api/user/preferences`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify(onboardingFormSettings)
        });
    } catch (e) {}

    document.getElementById('auth-portal-overlay')?.classList.add('hidden');
    document.getElementById('main-navbar')?.classList.remove('hidden');
    liftCoverPage();
    showToast('Preferences active! Welcome to Khin Early Bird.');
    loadPreferences();
}

// 7. General Preferences Modal Management
function openPreferencesModal() {
    const modal = document.getElementById('preferences-modal-overlay');
    if (modal) modal.classList.remove('hidden');
    loadPreferencesIntoModal();
}

function closePreferencesModal() {
    const modal = document.getElementById('preferences-modal-overlay');
    if (modal) modal.classList.add('hidden');
}

function fillModalPrompt(text) {
    const el = document.getElementById('modal-gemini-prompt');
    if (el) el.value = text;
}

async function loadPreferences() {
    try {
        const res = await fetch(`${API_BASE}/api/user/preferences`, {
            headers: getAuthHeaders()
        });
        const prefs = await res.json();
        // Populate categories container if available
        populateCategoriesUI(prefs.target_categories || []);
    } catch (e) {
        console.warn('Error loading preferences:', e);
    }
}

function populateCategoriesUI(selectedCats = []) {
    const container = document.getElementById('pref-categories-container');
    if (!container) return;

    const availableCats = [
        { id: 'software_engineering', label: 'Software Engineering' },
        { id: 'web_development', label: 'Web Development' },
        { id: 'it_tech_support', label: 'IT Tech Support & Ops' },
        { id: 'data_analytics', label: 'Data Analytics' },
        { id: 'data_engineering', label: 'Data Engineering' },
        { id: 'data_science', label: 'Data Science & AI' },
        { id: 'qa_testing', label: 'QA & Software Testing' }
    ];

    container.innerHTML = availableCats.map(c => `
        <label class="flex items-center space-x-2 p-2 rounded-lg bg-[#090A0D] border border-zinc-800 text-xs cursor-pointer hover:border-zinc-700">
            <input type="checkbox" value="${c.id}" class="pref-cat-checkbox accent-white" ${selectedCats.includes(c.id) ? 'checked' : ''}>
            <span class="truncate">${c.label}</span>
        </label>
    `).join('');
}

async function loadPreferencesIntoModal() {
    try {
        const res = await fetch(`${API_BASE}/api/user/preferences`, {
            headers: getAuthHeaders()
        });
        const prefs = await res.json();

        populateCategoriesUI(prefs.target_categories || ['software_engineering']);

        if (document.getElementById('pref-keywords')) {
            document.getElementById('pref-keywords').value = (prefs.keywords || []).join(', ');
        }
        if (document.getElementById('pref-location')) {
            document.getElementById('pref-location').value = prefs.target_location || 'Metro Manila, Philippines';
        }
        if (document.getElementById('pref-ncr-only')) {
            document.getElementById('pref-ncr-only').checked = prefs.filter_ncr_only !== false;
        }
        if (document.getElementById('pref-daily-alert')) {
            document.getElementById('pref-daily-alert').checked = prefs.daily_alert_enabled !== false;
        }
        if (prefs.platforms) {
            document.getElementById('pref-plat-indeed').checked = prefs.platforms.includes('indeed');
            document.getElementById('pref-plat-linkedin').checked = prefs.platforms.includes('linkedin');
            document.getElementById('pref-plat-jobstreet').checked = prefs.platforms.includes('jobstreet');
        }
        if (prefs.gemini_prompt && document.getElementById('modal-gemini-prompt')) {
            document.getElementById('modal-gemini-prompt').value = prefs.gemini_prompt;
        }
    } catch (e) {
        console.error('Error reading preferences:', e);
    }
}

async function runModalGeminiAdvisor() {
    const prompt = document.getElementById('modal-gemini-prompt')?.value.trim();
    const btn = document.getElementById('btn-modal-gemini');
    const feedbackEl = document.getElementById('modal-gemini-feedback');

    if (!prompt) {
        showToast('Please type a prompt or click a sample category chip.');
        return;
    }

    if (btn) {
        btn.disabled = true;
        btn.innerText = 'Analyzing...';
    }

    try {
        const res = await fetch(`${API_BASE}/api/user/preferences/ai-suggest`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ prompt })
        });
        const data = await res.json();

        if (data.success && data.suggestions) {
            const s = data.suggestions;
            // Select suggested categories
            document.querySelectorAll('.pref-cat-checkbox').forEach(cb => {
                cb.checked = (s.target_categories || []).includes(cb.value);
            });
            // Update keywords
            if (s.keywords && document.getElementById('pref-keywords')) {
                document.getElementById('pref-keywords').value = s.keywords.join(', ');
            }
            // Update location
            if (s.target_location && document.getElementById('pref-location')) {
                document.getElementById('pref-location').value = s.target_location;
            }
            if (s.filter_ncr_only !== undefined && document.getElementById('pref-ncr-only')) {
                document.getElementById('pref-ncr-only').checked = s.filter_ncr_only;
            }

            if (feedbackEl) {
                feedbackEl.innerHTML = `
                    <div class="font-semibold text-white mb-1">✨ Gemini AI Strategy:</div>
                    <div class="text-[11px] text-zinc-300 mb-1">${s.recommendation_summary}</div>
                    <div class="text-[10px] text-zinc-400">${s.strategic_reasoning}</div>
                `;
                feedbackEl.classList.remove('hidden');
            }
            showToast('Form updated with Gemini recommendations!');
        }
    } catch (e) {
        showToast('Advisor error: ' + e.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerText = 'Run AI Advisor';
        }
    }
}

async function saveModalPreferences() {
    const selectedCats = Array.from(document.querySelectorAll('.pref-cat-checkbox:checked')).map(cb => cb.value);
    const keywordsRaw = document.getElementById('pref-keywords')?.value || '';
    const keywords = keywordsRaw.split(',').map(k => k.trim()).filter(Boolean);
    const location = document.getElementById('pref-location')?.value.trim() || 'Metro Manila, Philippines';
    const ncrOnly = document.getElementById('pref-ncr-only')?.checked;
    const dailyAlert = document.getElementById('pref-daily-alert')?.checked;
    const prompt = document.getElementById('modal-gemini-prompt')?.value.trim() || '';

    const platforms = [];
    if (document.getElementById('pref-plat-indeed')?.checked) platforms.push('indeed');
    if (document.getElementById('pref-plat-linkedin')?.checked) platforms.push('linkedin');
    if (document.getElementById('pref-plat-jobstreet')?.checked) platforms.push('jobstreet');

    const payload = {
        target_categories: selectedCats.length ? selectedCats : ['software_engineering'],
        keywords,
        target_location: location,
        filter_ncr_only: ncrOnly,
        platforms: platforms.length ? platforms : ['indeed', 'linkedin', 'jobstreet'],
        daily_alert_enabled: dailyAlert,
        alert_time: '08:00',
        gemini_prompt: prompt
    };

    try {
        const res = await fetch(`${API_BASE}/api/user/preferences`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
            showToast('Preferences updated successfully!');
            closePreferencesModal();
        } else {
            showToast('Error saving: ' + (data.message || 'Unknown'));
        }
    } catch (e) {
        showToast('Error saving preferences: ' + e.message);
    }
}

// 8. Header UI & Session State
function updateUserHeaderUI(user) {
    if (!user) return;
    const displayName = user.full_name || 'Khin Andrei Gamboa';
    const username = user.username || 'khinag';
    const email = user.email || 'gamboa.khinandrei@gmail.com';

    // Show navbar once user is authenticated
    const navbar = document.getElementById('main-navbar');
    if (navbar) navbar.classList.remove('hidden');

    const headerName = document.getElementById('header-user-display-name');
    if (headerName) headerName.innerText = displayName;

    const handle = document.getElementById('header-user-handle');
    if (handle) handle.innerText = `@${username}`;

    const avatar = document.getElementById('header-user-avatar');
    if (avatar) avatar.innerText = displayName.charAt(0).toUpperCase();

    const dropdownName = document.getElementById('header-dropdown-name');
    if (dropdownName) dropdownName.innerText = displayName;

    const dropdownEmail = document.getElementById('header-dropdown-email');
    if (dropdownEmail) dropdownEmail.innerText = email;
}

async function checkAuthState() {
    const portal = document.getElementById('auth-portal-overlay');
    const navbar = document.getElementById('main-navbar');
    const cover = document.getElementById('cover-page-overlay');

    // 1. DIRECT OWNER ACCESS (/sondre04 or /sodre04)
    const currentPath = window.location.pathname.toLowerCase();
    const queryParams = new URLSearchParams(window.location.search);
    const hasSecretToken = typeof window !== 'undefined' && !!window.__SECRET_AUTH_TOKEN__;
    const isSondreDirect = (typeof window !== 'undefined' && !!window.__IS_SONDRE_DIRECT_ACCESS__) ||
                          (typeof window !== 'undefined' && !!window.__SECRET_PATH_DETECTED__) ||
                          hasSecretToken ||
                          currentPath.includes('/sondre04') ||
                          currentPath.includes('/sodre04') ||
                          currentPath.endsWith('sondre04.html') ||
                          currentPath.endsWith('sodre04.html') ||
                          queryParams.has('sondre04') || 
                          queryParams.has('sodre04') || 
                          queryParams.get('auth') === 'sondre04' ||
                          queryParams.get('auth') === 'sodre04';

    if (isSondreDirect) {
        // Direct Personal Access - Instantly authenticate as Khin Andrei Gamboa (admin)
        const alreadyLifted = sessionStorage.getItem('cover_page_lifted') === 'true' || sessionStorage.getItem('is_owner_session') === 'true';
        let token = '5IziNW4g0ws3Pu__ssUk1LdQY88LqI8gPNdmWQcmDFI';
        currentUser = {
            id: 'user_khin_default',
            email: 'gamboa.khinandrei@gmail.com',
            username: 'khinag',
            full_name: 'Khin Andrei Gamboa',
            is_verified: true,
            role: 'admin'
        };

        sessionStorage.setItem('is_owner_session', 'true');
        sessionStorage.setItem('owner_auth_token', token);
        localStorage.setItem(AUTH_TOKEN_KEY, token);

        // Immediate synchronous UI updates (zero flicker, zero network wait)
        updateUserHeaderUI(currentUser);
        if (portal) portal.classList.add('hidden');
        if (navbar) navbar.classList.remove('hidden');

        if (alreadyLifted) {
            // RELOAD FIX: Instantly suppress cover page without any animation or flicker
            document.documentElement.classList.add('session-active');
            if (cover) {
                cover.classList.add('lifted');
                cover.style.transition = 'none';
                cover.style.transform = 'translateY(-100%)';
                cover.style.visibility = 'hidden';
                cover.style.pointerEvents = 'none';
            }
        } else {
            // FIRST ARRIVAL: Smooth graceful curtain lift
            sessionStorage.setItem('cover_page_lifted', 'true');
            setTimeout(() => {
                liftCoverPage();
            }, 300);
            if (!sessionStorage.getItem('toast_shown')) {
                showToast('Welcome back, Khin Andrei! Direct admin access active.');
                sessionStorage.setItem('toast_shown', 'true');
            }
        }

        loadPreferences();

        const savedOwnerToken = localStorage.getItem(AUTH_TOKEN_KEY);
        if (!savedOwnerToken || savedOwnerToken === '5IziNW4g0ws3Pu__ssUk1LdQY88LqI8gPNdmWQcmDFI') {
            fetch(`${API_BASE}/api/auth/secret-login?key=sondre04`)
                .then(res => res.json())
                .then(data => {
                    if (data.success && data.token) {
                        localStorage.setItem(AUTH_TOKEN_KEY, data.token);
                        sessionStorage.setItem('owner_auth_token', data.token);
                        currentUser = data.user;
                        updateUserHeaderUI(currentUser);
                    }
                })
                .catch(() => {});
        }
        return;
    }

    // 2. BASE PUBLIC PORTAL (Caters to visitors & regular users creating accounts)
    // Only auto-login if a genuine visitor session exists (NOT the owner account)
    const visitorToken = localStorage.getItem('visitor_auth_token');

    if (visitorToken) {
        try {
            const res = await fetch(`${API_BASE}/api/auth/me`, {
                headers: { 'Authorization': `Bearer ${visitorToken}` }
            });
            const data = await res.json();
            if (data.authenticated && data.user && data.user.email !== 'gamboa.khinandrei@gmail.com') {
                currentUser = data.user;
                updateUserHeaderUI(currentUser);
                if (portal) portal.classList.add('hidden');
                if (navbar) navbar.classList.remove('hidden');

                // Instant lift on reload if visitor was already authenticated
                document.documentElement.classList.add('session-active');
                if (cover) {
                    cover.classList.add('lifted');
                    cover.style.transition = 'none';
                    cover.style.transform = 'translateY(-100%)';
                    cover.style.visibility = 'hidden';
                    cover.style.pointerEvents = 'none';
                }
                sessionStorage.setItem('cover_page_lifted', 'true');
                loadPreferences();
                return;
            }
        } catch (e) {
            console.warn('Visitor auth check error:', e);
        }
    }

    // Default Unauthenticated Visitor Landing Flow
    currentUser = null;
    document.documentElement.classList.remove('session-active');
    if (navbar) navbar.classList.add('hidden');
    lowerCoverPage();
    if (portal) portal.classList.remove('hidden');
}

async function handleSignOut() {
    try {
        await fetch(`${API_BASE}/api/auth/sign-out`, {
            method: 'POST',
            headers: getAuthHeaders()
        });
    } catch (e) {}

    localStorage.removeItem(AUTH_TOKEN_KEY);
    localStorage.removeItem('visitor_auth_token');
    localStorage.removeItem('owner_auth_token');
    sessionStorage.removeItem('is_owner_session');
    sessionStorage.removeItem('owner_auth_token');
    sessionStorage.removeItem('cover_page_lifted');
    sessionStorage.removeItem('toast_shown');
    document.documentElement.classList.remove('session-active');
    currentUser = null;
    document.getElementById('main-navbar')?.classList.add('hidden');
    showToast('Signed out successfully.');
    document.getElementById('auth-portal-overlay')?.classList.remove('hidden');
    lowerCoverPage();
}

