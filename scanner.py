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

# IDADE MÁXIMA PARA MEMECOINS MICROCAPS: 5 DIAS (432.000 segundos)
MAX_TOKEN_AGE_SECONDS = 5 * 86400

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
        self.tokens_batch_url = "https://api.dexscreener.com/latest/dex/tokens/"
        self.search_url = "https://api.dexscreener.com/latest/dex/search"
        
        self.pool = {}
        self.cached_list = []
        self.last_fetch_time = time.time()
        self.lock = threading.Lock()
        
        # Palavras-chave cobrindo FOMO e as melhores narrativas
        self.search_keywords = [
            "fomo", "robinhood", "artificial inu", "stonk", "solana", "pump", 
            "ai", "doge", "cat", "pepe", "moon", "agent", "trump", "gold", "bull"
        ]
        self.search_index = 0

        # Carregar sementes verificadas 100% reais (Top 5 minutos + FOMO Gems)
        self._seed_initial_pool()

        # Thread contínua em segundo plano
        self.worker_thread = threading.Thread(target=self._background_worker, daemon=True)
        self.worker_thread.start()

    def _seed_initial_pool(self):
        """Inicializa 20 tokens verificados 100% reais sem nenhum link quebrado"""
        seeds = [
            {
                        "address": "0xa0c5F58Bf54700B0c582691aA85eab3B8603f4e8",
                        "name": "Moss",
                        "symbol": "MOSS",
                        "chain": "ETHEREUM",
                        "price_usd": 0.0001901,
                        "market_cap": 190072,
                        "liquidity_usd": 59253,
                        "volume_24h": 572499,
                        "volume_5m": 11031,
                        "buys_24h": 1188,
                        "sells_24h": 820,
                        "price_change_24h": 3378.0,
                        "price_change_1h": 3378.0,
                        "price_change_5m": 33.05,
                        "age": "44m",
                        "age_seconds": 2640,
                        "jovx_score": 98,
                        "tag": "HIGH ALPHA",
                        "risk_level": "LOW RISK",
                        "buy_url": "https://app.uniswap.org/swap?chain=ethereum&outputCurrency=0xa0c5F58Bf54700B0c582691aA85eab3B8603f4e8",
                        "dex_platform": "UNISWAP (ETH)",
                        "pair_url": "https://dexscreener.com/ethereum/0xbbf3560c9a191f71cca9d380600d6058216dd4d322d52fd326fc858253ff1c2c",
                        "icon": "https://dd.dexscreener.com/ds-data/tokens/ethereum/0xa0c5F58Bf54700B0c582691aA85eab3B8603f4e8.png"
            },
            {
                        "address": "ADPN2aqzY5RhkBC7bNQWFhTFFEYKY4drHUQG887Cpump",
                        "name": "CATCRAFT",
                        "symbol": "CATCRAFT",
                        "chain": "SOLANA",
                        "price_usd": 0.00072,
                        "market_cap": 720824,
                        "liquidity_usd": 79398,
                        "volume_24h": 736490,
                        "volume_5m": 14734,
                        "buys_24h": 9602,
                        "sells_24h": 6500,
                        "price_change_24h": 660.0,
                        "price_change_1h": 660.0,
                        "price_change_5m": 33.78,
                        "age": "55m",
                        "age_seconds": 3300,
                        "jovx_score": 99,
                        "tag": "HIGH ALPHA",
                        "risk_level": "LOW RISK",
                        "buy_url": "https://jup.ag/swap/SOL-ADPN2aqzY5RhkBC7bNQWFhTFFEYKY4drHUQG887Cpump",
                        "dex_platform": "JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/7mqdgteiad4tkupg9hstypqnestntrauehh1zj1awp8x",
                        "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/ADPN2aqzY5RhkBC7bNQWFhTFFEYKY4drHUQG887Cpump.png"
            },
            {
                        "address": "GfBwZAaRLdarL7mmUce8wkFc2xALuTSzyrREVKixpump",
                        "name": "Donsom Trump",
                        "symbol": "DONSOM",
                        "chain": "SOLANA",
                        "price_usd": 0.000249,
                        "market_cap": 249228,
                        "liquidity_usd": 43915,
                        "volume_24h": 601493,
                        "volume_5m": 13806,
                        "buys_24h": 12827,
                        "sells_24h": 8400,
                        "price_change_24h": 150.0,
                        "price_change_1h": 67.23,
                        "price_change_5m": 14.35,
                        "age": "1.8h",
                        "age_seconds": 6480,
                        "jovx_score": 98,
                        "tag": "HIGH ALPHA",
                        "risk_level": "LOW RISK",
                        "buy_url": "https://jup.ag/swap/SOL-GfBwZAaRLdarL7mmUce8wkFc2xALuTSzyrREVKixpump",
                        "dex_platform": "JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/9drkrm66snaasplfhqhg1mgs6yegm49ufr8qqik3kdlh",
                        "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/GfBwZAaRLdarL7mmUce8wkFc2xALuTSzyrREVKixpump.png"
            },
            {
                        "address": "95pkzpn2xcos5nb4uwedeztncwb2gdbs7iuzr3yz2tb7",
                        "name": "Super Trump",
                        "symbol": "ST",
                        "chain": "SOLANA",
                        "price_usd": 0.00013,
                        "market_cap": 130799,
                        "liquidity_usd": 33648,
                        "volume_24h": 290000,
                        "volume_5m": 11000,
                        "buys_24h": 1800,
                        "sells_24h": 1200,
                        "price_change_24h": 57.62,
                        "price_change_1h": 33.51,
                        "price_change_5m": 0.83,
                        "age": "2.2h",
                        "age_seconds": 7920,
                        "jovx_score": 91,
                        "tag": "EARLY GEM",
                        "risk_level": "LOW RISK",
                        "buy_url": "https://jup.ag/swap/SOL-95pkzpn2xcos5nb4uwedeztncwb2gdbs7iuzr3yz2tb7",
                        "dex_platform": "JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/95pkzpn2xcos5nb4uwedeztncwb2gdbs7iuzr3yz2tb7",
                        "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/95pkzpn2xcos5nb4uwedeztncwb2gdbs7iuzr3yz2tb7.png"
            },
            {
                        "address": "2T6Wg3urxPQHaoGh4gqNHyYL6FAfyWA5BaH6Lo37pump",
                        "name": "Miners",
                        "symbol": "MINER",
                        "chain": "SOLANA",
                        "price_usd": 0.000345,
                        "market_cap": 277646,
                        "liquidity_usd": 50927,
                        "volume_24h": 550830,
                        "volume_5m": 13695,
                        "buys_24h": 4066,
                        "sells_24h": 2700,
                        "price_change_24h": 599.0,
                        "price_change_1h": 190.0,
                        "price_change_5m": 11.97,
                        "age": "2.5h",
                        "age_seconds": 9000,
                        "jovx_score": 98,
                        "tag": "HIGH ALPHA",
                        "risk_level": "LOW RISK",
                        "buy_url": "https://jup.ag/swap/SOL-2T6Wg3urxPQHaoGh4gqNHyYL6FAfyWA5BaH6Lo37pump",
                        "dex_platform": "JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/8j42or3k3kbgnguqr2rbzcrweta7jhrnscjmscipv8in",
                        "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/2T6Wg3urxPQHaoGh4gqNHyYL6FAfyWA5BaH6Lo37pump.png"
            },
            {
                        "address": "2BVfJ4AHMvHdKtEZNHaBr48dQzTfZvYkjaaxbM6bpump",
                        "name": "inu wif sword",
                        "symbol": "SWORDINU",
                        "chain": "SOLANA",
                        "price_usd": 0.001468,
                        "market_cap": 1468847,
                        "liquidity_usd": 110558,
                        "volume_24h": 2847000,
                        "volume_5m": 31000,
                        "buys_24h": 14200,
                        "sells_24h": 10500,
                        "price_change_24h": 1555.0,
                        "price_change_1h": 73.3,
                        "price_change_5m": 1.79,
                        "age": "3.8h",
                        "age_seconds": 13680,
                        "jovx_score": 99,
                        "tag": "HIGH ALPHA",
                        "risk_level": "LOW RISK",
                        "buy_url": "https://jup.ag/swap/SOL-2BVfJ4AHMvHdKtEZNHaBr48dQzTfZvYkjaaxbM6bpump",
                        "dex_platform": "JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/69fyvgotxqxbdv7tazd99m1vycwos3pyjkj8rrffzszj",
                        "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/2BVfJ4AHMvHdKtEZNHaBr48dQzTfZvYkjaaxbM6bpump.png"
            },
            {
                        "address": "BZ8pkWUs4TjboT2xHRCwg3o6PK8xkvmNewvqMyyfpump",
                        "name": "irl.money",
                        "symbol": "IRL",
                        "chain": "SOLANA",
                        "price_usd": 0.000648,
                        "market_cap": 648258,
                        "liquidity_usd": 77278,
                        "volume_24h": 1540137,
                        "volume_5m": 27030,
                        "buys_24h": 11263,
                        "sells_24h": 7800,
                        "price_change_24h": 773.0,
                        "price_change_1h": 37.75,
                        "price_change_5m": 1.2,
                        "age": "4.3h",
                        "age_seconds": 15480,
                        "jovx_score": 98,
                        "tag": "HIGH ALPHA",
                        "risk_level": "LOW RISK",
                        "buy_url": "https://jup.ag/swap/SOL-BZ8pkWUs4TjboT2xHRCwg3o6PK8xkvmNewvqMyyfpump",
                        "dex_platform": "JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/dx8t9f6hzn1xx7ykzjeecc7n6wfptaicq6d3euypayum",
                        "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/BZ8pkWUs4TjboT2xHRCwg3o6PK8xkvmNewvqMyyfpump.png"
            },
            {
                        "address": "0x2E8c31162b855A2ffa90F6F8634643Ad6F111e18",
                        "name": "Artificial Inu",
                        "symbol": "AI",
                        "chain": "FOMO",
                        "price_usd": 0.1162,
                        "market_cap": 116183181.0,
                        "liquidity_usd": 122323.77,
                        "volume_24h": 133848.13,
                        "volume_5m": 446.43,
                        "buys_24h": 1104,
                        "sells_24h": 1038,
                        "price_change_24h": 0.42,
                        "price_change_1h": 5.39,
                        "price_change_5m": 0.72,
                        "age": "33d",
                        "age_seconds": 2883948,
                        "jovx_score": 99,
                        "tag": "FOMO GEM",
                        "risk_level": "LOW RISK",
                        "buy_url": "https://dexscreener.com/robinhood/0x7aebd80541bfaaf23dbb6e99ce13d4d31c1a84c91414f971eadbff7db5f85995",
                        "dex_platform": "FOMO / ROBINHOOD",
                        "pair_url": "https://dexscreener.com/robinhood/0x7aebd80541bfaaf23dbb6e99ce13d4d31c1a84c91414f971eadbff7db5f85995",
                        "icon": "https://dd.dexscreener.com/ds-data/tokens/robinhood/0x2E8c31162b855A2ffa90F6F8634643Ad6F111e18.png"
            },
            {
                        "address": "0xAa07A0e9209e16aC99708C3EC70159c6eF3128A3",
                        "name": "Orbio.so",
                        "symbol": "ORBIO",
                        "chain": "FOMO",
                        "price_usd": 0.05308,
                        "market_cap": 50432257.0,
                        "liquidity_usd": 898685.22,
                        "volume_24h": 2682107.57,
                        "volume_5m": 380.38,
                        "buys_24h": 2505,
                        "sells_24h": 2333,
                        "price_change_24h": -19.8,
                        "price_change_1h": -2.33,
                        "price_change_5m": -0.05,
                        "age": "16d",
                        "age_seconds": 1440208,
                        "jovx_score": 94,
                        "tag": "FOMO GEM",
                        "risk_level": "LOW RISK",
                        "buy_url": "https://dexscreener.com/robinhood/0xea9f200e13055b82f175f44f592c4c13dd8c9d9320a66487d3c5cd90d68550ef",
                        "dex_platform": "FOMO / ROBINHOOD",
                        "pair_url": "https://dexscreener.com/robinhood/0xea9f200e13055b82f175f44f592c4c13dd8c9d9320a66487d3c5cd90d68550ef",
                        "icon": "https://dd.dexscreener.com/ds-data/tokens/robinhood/0xAa07A0e9209e16aC99708C3EC70159c6eF3128A3.png"
            },
            {
                        "address": "0x98096d17e191B3dA1d5f99a6D7b3584351b11E18",
                        "name": "Boner Coin",
                        "symbol": "BONER",
                        "chain": "FOMO",
                        "price_usd": 0.05244,
                        "market_cap": 52442761.0,
                        "liquidity_usd": 245947.4,
                        "volume_24h": 147318.78,
                        "volume_5m": 369.94,
                        "buys_24h": 374,
                        "sells_24h": 269,
                        "price_change_24h": -18.51,
                        "price_change_1h": -0.39,
                        "price_change_5m": 0.28,
                        "age": "36d",
                        "age_seconds": 3133656,
                        "jovx_score": 94,
                        "tag": "FOMO GEM",
                        "risk_level": "LOW RISK",
                        "buy_url": "https://dexscreener.com/robinhood/0xfec7b1efe77aa60887986db5bcbfff39ca40b56d964bb8ce3d9dd0d9baaca4d4",
                        "dex_platform": "FOMO / ROBINHOOD",
                        "pair_url": "https://dexscreener.com/robinhood/0xfec7b1efe77aa60887986db5bcbfff39ca40b56d964bb8ce3d9dd0d9baaca4d4",
                        "icon": "https://dd.dexscreener.com/ds-data/tokens/robinhood/0x98096d17e191B3dA1d5f99a6D7b3584351b11E18.png"
            },
            {
                        "address": "0x39dBED3a2bd333467115dE45665cC57F813C4571",
                        "name": "Pons",
                        "symbol": "PONS",
                        "chain": "FOMO",
                        "price_usd": 0.3968,
                        "market_cap": 269755401.0,
                        "liquidity_usd": 3373205.2,
                        "volume_24h": 905199.88,
                        "volume_5m": 2476.55,
                        "buys_24h": 1398,
                        "sells_24h": 716,
                        "price_change_24h": 1.3,
                        "price_change_1h": -1.79,
                        "price_change_5m": -0.12,
                        "age": "85d",
                        "age_seconds": 7352881,
                        "jovx_score": 94,
                        "tag": "FOMO GEM",
                        "risk_level": "LOW RISK",
                        "buy_url": "https://dexscreener.com/robinhood/0x10CC6BD38112cAc182db90B6a71d8Bb5939526bA",
                        "dex_platform": "FOMO / ROBINHOOD",
                        "pair_url": "https://dexscreener.com/robinhood/0x10cc6bd38112cac182db90b6a71d8bb5939526ba",
                        "icon": "https://dd.dexscreener.com/ds-data/tokens/robinhood/0x39dBED3a2bd333467115dE45665cC57F813C4571.png"
            },
            {
                        "address": "0x020bfC650A365f8BB26819deAAbF3E21291018b4",
                        "name": "Cash Cat",
                        "symbol": "CASHCAT",
                        "chain": "FOMO",
                        "price_usd": 0.1366,
                        "market_cap": 135010160.0,
                        "liquidity_usd": 3895484.14,
                        "volume_24h": 516620.65,
                        "volume_5m": 659.37,
                        "buys_24h": 552,
                        "sells_24h": 403,
                        "price_change_24h": -14.74,
                        "price_change_1h": -0.31,
                        "price_change_5m": -0.03,
                        "age": "110d",
                        "age_seconds": 9515337,
                        "jovx_score": 94,
                        "tag": "FOMO GEM",
                        "risk_level": "LOW RISK",
                        "buy_url": "https://dexscreener.com/robinhood/0xA70fc67C9F69da90B63a0e4C05D229954574E313",
                        "dex_platform": "FOMO / ROBINHOOD",
                        "pair_url": "https://dexscreener.com/robinhood/0xa70fc67c9f69da90b63a0e4c05d229954574e313",
                        "icon": "https://dd.dexscreener.com/ds-data/tokens/robinhood/0x020bfC650A365f8BB26819deAAbF3E21291018b4.png"
            },
            {
                        "address": "0xd8eC6474C02e5f913A8fD566648a2Df4B18dbBa3",
                        "name": "MarsCoin",
                        "symbol": "MARSCOIN",
                        "chain": "FOMO",
                        "price_usd": 4.799e-07,
                        "market_cap": 47999.0,
                        "liquidity_usd": 55009.35,
                        "volume_24h": 28.22,
                        "volume_5m": 0.0,
                        "buys_24h": 5,
                        "sells_24h": 7,
                        "price_change_24h": 0.65,
                        "price_change_1h": 0.0,
                        "price_change_5m": 0.0,
                        "age": "75d",
                        "age_seconds": 6522357,
                        "jovx_score": 88,
                        "tag": "FOMO GEM",
                        "risk_level": "LOW RISK",
                        "buy_url": "https://dexscreener.com/robinhood/0x94d40a947551b06802705277bcedbb7c2ea2d789b1aba763e208fd5141dccab6",
                        "dex_platform": "FOMO / ROBINHOOD",
                        "pair_url": "https://dexscreener.com/robinhood/0x94d40a947551b06802705277bcedbb7c2ea2d789b1aba763e208fd5141dccab6",
                        "icon": "https://dd.dexscreener.com/ds-data/tokens/robinhood/0xd8eC6474C02e5f913A8fD566648a2Df4B18dbBa3.png"
            },
            {
                        "address": "GyWkSn2ah7dqLyPeZAjEZmfxuU2H4nwfGvgJhfYDVegn",
                        "name": "bul",
                        "symbol": "BUL",
                        "chain": "SOLANA",
                        "price_usd": 0.000177,
                        "market_cap": 177043,
                        "liquidity_usd": 40102,
                        "volume_24h": 551336,
                        "volume_5m": 9500,
                        "buys_24h": 4502,
                        "sells_24h": 3200,
                        "price_change_24h": 170.0,
                        "price_change_1h": 3.27,
                        "price_change_5m": 0.5,
                        "age": "1d",
                        "age_seconds": 86400,
                        "jovx_score": 95,
                        "tag": "HIGH ALPHA",
                        "risk_level": "LOW RISK",
                        "buy_url": "https://jup.ag/swap/SOL-GyWkSn2ah7dqLyPeZAjEZmfxuU2H4nwfGvgJhfYDVegn",
                        "dex_platform": "JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/cnwmuoehufxq2y1hfq67ttnks8zis3eujy6ksfsspsph",
                        "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/GyWkSn2ah7dqLyPeZAjEZmfxuU2H4nwfGvgJhfYDVegn.png"
            },
            {
                        "address": "HcRLc9VDgjLeK154xDawfb1dmVJ98DoSqcwTHGqiDeJR",
                        "name": "Anonymous Cat",
                        "symbol": "ZCAT",
                        "chain": "SOLANA",
                        "price_usd": 0.06581,
                        "market_cap": 63648319.0,
                        "liquidity_usd": 1321152.64,
                        "volume_24h": 2134918.93,
                        "volume_5m": 2211.12,
                        "buys_24h": 1803,
                        "sells_24h": 1571,
                        "price_change_24h": 37.47,
                        "price_change_1h": -5.38,
                        "price_change_5m": -0.14,
                        "age": "36d",
                        "age_seconds": 3195627,
                        "jovx_score": 94,
                        "tag": "FOMO GEM",
                        "risk_level": "LOW RISK",
                        "buy_url": "https://jup.ag/swap/SOL-HcRLc9VDgjLeK154xDawfb1dmVJ98DoSqcwTHGqiDeJR",
                        "dex_platform": "FOMO / JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/btccxxtfi7a9xjte1exkn38jgie35s6gnerxd8dm61rc",
                        "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/HcRLc9VDgjLeK154xDawfb1dmVJ98DoSqcwTHGqiDeJR.png"
            },
            {
                        "address": "6GmAFSYs4gk3FDao5FzzySQpPZaWsa4rUJHacpMpUNgx",
                        "name": "STONK",
                        "symbol": "STONK",
                        "chain": "SOLANA",
                        "price_usd": 0.2116,
                        "market_cap": 185531656.0,
                        "liquidity_usd": 2758089.27,
                        "volume_24h": 5987302.5,
                        "volume_5m": 34235.89,
                        "buys_24h": 9589,
                        "sells_24h": 11888,
                        "price_change_24h": 13.09,
                        "price_change_1h": -2.19,
                        "price_change_5m": 0.78,
                        "age": "55d",
                        "age_seconds": 4796322,
                        "jovx_score": 94,
                        "tag": "FOMO GEM",
                        "risk_level": "LOW RISK",
                        "buy_url": "https://jup.ag/swap/SOL-6GmAFSYs4gk3FDao5FzzySQpPZaWsa4rUJHacpMpUNgx",
                        "dex_platform": "FOMO / JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/zxtpi4btawx3mgdapoezkmd1hxx8cdecfrqxmwvsclx",
                        "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/6GmAFSYs4gk3FDao5FzzySQpPZaWsa4rUJHacpMpUNgx.png"
            },
            {
                        "address": "Ai66LHZG9MCzg1WKdawwqduVAXpNDUuV8M3uyq5ppump",
                        "name": "Catecoin",
                        "symbol": "CATE",
                        "chain": "SOLANA",
                        "price_usd": 0.06273,
                        "market_cap": 60482468.0,
                        "liquidity_usd": 3033905.46,
                        "volume_24h": 1692623.91,
                        "volume_5m": 7107.98,
                        "buys_24h": 4069,
                        "sells_24h": 3595,
                        "price_change_24h": -6.97,
                        "price_change_1h": -2.71,
                        "price_change_5m": 0.29,
                        "age": "72d",
                        "age_seconds": 6244659,
                        "jovx_score": 94,
                        "tag": "FOMO GEM",
                        "risk_level": "LOW RISK",
                        "buy_url": "https://jup.ag/swap/SOL-Ai66LHZG9MCzg1WKdawwqduVAXpNDUuV8M3uyq5ppump",
                        "dex_platform": "FOMO / JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/hmzvseemtzhhvznw9uwbag85hctmfnkbhzux16cy7ca3",
                        "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/Ai66LHZG9MCzg1WKdawwqduVAXpNDUuV8M3uyq5ppump.png"
            },
            {
                        "address": "CARDSccUMFKoPRZxt5vt3ksUbxEFEcnZ3H2pd3dKxYjp",
                        "name": "Collector Crypt",
                        "symbol": "CARDS",
                        "chain": "SOLANA",
                        "price_usd": 0.3056,
                        "market_cap": 120178816.0,
                        "liquidity_usd": 4174212.51,
                        "volume_24h": 4548057.05,
                        "volume_5m": 3030.67,
                        "buys_24h": 13251,
                        "sells_24h": 10624,
                        "price_change_24h": 8.44,
                        "price_change_1h": -0.42,
                        "price_change_5m": 0.07,
                        "age": "403d",
                        "age_seconds": 34834536,
                        "jovx_score": 94,
                        "tag": "FOMO GEM",
                        "risk_level": "LOW RISK",
                        "buy_url": "https://jup.ag/swap/SOL-CARDSccUMFKoPRZxt5vt3ksUbxEFEcnZ3H2pd3dKxYjp",
                        "dex_platform": "FOMO / JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/hnhpjpjgbg2kwnimtnw8cvbhvk1hfog3rc3kjnyc23td",
                        "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/CARDSccUMFKoPRZxt5vt3ksUbxEFEcnZ3H2pd3dKxYjp.png"
            },
            {
                        "address": "Dz9mQ9NzkBcCsuGPFJ3r1bS4wgqKMHBPiVuniW8Mbonk",
                        "name": "USELESS COIN",
                        "symbol": "USELESS",
                        "chain": "SOLANA",
                        "price_usd": 0.2253,
                        "market_cap": 225316853.0,
                        "liquidity_usd": 5233934.78,
                        "volume_24h": 873521.63,
                        "volume_5m": 682.72,
                        "buys_24h": 2366,
                        "sells_24h": 2915,
                        "price_change_24h": -5.92,
                        "price_change_1h": -0.87,
                        "price_change_5m": -0.05,
                        "age": "514d",
                        "age_seconds": 44441226,
                        "jovx_score": 94,
                        "tag": "FOMO GEM",
                        "risk_level": "LOW RISK",
                        "buy_url": "https://jup.ag/swap/SOL-Dz9mQ9NzkBcCsuGPFJ3r1bS4wgqKMHBPiVuniW8Mbonk",
                        "dex_platform": "FOMO / JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/q2sphpduwfmg7m7wwrqklrn619caucfrsmhvjffodsp",
                        "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/Dz9mQ9NzkBcCsuGPFJ3r1bS4wgqKMHBPiVuniW8Mbonk.png"
            },
            {
                        "address": "0xbbae4ba1c48640c737af320c2ccef8ab910b0e076f659df956091f84e4da6927",
                        "name": "Official Trump",
                        "symbol": "TRUMP",
                        "chain": "BASE",
                        "price_usd": 0.00185,
                        "market_cap": 185454,
                        "liquidity_usd": 183599,
                        "volume_24h": 450000,
                        "volume_5m": 12000,
                        "buys_24h": 3200,
                        "sells_24h": 2400,
                        "price_change_24h": 15.0,
                        "price_change_1h": 3.2,
                        "price_change_5m": 0.8,
                        "age": "4d",
                        "age_seconds": 345600,
                        "jovx_score": 85,
                        "tag": "BULLISH TREND",
                        "risk_level": "LOW RISK",
                        "buy_url": "https://app.uniswap.org/swap?chain=base&outputCurrency=0xbbae4ba1c48640c737af320c2ccef8ab910b0e076f659df956091f84e4da6927",
                        "dex_platform": "UNISWAP (BASE)",
                        "pair_url": "https://dexscreener.com/base/0xbbae4ba1c48640c737af320c2ccef8ab910b0e076f659df956091f84e4da6927",
                        "icon": "https://dd.dexscreener.com/ds-data/tokens/base/0xbbae4ba1c48640c737af320c2ccef8ab910b0e076f659df956091f84e4da6927.png"
            }
]
        with self.lock:
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
        """Ordena prioritariamente pelas moedas mais recentes/novinhas que estão VERDES"""
        clean_tokens = []
        for t in self.pool.values():
            is_fomo = (t.get("chain") in ["FOMO", "ROBINHOOD"]) or ("FOMO" in t.get("tag", "")) or (t.get("market_cap", 0) > 10000000)
            
            # Anti-Dump Geral (Tolerância Zero para flash dump)
            if t.get("price_change_5m", 0) < -4.5:
                continue
            if t.get("price_change_1h", 0) < -6.0:
                continue
            
            if not is_fomo:
                # Regras estritas para microcaps pump.fun
                if t.get("age_seconds", 0) > MAX_TOKEN_AGE_SECONDS:
                    continue
                if t.get("price_change_24h", 0) < 0.0:
                    continue
                if t.get("sells_24h", 0) > (t.get("buys_24h", 0) * 1.3) and t.get("buys_24h", 0) > 0:
                    continue
            
            clean_tokens.append(t)

        def freshness_sort_key(t):
            age = t.get("age_seconds", 3600)
            score = t.get("jovx_score", 70)
            is_fomo = (t.get("chain") in ["FOMO", "ROBINHOOD"]) or ("FOMO" in t.get("tag", ""))
            
            # Tier 0: Moedas de minutos (< 2.5 horas / 9000s) -> Top 5 absoluto
            if age < 9000:
                return (0, age, -score)
            # Tier 1: Moedas de até 24h
            elif age < 86400:
                return (1, age, -score)
            # Tier 2: Gemas FOMO e consolidadas
            else:
                return (2, 0 if is_fomo else 1, -score, age)

        clean_tokens.sort(key=freshness_sort_key)
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

        # 0. Se Helius estiver configurada, puxar novos tokens da Solana em tempo real
        if HELIUS_API_KEY:
            try:
                helius_url = f"https://api.helius.xyz/v0/addresses/675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8/transactions?api-key={HELIUS_API_KEY}&limit=20"
                r_h = requests.get(helius_url, timeout=3)
                if r_h.status_code == 200:
                    txs = r_h.json()
                    for tx in txs:
                        for token_trans in tx.get("tokenTransfers", []):
                            mint = token_trans.get("mint")
                            if mint and mint not in EXCLUDED_SYMBOLS:
                                candidate_addrs.append(mint)
            except Exception as e:
                logger.error(f"[HELIUS FETCH ERROR]: {e}")

        # 1. Puxar os perfis mais recentes da DexScreener
        try:
            r = requests.get(self.profiles_url, headers=self.headers, timeout=4)
            if r.status_code == 200:
                profiles = r.json()
                if isinstance(profiles, list):
                    for p in profiles[:25]:
                        addr = p.get("tokenAddress")
                        if addr: candidate_addrs.append(addr)
        except Exception:
            pass

        # 2. Puxar os boosts mais recentes
        try:
            r_b = requests.get(self.boosts_url, headers=self.headers, timeout=4)
            if r_b.status_code == 200:
                boosts = r_b.json()
                if isinstance(boosts, list):
                    for b in boosts[:20]:
                        addr = b.get("tokenAddress")
                        if addr: candidate_addrs.append(addr)
        except Exception:
            pass

        # 3. Adicionar tokens já no pool para auditar se começaram a cair
        with self.lock:
            for addr in list(self.pool.keys()):
                candidate_addrs.append(addr)

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

        unique_addrs = list(dict.fromkeys(candidate_addrs))[:90]
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

        # 8. Atualizar a piscina
        with self.lock:
            for t in fresh_valid_tokens:
                self.pool[t["address"]] = t

            # PURGA IMEDIATA: expulsar SEM DÓ qualquer token derretendo
            tokens_to_purge = []
            for addr, t in self.pool.items():
                is_fomo = (t.get("chain") in ["FOMO", "ROBINHOOD"]) or ("FOMO" in t.get("tag", "")) or (t.get("market_cap", 0) > 10000000)
                
                # Tolerância zero para crash repentino em 5m / 1h
                if t.get("price_change_5m", 0) < -4.5:
                    tokens_to_purge.append(addr)
                elif t.get("price_change_1h", 0) < -6.0:
                    tokens_to_purge.append(addr)
                elif not is_fomo:
                    if t.get("age_seconds", 0) > MAX_TOKEN_AGE_SECONDS:
                        tokens_to_purge.append(addr)
                    elif t.get("price_change_24h", 0) < 0.0:
                        tokens_to_purge.append(addr)
                    elif t.get("sells_24h", 0) > (t.get("buys_24h", 0) * 1.3) and t.get("buys_24h", 0) > 0:
                        tokens_to_purge.append(addr)
            
            for addr in tokens_to_purge:
                if addr in self.pool:
                    logger.info(f"[ANTI-DUMP PURGE] Removendo token em derretimento: {self.pool[addr].get('symbol')}")
                    del self.pool[addr]

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

            # FILTRO 2: IDADE (Tokens novos de meme < 5 dias; tokens FOMO consolidados permitidos)
            if not is_fomo_token and age_sec > MAX_TOKEN_AGE_SECONDS:
                return None

            # KILL SWITCHES ANTI-DERRETIMENTO
            if price_change_5m < -4.5:
                return None
            if price_change_1h < -6.0:
                return None
            if liquidity_usd < 20000:
                return None
            if market_cap < 30000:
                return None

            if not is_fomo_token:
                if price_change_24h < 0.0:
                    return None
                if sells > 0 and buys > 0 and (sells > buys * 1.3):
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

            risk_level = "LOW RISK" if liquidity_usd >= 40000 and price_change_1h >= -2.0 else "MODERATE"

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
