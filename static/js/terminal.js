// JOVX Terminal - Enhanced Client Engine

// Check PRO subscription state
const urlParams = new URLSearchParams(window.location.search);
let isProUser = localStorage.getItem('jovx_pro') === 'true' || urlParams.get('pro') === 'true' || urlParams.get('status') === 'success';

if (urlParams.get('pro') === 'true' || urlParams.get('status') === 'success') {
    localStorage.setItem('jovx_pro', 'true');
    isProUser = true;
}

window.setPro = function(val) {
    isProUser = !!val;
    localStorage.setItem('jovx_pro', isProUser ? 'true' : 'false');
    updateProUI();
    renderTokens();
    showToast(isProUser ? 'PRO Pass Activated!' : 'Modo Visitante Grátis (Top 5 Bloqueadas)');
};

window.toggleProTest = function() {
    window.setPro(!isProUser);
};

function updateProUI() {
    const badge = document.getElementById('userTierBadge');
    const badgeText = document.getElementById('userTierText');
    const headerBtn = document.getElementById('headerUpgradeBtn');
    if (isProUser) {
        if (badge) {
            badge.className = "hidden sm:flex items-center space-x-1.5 px-2.5 py-1 rounded border border-emerald-500/50 bg-emerald-500/10 text-[11px] font-mono text-alphaGreen";
        }
        if (badgeText) {
            badgeText.textContent = "JOVX PRO ACTIVE ⚡";
        }
        if (headerBtn) {
            headerBtn.innerHTML = '<i data-lucide="check-circle" class="w-3.5 h-3.5 text-alphaGreen"></i><span>PRO ACTIVE</span>';
            headerBtn.className = "px-3 py-1 rounded bg-surface border border-emerald-500/40 text-alphaGreen font-semibold transition flex items-center space-x-1.5";
        }
    } else {
        if (badge) {
            badge.className = "hidden sm:flex items-center space-x-1.5 px-2.5 py-1 rounded border border-surfaceBorder bg-surface text-[11px] font-mono text-slate-400";
        }
        if (badgeText) {
            badgeText.textContent = "FREE TIER (5 PRO GEMS LOCKED)";
        }
        if (headerBtn) {
            headerBtn.innerHTML = '<i data-lucide="sparkles" class="w-3.5 h-3.5"></i><span>UPGRADE TO PRO ($19.90 / 3 MONTHS)</span>';
            headerBtn.className = "px-3 py-1 rounded bg-gradient-to-r from-jovxDarkPurple to-jovxPurple hover:from-purple-600 hover:to-jovxNeon text-white font-semibold transition shadow-lg shadow-purple-900/40 flex items-center space-x-1.5";
        }
    }
    if (window.lucide) lucide.createIcons();
}

let allTokens = [];
let currentFilter = 'ALL';
let currentChain = 'ALL';
let audioEnabled = true;
let seenTopTokenAddrs = new Set();
let countdown = 15;
let countdownInterval = null;

// Web Audio API Synth Chime para alertas Alpha
let audioCtx = null;
function playAlphaChime() {
    if (!audioEnabled) return;
    try {
        if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const now = audioCtx.currentTime;
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(587.33, now); // D5
        osc.frequency.exponentialRampToValueAtTime(880.00, now + 0.15); // A5
        gain.gain.setValueAtTime(0.08, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start(now);
        osc.stop(now + 0.35);
    } catch (e) {
        // Ignora restrições do browser
    }
}

function toggleAudio() {
    audioEnabled = !audioEnabled;
    const label = document.getElementById('soundLabel');
    if (label) {
        label.textContent = audioEnabled ? 'SOUND: ON' : 'SOUND: MUTED';
    }
    showToast(audioEnabled ? 'Sound alerts enabled' : 'Sound alerts muted');
}

// Relógio com contagem regressiva visual
function startCountdown() {
    countdown = 15;
    const timerEl = document.getElementById('countdownTimer');
    if (countdownInterval) clearInterval(countdownInterval);

    countdownInterval = setInterval(() => {
        countdown--;
        if (timerEl) timerEl.textContent = countdown;
        if (countdown <= 0) {
            countdown = 15;
            fetchTokens();
        }
    }, 1000);
}

// Fetch tokens from API com proteção anti-esvaziamento
async function fetchTokens(manual = false) {
    if (manual) countdown = 15;

    try {
        const res = await fetch('/api/tokens/live');
        const data = await res.json();
        
        if (data.status === 'success' && data.tokens && data.tokens.length > 0) {
            allTokens = data.tokens;

            // Toca o alarme sonoro APENAS se houver uma NOVA moeda com Score >= 90
            let hasNewAlpha = false;
            allTokens.forEach(t => {
                if (t.jovx_score >= 90 && !seenTopTokenAddrs.has(t.address)) {
                    hasNewAlpha = true;
                    seenTopTokenAddrs.add(t.address);
                }
            });

            if (hasNewAlpha) {
                playAlphaChime();
            }

            renderTokens();
            updateStats(allTokens);
        }
    } catch (err) {
        console.error('Error fetching JOVX live tokens:', err);
    }
}

function updateStats(tokens) {
    const statActive = document.getElementById('statActiveGems');
    if (statActive) statActive.textContent = `${tokens.length} TOKENS`;
    
    const countLabel = document.getElementById('tokenCountLabel');
    if (countLabel) countLabel.textContent = tokens.length;
}

function setFilter(filterName) {
    currentFilter = filterName;
    document.querySelectorAll('.filter-pill').forEach(btn => {
        btn.classList.remove('active', 'border-jovxPurple', 'bg-jovxPurple/20', 'text-jovxNeon');
        btn.classList.add('border-surfaceBorder', 'text-slate-300');
    });

    const activeBtn = document.getElementById(`filter-${filterName}`);
    if (activeBtn) {
        activeBtn.classList.remove('border-surfaceBorder', 'text-slate-300');
        activeBtn.classList.add('active', 'border-jovxPurple', 'bg-jovxPurple/20', 'text-jovxNeon');
    }

    renderTokens();
}

function setChainFilter(chainName) {
    currentChain = chainName;
    document.querySelectorAll('.chain-pill').forEach(btn => {
        btn.classList.remove('active', 'border-jovxPurple', 'bg-jovxPurple/20', 'text-jovxNeon');
        btn.classList.add('border-surfaceBorder', 'text-slate-300');
    });

    const activeBtn = document.getElementById(`chain-${chainName}`);
    if (activeBtn) {
        activeBtn.classList.remove('border-surfaceBorder', 'text-slate-300');
        activeBtn.classList.add('active', 'border-jovxPurple', 'bg-jovxPurple/20', 'text-jovxNeon');
    }

    renderTokens();
}

function handleSearch() {
    renderTokens();
}

function renderTokens() {
    const tbody = document.getElementById('tokenTableBody');
    if (!tbody) return;

    const searchTerm = (document.getElementById('searchInput')?.value || '').toLowerCase().trim();

    let filtered = allTokens.filter(t => {
        // Filtro de Rede
        if (currentChain !== 'ALL') {
            if (currentChain === 'FOMO') {
                const isFomo = t.chain === 'FOMO' || t.chain === 'ROBINHOOD' || (t.dex_platform && t.dex_platform.includes('FOMO')) || (t.tag && t.tag.includes('FOMO'));
                if (!isFomo) return false;
            } else if (currentChain === 'SOLANA') {
                if (t.chain !== 'SOLANA' && (!t.dex_platform || !t.dex_platform.includes('SOL'))) return false;
            } else if (t.chain !== currentChain) {
                return false;
            }
        }

        // Filtro de Texto
        if (searchTerm) {
            const matchName = t.name.toLowerCase().includes(searchTerm);
            const matchSymbol = t.symbol.toLowerCase().includes(searchTerm);
            const matchAddr = t.address.toLowerCase().includes(searchTerm);
            if (!matchName && !matchSymbol && !matchAddr) return false;
        }

        // Filtro de Estratégia
        if (currentFilter === 'ALPHA') return t.jovx_score >= 85;
        if (currentFilter === 'EARLY') return t.market_cap < 500000;
        if (currentFilter === 'WHALE') return (t.buys_24h / (t.sells_24h || 1)) >= 1.25;
        if (currentFilter === 'FOMO') {
            return t.chain === 'FOMO' || t.chain === 'ROBINHOOD' || (t.dex_platform && t.dex_platform.includes('FOMO')) || (t.tag && t.tag.includes('FOMO'));
        }

        return true;
    });

    if (filtered.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="11" class="py-12 text-center text-slate-500 font-mono">
                    NO TOKENS CURRENTLY MATCH THIS COMBINED FILTER CRITERIA.
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = filtered.map((t, idx) => {
        const isLocked = !isProUser && idx < 5;
        const isTopScore = t.jovx_score >= 88;
        const scoreColor = isTopScore ? 'text-jovxNeon font-bold' : (t.jovx_score >= 75 ? 'text-alphaGreen' : 'text-warningAmber');
        const scoreBadgeBg = isTopScore ? 'bg-jovxPurple/20 border-jovxPurple pulse-alpha' : (t.jovx_score >= 75 ? 'bg-emerald-500/15 border-emerald-500/40' : 'bg-amber-500/15 border-amber-500/40');

        // Buy/Sell pressure
        const totalTx = (t.buys_24h + t.sells_24h) || 1;
        const buyPct = Math.round((t.buys_24h / totalTx) * 100);

        // Chain badge color & label
        const isFomo = t.chain === 'FOMO' || t.chain === 'ROBINHOOD' || (t.dex_platform && t.dex_platform.includes('FOMO'));
        const chainBadgeColor = isFomo ? 'bg-emerald-900/40 text-emerald-300 border-emerald-700/50' : 
                               (t.chain === 'SOLANA' ? 'bg-purple-900/40 text-purple-300 border-purple-700/50' : 
                               (t.chain === 'BASE' ? 'bg-blue-900/40 text-blue-300 border-blue-700/50' : 'bg-slate-800 text-slate-300 border-slate-700'));
        const chainLabel = isFomo ? '⚡ FOMO' : t.chain;

        // Renderização para Token Bloqueado (Top 5 Free Tier)
        if (isLocked) {
            return `
                <tr class="pro-row-locked hover:bg-surfaceBorder/40 transition">
                    <td class="py-3 px-4 text-center font-mono">
                        <span class="px-2 py-0.5 rounded bg-jovxPurple/25 border border-jovxPurple text-jovxNeon font-mono text-xs font-black shadow-md shadow-purple-900/40">
                            #${idx + 1} 🔥
                        </span>
                    </td>
                    
                    <!-- TOKEN IDENTIFIER (BLURRED & LOCKED) -->
                    <td class="py-3 px-4">
                        <div class="flex items-center space-x-3 cursor-pointer" onclick="startStripeCheckout()" title="VIP Alpha Gem — Toque para Liberar no Plano Pró">
                            <div class="w-9 h-9 rounded-lg bg-surface border border-jovxPurple/60 flex items-center justify-center shrink-0 shadow-lg shadow-purple-500/20">
                                <i data-lucide="lock" class="w-4 h-4 text-jovxNeon pulse-lock"></i>
                            </div>
                            <div>
                                <div class="flex items-center space-x-2">
                                    <span class="pro-locked-blur font-mono font-black text-white text-sm tracking-widest select-none">████████</span>
                                    <span class="text-[9px] px-1.5 py-0.5 rounded font-mono font-bold bg-gradient-to-r from-jovxDarkPurple to-jovxPurple text-white pro-badge-glow">PRO VIP</span>
                                    <span class="text-[10px] px-1.5 py-0.5 rounded border ${chainBadgeColor} font-mono">${chainLabel}</span>
                                </div>
                                <div class="flex items-center space-x-1.5 text-[11px] font-mono mt-0.5">
                                    <i data-lucide="sparkles" class="w-3 h-3 text-jovxNeon"></i>
                                    <span class="text-slate-400">Score ${t.jovx_score}/100 • </span>
                                    <span class="text-jovxNeon underline hover:text-white transition font-semibold">Liberar no Plano Pró</span>

                                </div>
                            </div>
                        </div>
                    </td>

                    <!-- JOVX SCORE (FULLY VISIBLE TO CREATE FOMO) -->
                    <td class="py-3 px-4 text-center">
                        <div class="inline-flex flex-col items-center">
                            <span class="px-2.5 py-1 rounded-md border text-xs font-mono font-bold ${scoreBadgeBg} ${scoreColor}">
                                ${t.jovx_score} / 100 🔥
                            </span>
                            <span class="text-[9px] uppercase tracking-wider text-jovxNeon mt-1 font-mono font-bold">TOP ALPHA</span>
                        </div>
                    </td>

                    <!-- PRICE -->
                    <td class="py-3 px-4 text-right font-mono">
                        <div class="font-semibold text-white">$${formatPrice(t.price_usd)}</div>
                        <div class="text-[10px] font-bold ${t.price_change_24h >= 0 ? 'text-alphaGreen' : 'text-dangerRose'}">
                            ${t.price_change_24h >= 0 ? '+' : ''}${t.price_change_24h.toFixed(1)}%
                        </div>
                    </td>

                    <!-- MARKET CAP -->
                    <td class="py-3 px-4 text-right font-mono">
                        <div class="font-bold text-white">$${formatCurrency(t.market_cap)}</div>
                        <div class="text-[10px] text-slate-500">FDV</div>
                    </td>

                    <!-- LIQUIDITY -->
                    <td class="py-3 px-4 text-right font-mono">
                        <div class="font-semibold text-slate-200">$${formatCurrency(t.liquidity_usd)}</div>
                        <div class="text-[10px] text-alphaGreen font-mono font-bold">LP LOCKED 🔒</div>
                    </td>

                    <!-- 24H VOLUME -->
                    <td class="py-3 px-4 text-right font-mono">
                        <div class="font-semibold text-slate-200">$${formatCurrency(t.volume_24h)}</div>
                        <div class="text-[10px] text-jovxNeon">5m: $${formatCurrency(t.volume_5m)}</div>
                    </td>

                    <!-- BUY/SELL RATIO -->
                    <td class="py-3 px-4 text-center">
                        <div class="w-24 mx-auto space-y-1 font-mono text-[10px]">
                            <div class="flex justify-between text-slate-400">
                                <span class="text-alphaGreen">${buyPct}% B</span>
                                <span class="text-dangerRose">${100 - buyPct}% S</span>
                            </div>
                            <div class="h-1.5 w-full bg-dangerRose/60 rounded-full overflow-hidden flex">
                                <div class="bg-alphaGreen h-full" style="width: ${buyPct}%"></div>
                            </div>
                        </div>
                    </td>

                    <!-- AGE -->
                    <td class="py-3 px-4 text-center font-mono text-slate-400">${t.age}</td>

                    <!-- RISK LEVEL -->
                    <td class="py-3 px-4 text-center">
                        <span class="px-2 py-0.5 rounded text-[10px] font-mono border bg-emerald-500/10 border-emerald-500/30 text-alphaGreen font-semibold">
                            AUDITED
                        </span>
                    </td>

                    <!-- CTA BOTÃO DE DESBLOQUEIO -->
                    <td class="py-3 px-4 text-center">
                        <div class="flex items-center justify-center space-x-2">
                            <button onclick="startStripeCheckout()" class="px-3.5 py-1.5 rounded-lg unlock-btn-glow text-white font-mono text-[11px] font-extrabold flex items-center space-x-1.5 shadow-lg transform hover:scale-105 active:scale-95" title="Ir para pagamento seguro Stripe — Plano Pró (3 Meses)">
                                <i data-lucide="lock" class="w-3.5 h-3.5"></i>
                                <span>PLANO PRÓ ⚡</span>
                            </button>
                            <button onclick="openProModal()" class="p-1.5 rounded bg-surface border border-surfaceBorder hover:border-jovxPurple text-slate-400 hover:text-white transition" title="Benefícios do Plano Pró">
                                <i data-lucide="info" class="w-3.5 h-3.5"></i>
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }

        // Renderização para Tokens Abertos (Rank #6 ao #20, ou TODOS se PRO)
        return `
            <tr class="hover:bg-surfaceBorder/40 transition">
                <td class="py-3 px-4 text-center font-mono text-slate-500 font-bold">${idx + 1}</td>
                
                <!-- TOKEN IDENTIFIER -->
                <td class="py-3 px-4">
                    <div class="flex items-center space-x-3">
                        <div class="w-8 h-8 rounded-lg bg-surface border border-surfaceBorder overflow-hidden flex items-center justify-center shrink-0">
                            ${t.icon ? `<img src="${t.icon}" alt="${t.symbol}" class="w-full h-full object-cover" onerror="this.onerror=null; this.parentElement.innerHTML='<span class=\\'font-mono text-xs font-bold text-jovxNeon\\'>${t.symbol.slice(0, 2)}</span>'">` : `<span class="font-mono text-xs font-bold text-jovxNeon">${t.symbol.slice(0, 2)}</span>`}
                        </div>
                        <div>
                            <div class="flex items-center space-x-2">
                                <span class="font-bold text-white text-sm tracking-tight">${t.name}</span>
                                <span class="text-[10px] px-1.5 py-0.5 rounded border ${chainBadgeColor} font-mono">${chainLabel}</span>
                            </div>
                            <div class="flex items-center space-x-2 text-[11px] text-slate-400 font-mono">
                                <span class="text-slate-300 font-semibold">$${t.symbol}</span>
                                <button onclick="copyToClipboard('${t.address}')" class="text-slate-500 hover:text-jovxNeon transition flex items-center space-x-1" title="Copy Contract Address">
                                    <span>${t.address.slice(0, 4)}...${t.address.slice(-4)}</span>
                                    <i data-lucide="copy" class="w-3 h-3"></i>
                                </button>
                            </div>
                        </div>
                    </div>
                </td>

                <!-- JOVX SCORE -->
                <td class="py-3 px-4 text-center">
                    <div class="inline-flex flex-col items-center">
                        <span class="px-2.5 py-1 rounded-md border text-xs font-mono font-bold ${scoreBadgeBg} ${scoreColor}">
                            ${t.jovx_score} / 100 ${isTopScore ? '🔥' : '🟢'}
                        </span>
                        <span class="text-[9px] uppercase tracking-wider text-slate-500 mt-1 font-mono">${t.tag}</span>
                    </div>
                </td>

                <!-- PRICE -->
                <td class="py-3 px-4 text-right font-mono">
                    <div class="font-semibold text-white">$${formatPrice(t.price_usd)}</div>
                    <div class="text-[10px] ${t.price_change_24h >= 0 ? 'text-alphaGreen' : 'text-dangerRose'}">
                        ${t.price_change_24h >= 0 ? '+' : ''}${t.price_change_24h.toFixed(1)}%
                    </div>
                </td>

                <!-- MARKET CAP -->
                <td class="py-3 px-4 text-right font-mono">
                    <div class="font-bold text-white">$${formatCurrency(t.market_cap)}</div>
                    <div class="text-[10px] text-slate-500">FDV</div>
                </td>

                <!-- LIQUIDITY -->
                <td class="py-3 px-4 text-right font-mono">
                    <div class="font-semibold text-slate-200">$${formatCurrency(t.liquidity_usd)}</div>
                    <div class="text-[10px] text-alphaGreen font-mono">LP VERIFIED</div>
                </td>

                <!-- 24H VOLUME -->
                <td class="py-3 px-4 text-right font-mono">
                    <div class="font-semibold text-slate-200">$${formatCurrency(t.volume_24h)}</div>
                    <div class="text-[10px] text-jovxNeon">5m: $${formatCurrency(t.volume_5m)}</div>
                </td>

                <!-- BUY/SELL RATIO -->
                <td class="py-3 px-4 text-center">
                    <div class="w-24 mx-auto space-y-1 font-mono text-[10px]">
                        <div class="flex justify-between text-slate-400">
                            <span class="text-alphaGreen">${buyPct}% B</span>
                            <span class="text-dangerRose">${100 - buyPct}% S</span>
                        </div>
                        <div class="h-1.5 w-full bg-dangerRose/60 rounded-full overflow-hidden flex">
                            <div class="bg-alphaGreen h-full" style="width: ${buyPct}%"></div>
                        </div>
                    </div>
                </td>

                <!-- AGE -->
                <td class="py-3 px-4 text-center font-mono text-slate-400">${t.age}</td>

                <!-- RISK LEVEL -->
                <td class="py-3 px-4 text-center">
                    <span class="px-2 py-0.5 rounded text-[10px] font-mono border ${t.risk_level === 'LOW RISK' ? 'bg-emerald-500/10 border-emerald-500/30 text-alphaGreen' : 'bg-amber-500/10 border-amber-500/30 text-warningAmber'}">
                        ${t.risk_level}
                    </span>
                </td>

                <!-- DIRECT BUY BUTTON -->
                <td class="py-3 px-4 text-center">
                    <div class="flex items-center justify-center space-x-2">
                        <!-- O BOTAO DE COMPRA PRINCIPAL BRILHANTE -->
                        <a href="${t.buy_url}" target="_blank" rel="noopener noreferrer" class="px-3 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-obsidian font-mono text-[11px] font-extrabold transition shadow-lg shadow-emerald-500/30 flex items-center space-x-1.5 transform hover:scale-105 active:scale-95" title="Direct Swap on ${t.dex_platform}">
                            <i data-lucide="shopping-cart" class="w-3.5 h-3.5"></i>
                            <span>BUY NOW</span>
                        </a>

                        <!-- ATALHO DEXSCREENER -->
                        <a href="${t.pair_url}" target="_blank" rel="noopener noreferrer" class="p-1.5 rounded bg-surface border border-surfaceBorder hover:border-jovxPurple text-slate-400 hover:text-white transition" title="Open Chart">
                            <i data-lucide="bar-chart-2" class="w-3.5 h-3.5"></i>
                        </a>
                    </div>
                </td>
            </tr>
        `;
    }).join('');

    lucide.createIcons();
}

function formatCurrency(val) {
    if (!val || val === 0) return '0';
    if (val >= 1000000) return (val / 1000000).toFixed(2) + 'M';
    if (val >= 1000) return (val / 1000).toFixed(1) + 'K';
    return val.toFixed(0);
}

function formatPrice(val) {
    if (!val) return '0.00';
    if (val < 0.00001) return val.toExponential(2);
    if (val < 0.01) return val.toFixed(5);
    return val.toFixed(3);
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast('Contract Copied to Clipboard!');
    }).catch(err => {
        console.error('Failed to copy contract:', err);
    });
}

function showToast(msg) {
    const toast = document.getElementById('toast');
    const toastMsg = document.getElementById('toastMsg');
    if (!toast || !toastMsg) return;

    toastMsg.textContent = msg;
    toast.classList.remove('translate-y-20', 'opacity-0');
    toast.classList.add('translate-y-0', 'opacity-100');

    setTimeout(() => {
        toast.classList.remove('translate-y-0', 'opacity-100');
        toast.classList.add('translate-y-20', 'opacity-0');
    }, 2500);
}

// Modal Handlers
function openProModal() {
    const modal = document.getElementById('proModal');
    if (modal) modal.classList.remove('hidden');
}

function closeProModal() {
    const modal = document.getElementById('proModal');
    if (modal) modal.classList.add('hidden');
}

const STRIPE_CHECKOUT_URL = 'https://buy.stripe.com/dRm00c3TZfCX2tTbT60co06';

async function startStripeCheckout() {
    showToast('Redirecionando para o Checkout Seguro Stripe...');
    const btn = document.getElementById('stripeCheckoutBtn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<div class="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div><span>Conectando à Stripe...</span>`;
    }

    setTimeout(() => {
        window.location.href = STRIPE_CHECKOUT_URL;
    }, 300);
}

// Inicialização automática
document.addEventListener('DOMContentLoaded', () => {
    updateProUI();
    fetchTokens();
    startCountdown();
});
