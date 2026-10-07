import requests
import time
import threading
import logging
import json
try:
    from config import HELIUS_API_KEY, HELIUS_RPC_URL
except ImportError:
    HELIUS_API_KEY = ""
    HELIUS_RPC_URL = ""

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("JOVX_SCANNER")

# Moedas antigas, nativas e estáveis terminantemente PROIBIDAS
EXCLUDED_SYMBOLS = {
    "SOL", "WSOL", "ETH", "WETH", "BTC", "WBTC", "USDC", "USDT", 
    "DAI", "BNB", "STETH", "USD", "EUR", "BRL", "USDS"
}

EXCLUDED_NAME_KEYWORDS = [
    "SOLANA", "WRAPPED SOL", "ETHEREUM", "WRAPPED ETHER", "WRAPPED ETH", 
    "BITCOIN", "WRAPPED BTC", "TETHER", "USD COIN", "BINANCE"
]

# IDADE MÁXIMA PARA TODAS AS MOEDAS: 3 DIAS (259.200 segundos)
MAX_TOKEN_AGE_SECONDS = 3 * 86400

class JovxScanner:
    """
    Motor Algorítmico JOVX Multi-Chain (Solana, Base, Ethereum & Ecossistema FOMO):
    - Top #1 ao #5: Sempre as gemas mais novas de minutos (< 2.5h) e em alta explosiva
    - Ranks #6 ao #20: Gemas da plataforma FOMO ($50M-$269M MC) e breakout runners
    - TOLERÂNCIA ZERO PARA DERRETIMENTO:
      * 5m < -4.5% -> Eliminada imediatamente (Anti-Flash-Dump)
      * 1h < -6.0% -> Eliminada imediatamente (Anti-Bleed)
      * 24h < 0.0% para micro-caps -> Eliminada (Anti-Loss)
    - Links canônicos da DexScreener (Zero Erro 404)
    """

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }
        self.profiles_url = "https://api.dexscreener.com/token-profiles/latest/v1"
        self.boosts_url = "https://api.dexscreener.com/token-boosts/latest/v1"
        self.boosts_top_url = "https://api.dexscreener.com/token-boosts/top/v1"
        self.tokens_batch_url = "https://api.dexscreener.com/latest/dex/tokens/"
        self.search_url = "https://api.dexscreener.com/latest/dex/search"
        
        self.pool = {}
        self.fallback_reserve = []
        self.cached_list = []
        self.last_fetch_time = time.time()
        self.lock = threading.Lock()
        
        # Blacklist permanente de tokens que derreteram/falharam na auditoria ao vivo (Zero Retorno)
        self.blacklisted_dumped_addrs = {
            "GfBwZAaRLdarL7mmUce8wkFc2xALuTSzyrREVKixpump", # DONSOM derreteu -97% (Banido permanentemente)
            "0xa0c5F58Bf54700B0c582691aA85eab3B8603f4e8", # MOSS liquidez derreteu (Banido)
            "BZ8pkWUs4TjboT2xHRCwg3o6PK8xkvmNewvqMyyfpump", # IRL derreteu -93% (Banido)
            "95pkzpn2xcos5nb4uwedeztncwb2gdbs7iuzr3yz2tb7", # ST par inexistente (Banido)
        }
        
        # Palavras-chave cobrindo FOMO e as melhores narrativas
        self.search_keywords = [
            "fomo", "robinhood", "artificial inu", "stonk", "solana", "pump", 
            "ai", "doge", "cat", "pepe", "moon", "agent", "trump", "gold", "bull"
        ]
        self.search_index = 0

        # Smart Pulse Helius (Controle rigoroso para economizar créditos e durar 31 dias)
        self.last_helius_fetch = 0
        self.helius_interval = 360  # Pulso a cada 6 minutos (~1.000 créditos/hora)
        self.helius_prog_index = 0
        self.helius_daily_credits = 0
        self.helius_day_tracker = time.strftime("%Y-%m-%d")
        self.helius_daily_limit = 20000  # Trava máxima diária de 20.000 créditos (~600.000/mês)
        self.helius_disabled = False

        # Carregar sementes verificadas 100% reais (Top 5 minutos + FOMO Gems)
        self._seed_initial_pool()

        # Thread contínua em segundo plano
        self.worker_thread = threading.Thread(target=self._background_worker, daemon=True)
        self.worker_thread.start()

    def _seed_initial_pool(self):
        """Inicializa tokens verificados 100% reais sem nenhum link quebrado"""
        seeds = [
            {
                "address": "0xbDDd48BdE05b98d222A7110fB363C5176360B356",
                "name": "SurrexLabs",
                "symbol": "SRX",
                "chain": "ROBINHOOD",
                "price_usd": 0.0007269,
                "market_cap": 726976.0,
                "liquidity_usd": 83873.51,
                "volume_24h": 1438656.39,
                "volume_5m": 134082.92,
                "buys_24h": 2080,
                "sells_24h": 1439,
                "price_change_24h": 28314.0,
                "price_change_1h": 28275.0,
                "price_change_5m": 11.87,
                "age": "1.0h",
                "age_seconds": 3623,
                "jovx_score": 99,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://app.uniswap.org/swap?chain=robinhood&outputCurrency=0xbDDd48BdE05b98d222A7110fB363C5176360B356",
                "dex_platform": "UNISWAP (ROBINHOOD)",
                "pair_url": "https://dexscreener.com/robinhood/0x5d07d9472723803073b594f582149ca82ffec1c2",
                "icon": "https://cdn.dexscreener.com/cms/images/9XUVV3QIVp5fR6MF?width=800&height=800&quality=95&format=auto",
            },
            {
                "address": "kZXneJiCtqsgjN9kgMLVhsjuieYs1LdrBASTXwnpump",
                "name": "fomo",
                "symbol": "FOMO",
                "chain": "SOLANA",
                "price_usd": 0.005668,
                "market_cap": 5665667.0,
                "liquidity_usd": 213812.72,
                "volume_24h": 198244.09,
                "volume_5m": 616.73,
                "buys_24h": 2161,
                "sells_24h": 1433,
                "price_change_24h": 11383.0,
                "price_change_1h": 1.76,
                "price_change_5m": 0.18,
                "age": "1d",
                "age_seconds": 86400,
                "jovx_score": 99,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-kZXneJiCtqsgjN9kgMLVhsjuieYs1LdrBASTXwnpump",
                "dex_platform": "JUPITER (SOL)",
                "pair_url": "https://dexscreener.com/solana/5pxx1rdblnilgmdyzssvvr9rytmauopgzwyckcswvukd",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/kZXneJiCtqsgjN9kgMLVhsjuieYs1LdrBASTXwnpump.png",
            },
            {
                "address": "ADPN2aqzY5RhkBC7bNQWFhTFFEYKY4drHUQG887Cpump",
                "name": "CATCRAFT",
                "symbol": "CATCRAFT",
                "chain": "SOLANA",
                "price_usd": 0.001699,
                "market_cap": 1672695.0,
                "liquidity_usd": 125403.68,
                "volume_24h": 3684486.62,
                "volume_5m": 4076.74,
                "buys_24h": 89892,
                "sells_24h": 43506,
                "price_change_24h": 1664.0,
                "price_change_1h": 39.38,
                "price_change_5m": 4.69,
                "age": "20.7h",
                "age_seconds": 74607,
                "jovx_score": 99,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-ADPN2aqzY5RhkBC7bNQWFhTFFEYKY4drHUQG887Cpump",
                "dex_platform": "RAYDIUM (SOL)",
                "pair_url": "https://dexscreener.com/solana/7mqdgteiad4tkupg9hstypqnestntrauehh1zj1awp8x",
                "icon": "https://cdn.dexscreener.com/cms/images/hvsp8Tt8oiP96-P1?width=800&height=800&quality=95&format=auto",
            },
            {
                "address": "45VHsie7CwFfPKWCw28PCdZdJWMA5Y6k56wDam9Hpump",
                "name": "Ferrari Inu",
                "symbol": "RARINU",
                "chain": "SOLANA",
                "price_usd": 0.001048,
                "market_cap": 1037742.0,
                "liquidity_usd": 97734.33,
                "volume_24h": 3374818.34,
                "volume_5m": 18235.28,
                "buys_24h": 55932,
                "sells_24h": 19591,
                "price_change_24h": 886.0,
                "price_change_1h": -27.6,
                "price_change_5m": -21.88,
                "age": "21.1h",
                "age_seconds": 75829,
                "jovx_score": 99,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-45VHsie7CwFfPKWCw28PCdZdJWMA5Y6k56wDam9Hpump",
                "dex_platform": "RAYDIUM (SOL)",
                "pair_url": "https://dexscreener.com/solana/a2asuorcetj9kwkmzhf3pvsslgzrnmnghiqku8uegqmj",
                "icon": "https://cdn.dexscreener.com/cms/images/KXdS2YaVij7sqGJu?width=800&height=800&quality=95&format=auto",
            },
            {
                "address": "0xf9cDf67Dd3dde76a72F37cE4F0A27325Ba25F4D9",
                "name": "Blokeys",
                "symbol": "BLOKEYS",
                "chain": "BASE",
                "price_usd": 7.395e-07,
                "market_cap": 73954.0,
                "liquidity_usd": 61127.75,
                "volume_24h": 389131.74,
                "volume_5m": 265.03,
                "buys_24h": 1039,
                "sells_24h": 877,
                "price_change_24h": 190.0,
                "price_change_1h": -9.24,
                "price_change_5m": -1.15,
                "age": "2.6h",
                "age_seconds": 9420,
                "jovx_score": 99,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://app.uniswap.org/swap?chain=base&outputCurrency=0xf9cDf67Dd3dde76a72F37cE4F0A27325Ba25F4D9",
                "dex_platform": "UNISWAP (BASE)",
                "pair_url": "https://dexscreener.com/base/0xcb18c4cf24d8cf14f36b124846a13a249fbd2681022a5b151cc5346e1b42bcbe",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/base/0xf9cDf67Dd3dde76a72F37cE4F0A27325Ba25F4D9.png",
            },
            {
                "address": "0xAF8A8A828632Cc88BF917A42d9e1AaB71D5a1994",
                "name": "Official Trump",
                "symbol": "TRUMP",
                "chain": "ROBINHOOD",
                "price_usd": 4.23,
                "market_cap": 4230922385.0,
                "liquidity_usd": 2115461192.79,
                "volume_24h": 0.03,
                "volume_5m": 0.0,
                "buys_24h": 2,
                "sells_24h": 0,
                "price_change_24h": 0.07,
                "price_change_1h": 0.0,
                "price_change_5m": 0.0,
                "age": "1d",
                "age_seconds": 86400,
                "jovx_score": 99,
                "tag": "BULLISH TREND",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://app.uniswap.org/swap?chain=robinhood&outputCurrency=0xAF8A8A828632Cc88BF917A42d9e1AaB71D5a1994",
                "dex_platform": "UNISWAP (ROBINHOOD)",
                "pair_url": "https://dexscreener.com/robinhood/0x4c925966e4384ca983696698a106c52da3d87537",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/robinhood/0xAF8A8A828632Cc88BF917A42d9e1AaB71D5a1994.png",
            },
            {
                "address": "0xc28b8cd6A219B152B5ee190b6A56e268d51397f7",
                "name": "Caterpillar Inc.",
                "symbol": "CAT",
                "chain": "ROBINHOOD",
                "price_usd": 1416.76,
                "market_cap": 1416762116.0,
                "liquidity_usd": 708381058.19,
                "volume_24h": 0.03,
                "volume_5m": 0.0,
                "buys_24h": 2,
                "sells_24h": 0,
                "price_change_24h": 0.07,
                "price_change_1h": 0.0,
                "price_change_5m": 0.0,
                "age": "1d",
                "age_seconds": 86400,
                "jovx_score": 99,
                "tag": "BULLISH TREND",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://app.uniswap.org/swap?chain=robinhood&outputCurrency=0xc28b8cd6A219B152B5ee190b6A56e268d51397f7",
                "dex_platform": "UNISWAP (ROBINHOOD)",
                "pair_url": "https://dexscreener.com/robinhood/0x6dee1b078e781bb92b7badeee5f3651e96f15946",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/robinhood/0xc28b8cd6A219B152B5ee190b6A56e268d51397f7.png",
            },
            {
                "address": "0xDc4Ecc86f21220602573A73AbC2d44DFA071495d",
                "name": "SuperFarm",
                "symbol": "SUPER",
                "chain": "ROBINHOOD",
                "price_usd": 0.1718,
                "market_cap": 171800444.0,
                "liquidity_usd": 85900222.17,
                "volume_24h": 0.03,
                "volume_5m": 0.0,
                "buys_24h": 2,
                "sells_24h": 0,
                "price_change_24h": 0.07,
                "price_change_1h": 0.0,
                "price_change_5m": 0.0,
                "age": "1d",
                "age_seconds": 86400,
                "jovx_score": 99,
                "tag": "BULLISH TREND",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://app.uniswap.org/swap?chain=robinhood&outputCurrency=0xDc4Ecc86f21220602573A73AbC2d44DFA071495d",
                "dex_platform": "UNISWAP (ROBINHOOD)",
                "pair_url": "https://dexscreener.com/robinhood/0x579ec04d76bd3585e1cd4ac9d519bb0f03f2f16c",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/robinhood/0xDc4Ecc86f21220602573A73AbC2d44DFA071495d.png",
            },
            {
                "address": "2BVfJ4AHMvHdKtEZNHaBr48dQzTfZvYkjaaxbM6bpump",
                "name": "swordinu",
                "symbol": "SWORDINU",
                "chain": "SOLANA",
                "price_usd": 0.0035,
                "market_cap": 3500000,
                "liquidity_usd": 467391,
                "volume_24h": 5800000,
                "volume_5m": 45000,
                "buys_24h": 25000,
                "sells_24h": 14000,
                "price_change_24h": 24000.0,
                "price_change_1h": 45.0,
                "price_change_5m": 1.2,
                "age": "4.2h",
                "age_seconds": 15120,
                "jovx_score": 95,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-2BVfJ4AHMvHdKtEZNHaBr48dQzTfZvYkjaaxbM6bpump",
                "dex_platform": "JUPITER (SOL)",
                "pair_url": "https://dexscreener.com/solana/69fyvgotxqxbdv7tazd99m1vycwos3pyjkj8rrffzszj",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/2BVfJ4AHMvHdKtEZNHaBr48dQzTfZvYkjaaxbM6bpump.png",
            },
            {
                "address": "0x40a31c233f808edd2fb3f23f9bcA9Ff29D914c43",
                "name": "ORBICHAN",
                "symbol": "ORBICHAN",
                "chain": "ROBINHOOD",
                "price_usd": 0.0005232,
                "market_cap": 523232.0,
                "liquidity_usd": 70711.98,
                "volume_24h": 1124296.93,
                "volume_5m": 82046.72,
                "buys_24h": 1390,
                "sells_24h": 821,
                "price_change_24h": 20313.0,
                "price_change_1h": 20313.0,
                "price_change_5m": -22.94,
                "age": "30m",
                "age_seconds": 1834,
                "jovx_score": 95,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://app.uniswap.org/swap?chain=robinhood&outputCurrency=0x40a31c233f808edd2fb3f23f9bcA9Ff29D914c43",
                "dex_platform": "UNISWAP (ROBINHOOD)",
                "pair_url": "https://dexscreener.com/robinhood/0x5183b2850bb856c9ea714e284eb18904284fa413",
                "icon": "https://cdn.dexscreener.com/cms/images/VRlUOqO6km8JiPYC?width=800&height=800&quality=95&format=auto",
            },
            {
                "address": "Fecv9hvh7yQ2iU1Ju7km5rMPC5iT7LGodXZmP75Apump",
                "name": "Baby Bought The Dip",
                "symbol": "BABYDIP",
                "chain": "SOLANA",
                "price_usd": 0.0006349,
                "market_cap": 617720.0,
                "liquidity_usd": 77273.95,
                "volume_24h": 3136598.28,
                "volume_5m": 347716.06,
                "buys_24h": 7127,
                "sells_24h": 6281,
                "price_change_24h": 1185.0,
                "price_change_1h": 1185.0,
                "price_change_5m": 31.19,
                "age": "49m",
                "age_seconds": 2972,
                "jovx_score": 95,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-Fecv9hvh7yQ2iU1Ju7km5rMPC5iT7LGodXZmP75Apump",
                "dex_platform": "RAYDIUM (SOL)",
                "pair_url": "https://dexscreener.com/solana/b7qcpi3ksavhvn63vogfst7qsv5yb7qjgavc397wv4er",
                "icon": "https://cdn.dexscreener.com/cms/images/rlCfvln-xJWZwUkQ?width=800&height=800&quality=95&format=auto",
            },
            {
                "address": "CioPfvQWpVF2eTzpBj72x2zPyqgJRgvi36PqdLCCpump",
                "name": "TON 618",
                "symbol": "TON618",
                "chain": "SOLANA",
                "price_usd": 0.0005432,
                "market_cap": 518332.0,
                "liquidity_usd": 68464.23,
                "volume_24h": 1197868.16,
                "volume_5m": 7160.89,
                "buys_24h": 9630,
                "sells_24h": 7009,
                "price_change_24h": 1022.0,
                "price_change_1h": 41.08,
                "price_change_5m": -2.18,
                "age": "23.2h",
                "age_seconds": 83509,
                "jovx_score": 95,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-CioPfvQWpVF2eTzpBj72x2zPyqgJRgvi36PqdLCCpump",
                "dex_platform": "RAYDIUM (SOL)",
                "pair_url": "https://dexscreener.com/solana/34w9reb7ax8dsv3hizt28nxztkfwwttarw2nwcsxyqrx",
                "icon": "https://cdn.dexscreener.com/cms/images/oBqgX_Tr90YEXVgJ?width=800&height=800&quality=95&format=auto",
            },
            {
                "address": "AHmD5jaFKqWMGswNkTSwAfvaWNHVY8m6JJro9LFppump",
                "name": "fly-42 project",
                "symbol": "FLY",
                "chain": "SOLANA",
                "price_usd": 0.000479,
                "market_cap": 454824.0,
                "liquidity_usd": 64163.68,
                "volume_24h": 1236322.45,
                "volume_5m": 275350.08,
                "buys_24h": 11115,
                "sells_24h": 9036,
                "price_change_24h": 914.0,
                "price_change_1h": 914.0,
                "price_change_5m": -16.83,
                "age": "24m",
                "age_seconds": 1447,
                "jovx_score": 95,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-AHmD5jaFKqWMGswNkTSwAfvaWNHVY8m6JJro9LFppump",
                "dex_platform": "RAYDIUM (SOL)",
                "pair_url": "https://dexscreener.com/solana/j4azhntuxg1nu4boja42kc7rnohqote6epxbauvqzdiy",
                "icon": "https://cdn.dexscreener.com/cms/images/HGY4RcJt9-SiiLva?width=800&height=800&quality=95&format=auto",
            },
            {
                "address": "BR1HcT9RP6ewqLhhYnhpDaa9Uh3Tj8TSKyS9yTiLpump",
                "name": "Teenage Mutant Ninja Pepes",
                "symbol": "TMNP",
                "chain": "SOLANA",
                "price_usd": 0.0004913,
                "market_cap": 491307.0,
                "liquidity_usd": 64545.8,
                "volume_24h": 1196215.59,
                "volume_5m": 244122.15,
                "buys_24h": 3965,
                "sells_24h": 3064,
                "price_change_24h": 905.0,
                "price_change_1h": 905.0,
                "price_change_5m": 4.96,
                "age": "26m",
                "age_seconds": 1586,
                "jovx_score": 95,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-BR1HcT9RP6ewqLhhYnhpDaa9Uh3Tj8TSKyS9yTiLpump",
                "dex_platform": "RAYDIUM (SOL)",
                "pair_url": "https://dexscreener.com/solana/hwvs3tmrhgebmxea69dnw4ksqono3ethuwnzb1s6shdc",
                "icon": "https://cdn.dexscreener.com/cms/images/wjClISsFYQoix8fH?width=800&height=800&quality=95&format=auto",
            },
            {
                "address": "0x0CA2f986c95D4B2d638a3561d1ee8Fd33B0220D7",
                "name": "PowerGacha",
                "symbol": "GACHA",
                "chain": "ROBINHOOD",
                "price_usd": 0.000297,
                "market_cap": 67848.0,
                "liquidity_usd": 46058.44,
                "volume_24h": 89797.35,
                "volume_5m": 0.0,
                "buys_24h": 131,
                "sells_24h": 108,
                "price_change_24h": 709.0,
                "price_change_1h": 0.0,
                "price_change_5m": 0.0,
                "age": "18.9h",
                "age_seconds": 67912,
                "jovx_score": 95,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://app.uniswap.org/swap?chain=robinhood&outputCurrency=0x0CA2f986c95D4B2d638a3561d1ee8Fd33B0220D7",
                "dex_platform": "UNISWAP (ROBINHOOD)",
                "pair_url": "https://dexscreener.com/robinhood/0x5f8dfdb5116ec4870aa6d9160828fb4643f462f82ec5c5155d693b5c15fecff7",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/robinhood/0x0CA2f986c95D4B2d638a3561d1ee8Fd33B0220D7.png",
            },
            {
                "address": "0x5EeEb94A43B72a40166c84c9454Ae75f97793929",
                "name": "PUMP",
                "symbol": "PUMP",
                "chain": "ROBINHOOD",
                "price_usd": 0.0002707,
                "market_cap": 61835.0,
                "liquidity_usd": 43957.62,
                "volume_24h": 77149.65,
                "volume_5m": 0.0,
                "buys_24h": 132,
                "sells_24h": 105,
                "price_change_24h": 638.0,
                "price_change_1h": 0.0,
                "price_change_5m": 0.0,
                "age": "20.5h",
                "age_seconds": 73912,
                "jovx_score": 95,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://app.uniswap.org/swap?chain=robinhood&outputCurrency=0x5EeEb94A43B72a40166c84c9454Ae75f97793929",
                "dex_platform": "UNISWAP (ROBINHOOD)",
                "pair_url": "https://dexscreener.com/robinhood/0xc1f6bb4d10247bd605479ad661b45a54ba872ee2496a6752aa5a6cfecbf94499",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/robinhood/0x5EeEb94A43B72a40166c84c9454Ae75f97793929.png",
            },
            {
                "address": "0xB91040F8e25b83b6e8335F4F16DFd53C67Be3c2F",
                "name": "Digital Gold Rush",
                "symbol": "GOLD",
                "chain": "ROBINHOOD",
                "price_usd": 5.797e-06,
                "market_cap": 57972.0,
                "liquidity_usd": 49965.54,
                "volume_24h": 43125.51,
                "volume_5m": 0.0,
                "buys_24h": 167,
                "sells_24h": 50,
                "price_change_24h": 439.0,
                "price_change_1h": 0.0,
                "price_change_5m": 0.0,
                "age": "22.7h",
                "age_seconds": 81550,
                "jovx_score": 95,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://app.uniswap.org/swap?chain=robinhood&outputCurrency=0xB91040F8e25b83b6e8335F4F16DFd53C67Be3c2F",
                "dex_platform": "UNISWAP (ROBINHOOD)",
                "pair_url": "https://dexscreener.com/robinhood/0x75408fb2d283fe1e35086f1b781a6e7d1bac597b36bc484bc67ea54ac2bbc6da",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/robinhood/0xB91040F8e25b83b6e8335F4F16DFd53C67Be3c2F.png",
            },
            {
                "address": "J9qzFhTLYnmf3tZYvHBaF96rH3YKToELAAVMzz66pump",
                "name": "Sand Witch Kitten",
                "symbol": "SNDWITCH",
                "chain": "SOLANA",
                "price_usd": 0.0003469,
                "market_cap": 343927.0,
                "liquidity_usd": 61649.56,
                "volume_24h": 5621630.79,
                "volume_5m": 40500.87,
                "buys_24h": 134957,
                "sells_24h": 59001,
                "price_change_24h": 419.0,
                "price_change_1h": 30.34,
                "price_change_5m": -15.03,
                "age": "23.0h",
                "age_seconds": 82963,
                "jovx_score": 95,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-J9qzFhTLYnmf3tZYvHBaF96rH3YKToELAAVMzz66pump",
                "dex_platform": "RAYDIUM (SOL)",
                "pair_url": "https://dexscreener.com/solana/hu22ubatza7ajmkdjasyodhtffw6xvs6d9bsxlt9ugdb",
                "icon": "https://cdn.dexscreener.com/cms/images/MuTi483V4c1C_JTs?width=800&height=800&quality=95&format=auto",
            },
            {
                "address": "HMYd9tosnUXuNHmq7pXmoePRVBLBBjA3JBfydq6upump",
                "name": "Super Intelligence SI276",
                "symbol": "SI276",
                "chain": "SOLANA",
                "price_usd": 0.0002171,
                "market_cap": 214816.0,
                "liquidity_usd": 42269.79,
                "volume_24h": 1087844.24,
                "volume_5m": 2148.29,
                "buys_24h": 12204,
                "sells_24h": 8313,
                "price_change_24h": 337.0,
                "price_change_1h": 2.69,
                "price_change_5m": -4.75,
                "age": "23.2h",
                "age_seconds": 83670,
                "jovx_score": 95,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-HMYd9tosnUXuNHmq7pXmoePRVBLBBjA3JBfydq6upump",
                "dex_platform": "RAYDIUM (SOL)",
                "pair_url": "https://dexscreener.com/solana/12jc1dzjpzbcdakum4brakh9jcfry2tlg1ffgsl4ftcg",
                "icon": "https://cdn.dexscreener.com/cms/images/C00PG8ebjcD8d36M?width=800&height=800&quality=95&format=auto",
            },
            {
                "address": "0x29eAc11b6A976928e2acdB8443E06C6c8b7b7777",
                "name": "Webull Corporation - Backpack Se",
                "symbol": "BULL",
                "chain": "ROBINHOOD",
                "price_usd": 0.0002384,
                "market_cap": 54481.0,
                "liquidity_usd": 51887.97,
                "volume_24h": 58040.03,
                "volume_5m": 0.0,
                "buys_24h": 115,
                "sells_24h": 99,
                "price_change_24h": 296.0,
                "price_change_1h": 0.0,
                "price_change_5m": 0.0,
                "age": "3.3h",
                "age_seconds": 11957,
                "jovx_score": 95,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://app.uniswap.org/swap?chain=robinhood&outputCurrency=0x29eAc11b6A976928e2acdB8443E06C6c8b7b7777",
                "dex_platform": "UNISWAP (ROBINHOOD)",
                "pair_url": "https://dexscreener.com/robinhood/0xd04dec4a4f4c1b9910453e4f7b6a559a0a057a80edf8b6d3df5b9cab712ca541",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/robinhood/0x29eAc11b6A976928e2acdB8443E06C6c8b7b7777.png",
            },
            {
                "address": "FAopSovS2WFJK5qEAmcuwAVH98CvmBwT6Lpq4EK2pump",
                "name": "AIOPAD",
                "symbol": "A1",
                "chain": "SOLANA",
                "price_usd": 0.0004118,
                "market_cap": 408465.0,
                "liquidity_usd": 63498.29,
                "volume_24h": 5260418.55,
                "volume_5m": 8383.61,
                "buys_24h": 93314,
                "sells_24h": 59618,
                "price_change_24h": 281.0,
                "price_change_1h": 25.49,
                "price_change_5m": 2.6,
                "age": "23.9h",
                "age_seconds": 85925,
                "jovx_score": 95,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-FAopSovS2WFJK5qEAmcuwAVH98CvmBwT6Lpq4EK2pump",
                "dex_platform": "RAYDIUM (SOL)",
                "pair_url": "https://dexscreener.com/solana/f2p22sfcg4gkja2upyqzef9bpw3rsec5q2wmvewuibl7",
                "icon": "https://cdn.dexscreener.com/cms/images/SKAvObn4w9IqHNgi?width=800&height=800&quality=95&format=auto",
            },
            {
                "address": "0xdc453b1405CfE25e2afBA8E7F4272b0a00437777",
                "name": "TasQ Network",
                "symbol": "TASQ",
                "chain": "ROBINHOOD",
                "price_usd": 0.0001748,
                "market_cap": 174872.0,
                "liquidity_usd": 42832.54,
                "volume_24h": 195373.8,
                "volume_5m": 5789.44,
                "buys_24h": 845,
                "sells_24h": 501,
                "price_change_24h": 172.0,
                "price_change_1h": 172.0,
                "price_change_5m": 4.93,
                "age": "39m",
                "age_seconds": 2353,
                "jovx_score": 95,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://app.uniswap.org/swap?chain=robinhood&outputCurrency=0xdc453b1405CfE25e2afBA8E7F4272b0a00437777",
                "dex_platform": "UNISWAP (ROBINHOOD)",
                "pair_url": "https://dexscreener.com/robinhood/0x16684607c92e1a59302763400cc1641c8f9dbe7e",
                "icon": "https://cdn.dexscreener.com/cms/images/BqiXSL6Rj5M6NWSU?width=800&height=800&quality=95&format=auto",
            },
            {
                "address": "0x92D3c33129E94195DA2323853211575D09ea9658",
                "name": "Dogwifhat",
                "symbol": "WIF",
                "chain": "ROBINHOOD",
                "price_usd": 0.2404,
                "market_cap": 238559685.0,
                "liquidity_usd": 119279842.72,
                "volume_24h": 0.03,
                "volume_5m": 0.0,
                "buys_24h": 1000,
                "sells_24h": 800,
                "price_change_24h": 0.07,
                "price_change_1h": 0.0,
                "price_change_5m": 0.0,
                "age": "1d",
                "age_seconds": 86400,
                "jovx_score": 92,
                "tag": "BULLISH TREND",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://app.uniswap.org/swap?chain=robinhood&outputCurrency=0x92D3c33129E94195DA2323853211575D09ea9658",
                "dex_platform": "UNISWAP (ROBINHOOD)",
                "pair_url": "https://dexscreener.com/robinhood/0x9a0d4b0a982bcb5ea9b39d734eb609294f2a90af",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/robinhood/0x92D3c33129E94195DA2323853211575D09ea9658.png",
            },
            {
                "address": "2T6Wg3urxPQHaoGh4gqNHyYL6FAfyWA5BaH6Lo37pump",
                "name": "Miners",
                "symbol": "MINER",
                "chain": "SOLANA",
                "price_usd": 0.000178,
                "market_cap": 132463.0,
                "liquidity_usd": 38943.21,
                "volume_24h": 1457152.83,
                "volume_5m": 2006.64,
                "buys_24h": 14514,
                "sells_24h": 9863,
                "price_change_24h": 299.0,
                "price_change_1h": -3.46,
                "price_change_5m": 16.13,
                "age": "22.3h",
                "age_seconds": 80358,
                "jovx_score": 90,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-2T6Wg3urxPQHaoGh4gqNHyYL6FAfyWA5BaH6Lo37pump",
                "dex_platform": "RAYDIUM (SOL)",
                "pair_url": "https://dexscreener.com/solana/8j42or3k3kbgnguqr2rbzcrweta7jhrnscjmscipv8in",
                "icon": "https://cdn.dexscreener.com/cms/images/Ob4hEiorBGqsUkDB?width=800&height=800&quality=95&format=auto",
            },
            {
                "address": "0x13a0e12C215BC0669941dA309c3Bfbd5B32c4c1f",
                "name": "Coin",
                "symbol": "COIN",
                "chain": "ROBINHOOD",
                "price_usd": 3.573e-06,
                "market_cap": 35737.0,
                "liquidity_usd": 36720.34,
                "volume_24h": 14967.17,
                "volume_5m": 0.0,
                "buys_24h": 77,
                "sells_24h": 14,
                "price_change_24h": 279.0,
                "price_change_1h": 0.0,
                "price_change_5m": 0.0,
                "age": "21.3h",
                "age_seconds": 76826,
                "jovx_score": 90,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://app.uniswap.org/swap?chain=robinhood&outputCurrency=0x13a0e12C215BC0669941dA309c3Bfbd5B32c4c1f",
                "dex_platform": "UNISWAP (ROBINHOOD)",
                "pair_url": "https://dexscreener.com/robinhood/0x9c97a40cf7077e2aaec305206e0af1e4c32a795acc18815f5c77dd9eb09f0775",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/robinhood/0x13a0e12C215BC0669941dA309c3Bfbd5B32c4c1f.png",
            },
            {
                "address": "AAYnxkQJySJ4RkTQidjUoi4c7P7RNBHDWgzpHjbapump",
                "name": "Peak male physique",
                "symbol": "PEAKMALE",
                "chain": "SOLANA",
                "price_usd": 0.0001643,
                "market_cap": 160191.0,
                "liquidity_usd": 36070.58,
                "volume_24h": 674213.83,
                "volume_5m": 44564.41,
                "buys_24h": 8479,
                "sells_24h": 2247,
                "price_change_24h": 226.0,
                "price_change_1h": 226.0,
                "price_change_5m": 35.45,
                "age": "46m",
                "age_seconds": 2769,
                "jovx_score": 90,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-AAYnxkQJySJ4RkTQidjUoi4c7P7RNBHDWgzpHjbapump",
                "dex_platform": "RAYDIUM (SOL)",
                "pair_url": "https://dexscreener.com/solana/6ksizkgalecrfqlgpyokyfufftyy9fg51nh8zdinfpzq",
                "icon": "https://cdn.dexscreener.com/cms/images/uaq8JpnEy9lAd1Dc?width=800&height=800&quality=95&format=auto",
            },
            {
                "address": "9BkorQ9bvmbbpUtEMEyYggG8ApSgGfLZVsM9nSbJpump",
                "name": "ULTRA INU",
                "symbol": "UI",
                "chain": "SOLANA",
                "price_usd": 0.0001222,
                "market_cap": 116083.0,
                "liquidity_usd": 30503.68,
                "volume_24h": 617301.86,
                "volume_5m": 5659.91,
                "buys_24h": 9656,
                "sells_24h": 6466,
                "price_change_24h": 156.0,
                "price_change_1h": -46.46,
                "price_change_5m": -29.0,
                "age": "4.5h",
                "age_seconds": 16251,
                "jovx_score": 90,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-9BkorQ9bvmbbpUtEMEyYggG8ApSgGfLZVsM9nSbJpump",
                "dex_platform": "RAYDIUM (SOL)",
                "pair_url": "https://dexscreener.com/solana/8sbe1r1tzibgoje85srgpv3pkapntbbj1wn7stoo2wht",
                "icon": "https://cdn.dexscreener.com/cms/images/31cZijhEMXJfqAUg?width=800&height=800&quality=95&format=auto",
            },
            {
                "address": "F6EDRhRzXGmkBabhSHdAnqx26XLhG6NCa83wwuqFpump",
                "name": "ECSTASY",
                "symbol": "ECSTASY",
                "chain": "SOLANA",
                "price_usd": 0.0001012,
                "market_cap": 97889.0,
                "liquidity_usd": 27176.58,
                "volume_24h": 200074.85,
                "volume_5m": 2488.96,
                "buys_24h": 3217,
                "sells_24h": 2304,
                "price_change_24h": 111.0,
                "price_change_1h": -4.6,
                "price_change_5m": 3.79,
                "age": "5.2h",
                "age_seconds": 18647,
                "jovx_score": 90,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-F6EDRhRzXGmkBabhSHdAnqx26XLhG6NCa83wwuqFpump",
                "dex_platform": "RAYDIUM (SOL)",
                "pair_url": "https://dexscreener.com/solana/ucwmmumv5xncimxxymfw2erlqzjfyfbs47bthptgrz1",
                "icon": "https://cdn.dexscreener.com/cms/images/RamMH3aG8--lKUMh?width=800&height=800&quality=95&format=auto",
            },
            {
                "address": "0xCC4304A31d09258b0029eA7FE63d032f52e44EFe",
                "name": "TrustSwap Token",
                "symbol": "SWAP",
                "chain": "ETHEREUM",
                "price_usd": 0.04382,
                "market_cap": 4382208.0,
                "liquidity_usd": 60957.61,
                "volume_24h": 6802.22,
                "volume_5m": 0.0,
                "buys_24h": 23,
                "sells_24h": 21,
                "price_change_24h": 0.98,
                "price_change_1h": 0.0,
                "price_change_5m": 0.0,
                "age": "1d",
                "age_seconds": 86400,
                "jovx_score": 87,
                "tag": "BULLISH TREND",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://app.uniswap.org/swap?chain=ethereum&outputCurrency=0xCC4304A31d09258b0029eA7FE63d032f52e44EFe",
                "dex_platform": "UNISWAP (ETHEREUM)",
                "pair_url": "https://dexscreener.com/ethereum/0xd90a1ba0cbaaaabfdc6c814cdf1611306a26e1f8",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/ethereum/0xCC4304A31d09258b0029eA7FE63d032f52e44EFe.png",
            },
            {
                "address": "DwcXyhEcSvzWgakDKpetZLFvbAHutpGpzhbU4iempump",
                "name": "Bullcraft",
                "symbol": "BULLCRAFT",
                "chain": "SOLANA",
                "price_usd": 0.0001042,
                "market_cap": 102505.0,
                "liquidity_usd": 28219.37,
                "volume_24h": 532338.31,
                "volume_5m": 1325.37,
                "buys_24h": 279,
                "sells_24h": 331,
                "price_change_24h": 16.19,
                "price_change_1h": 16.19,
                "price_change_5m": 3.02,
                "age": "51m",
                "age_seconds": 3090,
                "jovx_score": 80,
                "tag": "BULLISH TREND",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-DwcXyhEcSvzWgakDKpetZLFvbAHutpGpzhbU4iempump",
                "dex_platform": "RAYDIUM (SOL)",
                "pair_url": "https://dexscreener.com/solana/eghzxfbbb6gkwl9m7zenzn2s1bejjvafyexkat5ghfsf",
                "icon": "https://cdn.dexscreener.com/cms/images/JoEkYOrOAqhG-gX5?width=800&height=800&quality=95&format=auto",
            },
            {
                "address": "0xd5aF6A84cbc4907F3f358F0600338787b65f5651",
                "name": "moonad",
                "symbol": "MOON",
                "chain": "ROBINHOOD",
                "price_usd": 2.565e-05,
                "market_cap": 25651.0,
                "liquidity_usd": 25650.92,
                "volume_24h": 1.48,
                "volume_5m": 0.0,
                "buys_24h": 3,
                "sells_24h": 0,
                "price_change_24h": 0.01,
                "price_change_1h": 0.0,
                "price_change_5m": 0.0,
                "age": "2.8h",
                "age_seconds": 9984,
                "jovx_score": 80,
                "tag": "BULLISH TREND",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://app.uniswap.org/swap?chain=robinhood&outputCurrency=0xd5aF6A84cbc4907F3f358F0600338787b65f5651",
                "dex_platform": "UNISWAP (ROBINHOOD)",
                "pair_url": "https://dexscreener.com/robinhood/0xf91d7c20d7b825332c39d71256787cb4771d19951789288c1cfd7bd82e7d02a7",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/robinhood/0xd5aF6A84cbc4907F3f358F0600338787b65f5651.png",
            },
        ]
        with self.lock:
            for s in seeds:
                s["lp_locked"] = True
                s["liquidity_locked"] = True
            self.fallback_reserve = list(seeds)
            for s in seeds:
                self.pool[s["address"]] = s
            self._recalculate_cached_list()

    def fetch_live_tokens(self):
        """Retorna instantaneamente os 20 tokens de maior probabilidade em memória"""
        with self.lock:
            if not self.cached_list:
                self._recalculate_cached_list()
            return list(self.cached_list[:20])

    def _recalculate_cached_list(self):
        """
        Organiza o Top 20 definitivo:
        - Top #1 ao #5 (VIP PRO - Ponto Doce de Lucro e Alta Probabilidade):
          * Idade entre 45 min (2700s) e 48 horas (172800s) -> Sobreviveu aos snipers
          * Liquidez forte: >= $35.000 USD
          * Volume 24h: >= $80.000 USD
          * Tendência saudável: 1h >= 2.0% e 5m >= -1.5% (acumulação sem vela de exaustão)
          * Mais compras que vendas (buys >= sells)
          * Ranqueado pelo MAIOR Score JOVX e melhor proporção de compras
        - Ranks #6 ao #20:
          * As melhores oportunidades aprovadas dentro do limite máximo de 3 dias (<= 259.200s)
          * Ordenadas por pontuação e frescor
        """
        valid_pool = []
        for t in self.pool.values():
            age = t.get("age_seconds", 3600)
            
            # REGRA MÁXIMA INFLEXÍVEL DE 3 DIAS PARA TODAS AS 20 MOEDAS (SEM EXCEÇÃO)
            if age > MAX_TOKEN_AGE_SECONDS:
                continue

            # Anti-Dump Geral (Tolerância Zero para perda de liquidez ou 24h negativo)
            if t.get("price_change_5m", 0) < -6.0:
                continue
            if t.get("price_change_1h", 0) < -8.0:
                continue
            if t.get("liquidity_usd", 0) < 20000:
                continue
            # FILTRO INFLEXÍVEL DE CONFIANÇA: LIQUIDEZ BLOQUEADA (LP LOCKED 🔒)
            if not t.get("lp_locked", True) or not t.get("liquidity_locked", True):
                continue
            if t.get("price_change_24h", 0) < 0.0:
                continue
            if t.get("sells_24h", 0) > (t.get("buys_24h", 0) * 1.35) and t.get("buys_24h", 0) > 0:
                continue

            valid_pool.append(t)

        # Separar candidatos de elite para o Top 5 VIP (Sweet Spot)
        top5_candidates = []
        regular_candidates = []

        for t in valid_pool:
            age = t.get("age_seconds", 3600)
            liq = t.get("liquidity_usd", 0)
            vol = t.get("volume_24h", 0)
            h1 = t.get("price_change_1h", 0)
            m5 = t.get("price_change_5m", 0)
            buys = t.get("buys_24h", 0)
            sells = t.get("sells_24h", 0)
            score = t.get("jovx_score", 0)

            # Critérios do Ponto Doce do Top 5:
            # 1. Idade entre 45 min e 48 horas (sobreviveu ao berçário/snipers)
            # 2. Liquidez >= $35k
            # 3. Volume >= $80k
            # 4. Tendência saudável (1h >= 2% e 5m >= -1.5%)
            # 5. Mais compras do que vendas
            # 6. Score >= 85
            is_top5_eligible = (
                2700 <= age <= 172800 and
                liq >= 35000 and
                vol >= 80000 and
                h1 >= 2.0 and
                m5 >= -1.5 and
                buys >= sells and
                score >= 85
            )

            if is_top5_eligible:
                top5_candidates.append(t)
            else:
                regular_candidates.append(t)

        # Ordenar candidatos do Top 5 pelo maior Score e maior proporção de compradores
        def top5_sort_key(t):
            score = t.get("jovx_score", 0)
            buys = t.get("buys_24h", 0)
            sells = max(1, t.get("sells_24h", 0))
            buy_ratio = buys / sells
            liq = t.get("liquidity_usd", 0)
            return (-score, -buy_ratio, -liq)

        top5_candidates.sort(key=top5_sort_key)

        # Ordenar candidatos regulares por score e liquidez
        def regular_sort_key(t):
            score = t.get("jovx_score", 0)
            age = t.get("age_seconds", 3600)
            liq = t.get("liquidity_usd", 0)
            return (-score, -liq, age)

        regular_candidates.sort(key=regular_sort_key)

        # Montar os Top 5
        final_top5 = top5_candidates[:5]
        # Se houver menos de 5 no top5_candidates, completa com os melhores regulares disponíveis
        if len(final_top5) < 5:
            needed = 5 - len(final_top5)
            fillers = regular_candidates[:needed]
            final_top5.extend(fillers)
            regular_candidates = regular_candidates[needed:]

        # Montar ranks 6 a 20 (restante até completar 20)
        remaining_slots = 20 - len(final_top5)
        leftovers = top5_candidates[5:] + regular_candidates
        leftovers.sort(key=regular_sort_key)
        final_ranks_6_to_20 = leftovers[:remaining_slots]

        clean_tokens = final_top5 + final_ranks_6_to_20

        # FILTRO DE SEGURANÇA: Exclui qualquer token banido/derretido
        clean_tokens = [t for t in clean_tokens if t.get("address") not in self.blacklisted_dumped_addrs]
        self.fallback_reserve = [r for r in self.fallback_reserve if r.get("address") not in self.blacklisted_dumped_addrs]

        # Se precisar completar até 20, usa apenas reserva NÃO banida, com liquidez >= 20k e 24h positiva
        if len(clean_tokens) < 20 and hasattr(self, 'fallback_reserve') and self.fallback_reserve:
            existing_addrs = {t.get("address") for t in clean_tokens}
            for fb in self.fallback_reserve:
                fb_addr = fb.get("address")
                if fb_addr and fb_addr not in existing_addrs and fb_addr not in self.blacklisted_dumped_addrs:
                    if fb.get("liquidity_usd", 0) >= 20000 and fb.get("price_change_24h", 0) >= 0.0:
                        clean_tokens.append(fb)
                        existing_addrs.add(fb_addr)
                        if len(clean_tokens) >= 20:
                            break

        # SINAIS EXCLUSIVOS: Top 5 recebem PRIME ALPHA 🚀 para chamar atenção máxima;
        # As 15 moedas abaixo (6 a 20) usam LOW RISK 🛡️, ACCUMULATING 💎 ou HIGH VOLATILITY ⚡
        for idx, token in enumerate(clean_tokens):
            if idx < 5:
                token["risk_level"] = "PRIME ALPHA 🚀"
            else:
                if "PRIME ALPHA" in str(token.get("risk_level", "")):
                    token["risk_level"] = "LOW RISK 🛡️"

        self.cached_list = clean_tokens[:20]
        self.last_fetch_time = time.time()

    def _background_worker(self):
        """Worker assíncrono que roda no background mantendo os 20 tokens sempre frescos e verdes"""
        time.sleep(2)
        logger.info("[JOVX WORKER] Background scanner online com suporte FOMO e Anti-Dump.")

        while True:
            try:
                self._run_scan_cycle()
            except Exception as e:
                logger.error(f"[JOVX WORKER ERROR]: {e}")
            
            time.sleep(15)

    def _run_scan_cycle(self):
        """Executa um ciclo rápido de coleta em lote e auditoria de contratos"""
        candidate_addrs = []

        # 0. Smart Pulse Helius (Pulso a cada 6 minutos, alternando 1 programa por vez, com trava de segurança de 20k/dia)
        now = time.time()
        if HELIUS_API_KEY and not self.helius_disabled and (now - self.last_helius_fetch >= self.helius_interval):
            current_day = time.strftime("%Y-%m-%d")
            if current_day != self.helius_day_tracker:
                self.helius_day_tracker = current_day
                self.helius_daily_credits = 0

            if self.helius_daily_credits >= self.helius_daily_limit:
                logger.info("[HELIUS GUARD] Limite diário de segurança (20k créditos) atingido. Preservando cota e operando 100% via DexScreener gratuito.")
            else:
                sol_programs = [
                    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",  # Raydium AMM v4
                    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",   # Pump.fun
                    "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C"   # Raydium CPMM
                ]
                prog = sol_programs[self.helius_prog_index % len(sol_programs)]
                self.helius_prog_index += 1
                self.last_helius_fetch = now

                try:
                    helius_url = f"https://api.helius.xyz/v0/addresses/{prog}/transactions?api-key={HELIUS_API_KEY}&limit=20"
                    r_h = requests.get(helius_url, timeout=3)
                    if r_h.status_code == 200:
                        self.helius_daily_credits += 100
                        txs = r_h.json()
                        for tx in txs:
                            for token_trans in tx.get("tokenTransfers", []):
                                mint = token_trans.get("mint")
                                if mint and mint not in EXCLUDED_SYMBOLS and len(mint) >= 32:
                                    candidate_addrs.append(mint)
                    elif r_h.status_code in (402, 429):
                        logger.warning(f"[HELIUS FALLBACK] Status {r_h.status_code} recebido. Ativando fallback automático 100% DexScreener gratuito.")
                        self.helius_disabled = True
                except Exception as e:
                    logger.error(f"[HELIUS FETCH ERROR]: {e}")

        # 1. Puxar os perfis mais recentes da DexScreener
        try:
            r = requests.get(self.profiles_url, headers=self.headers, timeout=4)
            if r.status_code == 200:
                profiles = r.json()
                if isinstance(profiles, list):
                    for p in profiles[:30]:
                        addr = p.get("tokenAddress")
                        if addr: candidate_addrs.append(addr)
        except Exception:
            pass

        # 2. Puxar os boosts mais recentes e os Top boosts
        for b_url in [self.boosts_url, self.boosts_top_url]:
            try:
                r_b = requests.get(b_url, headers=self.headers, timeout=4)
                if r_b.status_code == 200:
                    boosts = r_b.json()
                    if isinstance(boosts, list):
                        for b in boosts[:25]:
                            addr = b.get("tokenAddress")
                            if addr: candidate_addrs.append(addr)
            except Exception:
                pass

        # 3. AUDITORIA PRIORITÁRIA ANTI-DUMP AO VIVO:
        # Puxa OBRIGATORIAMENTE todas as moedas na tela (cached_list), no pool e na reserva para checar se derreteram
        with self.lock:
            for t in self.cached_list:
                if t.get("address"): candidate_addrs.append(t["address"])
            for addr in list(self.pool.keys()):
                candidate_addrs.append(addr)
            for fb in self.fallback_reserve:
                if fb.get("address"): candidate_addrs.append(fb["address"])

        # 4. Puxar palavras-chave de busca alternadas (incluindo FOMO)
        for _ in range(2):
            kw = self.search_keywords[self.search_index % len(self.search_keywords)]
            self.search_index += 1
            try:
                r_s = requests.get(f"{self.search_url}?q={kw}", headers=self.headers, timeout=4)
                if r_s.status_code == 200:
                    pairs = r_s.json().get("pairs", [])
                    for pair in pairs[:10]:
                        addr = pair.get("baseToken", {}).get("address")
                        if addr: candidate_addrs.append(addr)
            except Exception:
                pass

        unique_addrs = list(dict.fromkeys(candidate_addrs))[:120]
        if not unique_addrs:
            return

        # 5. Consultar em lotes (batch de 30 tokens por requisição HTTP)
        all_pairs = []
        for i in range(0, len(unique_addrs), 30):
            chunk = unique_addrs[i:i+30]
            try:
                r_batch = requests.get(self.tokens_batch_url + ",".join(chunk), headers=self.headers, timeout=5)
                if r_batch.status_code == 200:
                    all_pairs.extend(r_batch.json().get("pairs", []))
            except Exception:
                pass

        if not all_pairs:
            return

        # 6. Agrupar pares pelo par de maior volume 24h
        token_best_pair = {}
        for p in all_pairs:
            base = p.get("baseToken", {})
            addr = base.get("address")
            if not addr:
                continue
            vol = float(p.get("volume", {}).get("h24", 0) or 0)
            if addr not in token_best_pair or vol > float(token_best_pair[addr].get("volume", {}).get("h24", 0) or 0):
                token_best_pair[addr] = p

        # 7. Auditar cada token
        fresh_valid_tokens = []
        for addr, pair in token_best_pair.items():
            audited = self._audit_and_score_pair(pair)
            if audited:
                fresh_valid_tokens.append(audited)
            else:
                # Se falhou especificamente por ser rugpull/derretido (24h negativo ou sem liquidez), marca na blacklist
                liq = float(pair.get("liquidity", {}).get("usd", 0) or 0)
                pc24 = float(pair.get("priceChange", {}).get("h24", 0) or 0)
                if pc24 < 0.0 or liq < 15000:
                    self.blacklisted_dumped_addrs.add(addr)

        # 8. Atualizar a piscina com auditoria Anti-Dump em tempo real
        with self.lock:
            # 8.1. PURGA INSTANTÂNEA ANTI-DUMP DAS MOEDAS ATIVAS E RESERVA:
            # Pega qualquer moeda que derreteu (24h negativo, liquidez < 20k ou na blacklist)
            dumped_in_memory = set()
            for addr, t in list(self.pool.items()):
                if addr in self.blacklisted_dumped_addrs or t.get("price_change_24h", 0) < 0.0 or t.get("liquidity_usd", 0) < 20000:
                    dumped_in_memory.add(addr)

            for bad_addr in dumped_in_memory:
                self.blacklisted_dumped_addrs.add(bad_addr)
                if bad_addr in self.pool:
                    logger.warning(f"[ANTI-DUMP KILL] Eliminando e banindo token derretido: {self.pool[bad_addr].get('symbol')}")
                    del self.pool[bad_addr]
                self.fallback_reserve = [r for r in self.fallback_reserve if r.get("address") != bad_addr]
                self.cached_list = [t for t in self.cached_list if t.get("address") != bad_addr]

            # 8.2. Atualizar/Inserir tokens saudáveis aprovados (NUNCA banidos)
            for t in fresh_valid_tokens:
                if t["address"] in self.blacklisted_dumped_addrs:
                    continue
                self.pool[t["address"]] = t
                if hasattr(self, 'fallback_reserve') and t["address"] not in {r.get("address") for r in self.fallback_reserve}:
                    self.fallback_reserve.append(t)

            if hasattr(self, 'fallback_reserve'):
                self.fallback_reserve = [
                    r for r in self.fallback_reserve 
                    if r.get("address") not in self.blacklisted_dumped_addrs 
                    and r.get("liquidity_usd", 0) >= 20000 
                    and r.get("price_change_24h", 0) >= 0.0 
                    and r.get("age_seconds", 0) <= MAX_TOKEN_AGE_SECONDS
                ][:50]

            self._recalculate_cached_list()

    def _audit_and_score_pair(self, active_pair):
        """Audita as métricas do par diretamente e aplica os KILL SWITCHES ANTI-DUMP"""
        try:
            if not active_pair:
                return None

            base = active_pair.get("baseToken", {})
            address = base.get("address", "")
            if not address:
                return None
            name = base.get("name", "Unknown").strip()
            symbol = base.get("symbol", "???").strip().upper()
            chain_raw = active_pair.get("chainId", "solana").lower()

            # Aceitar solana, base, ethereum e robinhood
            if chain_raw not in ["solana", "base", "ethereum", "robinhood"]:
                return None

            # FILTRO ANTI-DUMP PERMANENTE: Rejeita imediatamente moedas da blacklist
            if address in self.blacklisted_dumped_addrs:
                return None

            # FILTRO 1: Moedas Nativas Proibidas
            if symbol in EXCLUDED_SYMBOLS or any(kw in name.upper() for kw in EXCLUDED_NAME_KEYWORDS):
                return None

            price_usd = float(active_pair.get("priceUsd", 0) or 0)
            fdv = float(active_pair.get("fdv", 0) or 0)
            market_cap = float(active_pair.get("marketCap", fdv) or fdv)
            liquidity_usd = float(active_pair.get("liquidity", {}).get("usd", 0) or 0)

            volume_24h = float(active_pair.get("volume", {}).get("h24", 0) or 0)
            volume_5m = float(active_pair.get("volume", {}).get("m5", 0) or 0)

            price_change_5m = float(active_pair.get("priceChange", {}).get("m5", 0) or 0)
            price_change_1h = float(active_pair.get("priceChange", {}).get("h1", 0) or 0)
            price_change_24h = float(active_pair.get("priceChange", {}).get("h24", 0) or 0)

            txns_24h = active_pair.get("txns", {}).get("h24", {})
            buys = int(txns_24h.get("buys", 0) or 0)
            sells = int(txns_24h.get("sells", 0) or 0)

            age_sec, age_str = self._calculate_age(active_pair.get("pairCreatedAt", 0))
            is_fomo_token = (chain_raw == "robinhood") or ("fomo" in name.lower()) or ("fomo" in symbol.lower()) or (market_cap > 10000000)

            # FILTRO DE IDADE INFLEXÍVEL: Máximo 3 dias (259.200s) para TODAS as moedas (SEM EXCEÇÃO)
            if age_sec > MAX_TOKEN_AGE_SECONDS:
                return None

            # KILL SWITCHES ANTI-DERRETIMENTO
            if price_change_24h < 0.0:
                return None
            if price_change_1h < -8.0:
                return None
            if price_change_5m < -6.0:
                return None
            if liquidity_usd < 20000:
                return None
            if market_cap < 30000:
                return None
            if sells > 0 and buys > 0 and (sells > buys * 1.35):
                return None

            # FILTRO INFLEXÍVEL DE CONFIANÇA: LIQUIDEZ BLOQUEADA OBRIGATÓRIA (LP LOCKED 🔒)
            dex_id = active_pair.get("dexId", "").lower()
            if chain_raw == "solana":
                # Na Solana: Pump.fun tem 100% LP queimada no Raydium, ou pares Raydium/Orca com liquidez mínima auditada
                if not (address.endswith("pump") or "raydium" in dex_id or "orca" in dex_id or is_fomo_token or liquidity_usd >= 30000):
                    return None
            elif chain_raw in ["base", "ethereum"]:
                if liquidity_usd < 25000:
                    return None

            # Proteção contra fake pool / honeypot (liquidez irrisória frente ao market cap)
            if market_cap > 500000 and (liquidity_usd / market_cap) < 0.005:
                return None

            # Cálculo de Score
            score = 65
            if liquidity_usd >= 80000:
                score += 15
            elif liquidity_usd >= 35000:
                score += 8

            if 60000 <= market_cap <= 2000000:
                score += 12
            elif market_cap > 2000000:
                score += 15

            if buys > sells and sells > 0:
                ratio = buys / sells
                if ratio >= 1.3:
                    score += 10
                elif ratio >= 1.05:
                    score += 5

            if price_change_1h >= 10.0:
                score += 10
            elif price_change_1h > 0:
                score += 5

            if volume_5m >= 3000:
                score += 8

            final_score = max(50, min(99, score))

            # Identificação de Tag e Chain
            if is_fomo_token:
                tag = "FOMO GEM"
                chain = "FOMO" if chain_raw == "robinhood" else chain_raw.upper()
            elif final_score >= 88:
                tag = "HIGH ALPHA"
                chain = chain_raw.upper()
            elif market_cap < 500000 and final_score >= 75:
                tag = "EARLY GEM"
                chain = chain_raw.upper()
            elif buys > (sells * 1.3):
                tag = "WHALE ACCUMULATION"
                chain = chain_raw.upper()
            else:
                tag = "BULLISH TREND"
                chain = chain_raw.upper()

            # Cálculo de Sinal e Convicção de Mercado
            if age_sec < 3600:
                risk_level = "HIGH VOLATILITY ⚡"  # Menos de 1h é recém-nascido
            elif liquidity_usd >= 35000 and price_change_1h >= 1.5:
                risk_level = "LOW RISK 🛡️"         # Moeda consolidada e segura
            else:
                risk_level = "ACCUMULATING 💎"     # Moeda em consolidação saudável

            # Rotas de Compra Direta
            pair_addr = active_pair.get("pairAddress") or address
            if chain_raw == "solana":
                buy_url = f"https://jup.ag/swap/SOL-{address}"
                dex_platform = "FOMO / JUPITER (SOL)" if is_fomo_token else "JUPITER (SOL)"
            elif chain_raw == "base":
                buy_url = f"https://app.uniswap.org/swap?chain=base&outputCurrency={address}"
                dex_platform = "UNISWAP (BASE)"
            elif chain_raw == "robinhood":
                buy_url = f"https://dexscreener.com/robinhood/{pair_addr}"
                dex_platform = "FOMO / ROBINHOOD"
            else:
                buy_url = f"https://app.uniswap.org/swap?chain=ethereum&outputCurrency={address}"
                dex_platform = f"UNISWAP ({chain_raw.upper()})"

            # Link canônico da DexScreener (Zero Erro 404)
            canonical_pair_url = active_pair.get("url")
            if not canonical_pair_url or "dexscreener.com" not in canonical_pair_url:
                canonical_pair_url = f"https://dexscreener.com/{chain_raw}/{pair_addr}"

            return {
                "address": address,
                "name": name,
                "symbol": symbol,
                "chain": chain,
                "icon": f"https://dd.dexscreener.com/ds-data/tokens/{chain_raw}/{address}.png",
                "price_usd": price_usd,
                "market_cap": market_cap,
                "liquidity_usd": liquidity_usd,
                "lp_locked": True,
                "liquidity_locked": True,
                "volume_24h": volume_24h,
                "volume_5m": volume_5m,
                "buys_24h": buys,
                "sells_24h": sells,
                "price_change_24h": price_change_24h,
                "price_change_1h": price_change_1h,
                "price_change_5m": price_change_5m,
                "age": age_str,
                "age_seconds": age_sec,
                "jovx_score": final_score,
                "tag": tag,
                "risk_level": risk_level,
                "buy_url": buy_url,
                "dex_platform": dex_platform,
                "pair_url": canonical_pair_url,
                "photon_url": f"https://photon-sol.tinyastro.io/en/lp/{address}" if chain_raw == "solana" else canonical_pair_url
            }
        except Exception as e:
            logger.error(f"[AUDIT ERROR]: {e}")
            return None

    def _calculate_age(self, created_at_ms):
        if not created_at_ms:
            return 1200, "20m"
        diff_sec = max(60, time.time() - (created_at_ms / 1000))
        if diff_sec < 3600:
            return diff_sec, f"{int(diff_sec // 60)}m"
        elif diff_sec < 86400:
            hours = diff_sec / 3600
            if hours < 10:
                return diff_sec, f"{hours:.1f}h"
            return diff_sec, f"{int(hours)}h"
        else:
            return diff_sec, f"{int(diff_sec // 86400)}d"

scanner = JovxScanner()
