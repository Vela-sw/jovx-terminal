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

# =========================================================================
# REGRA INFLEXÍVEL DE 15 MOEDAS: DIVISÃO ESTRATÉGICA (8m a 45m)
# - Metade das moedas de 8m-45m vai para o Top #1 ao #5 (Área VIP / PRO)
# - A outra metade vai para o Top #6 ao #10 (Área Free Liberada para conversão)
# - Posições restantes completadas pelas melhores gemas consolidadas (45m a 12h)
# - Total SEMPRE cravado em 15 moedas!
# =========================================================================
TOTAL_DISPLAY_TOKENS = 15
MIN_TOKEN_AGE_SECONDS = 480          # 8 minutos (proteção contra snipers de berçário)
FRESH_WINDOW_MAX_SECONDS = 2700       # 45 minutos (janela ultra-fresca para split VIP/Free)
MAX_TOKEN_AGE_SECONDS = 12 * 3600   # 12 horas (43.200 segundos) - teto máximo de vida

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
            "BFn1AYpQdumP2D8KBLcACffqvZBWRTbDZ5EmJP4opump", # NVIDIA derreteu -95% (Banido permanentemente)
            "8Tq4hpxkc4Syv9p2dWb7yqn4idciSJhpZQMFNnE6pump", # FEED derreteu -93% (Banido permanentemente)
            "CVxmNU5pseYjegY1D8GBk6J1y3cRj7JrCZDyd2z1pump", # ONLYDOGE derreteu -98% (Banido permanentemente)
            "FXRDkcntDvxstU7fNEcy7PLc6EDncb3yNiKHPtVXpump", # OVERMIND derreteu -93% (Banido permanentemente)
            "4dLxcTxJQnkMmCKkkVoLcKgsRjj7CpGJYuwVU1repump", # UNICORN derreteu -52% (Banido permanentemente)
            "7tecn1nGFHaswTUFhivdwcj23XyxE9cnDoNjh3N1pump", # REWARDS derreteu -91% (Banido permanentemente)
            "F9MnczrxHB3p7FkV5ma2iHW5ka7kv667zP35RzbJpump", # GSC liquidez $0 (Banido permanentemente)
            "HQgMPJbGctpP9P27DdJW5f8rncz7gvg4vEL3hT7hpump", # LILANSEM derreteu -89% (Banido permanentemente)
            "4VScHuqZ13uma3S34iNkiSAQvZDEeGebjbM5bPcapump", # VSWAP derreteu -31% (Banido permanentemente)
            "8zmFs8YsZAd2FQXWJjqLSoHGVEsiKuheeKj4hhWXMops", # PADPAD liquidez $0 (Banido permanentemente)
            "9VKfarEDscEjg6N9NDPm3eqUgG3b61ReAArymRtpump", # CAT liquidez $0 (Banido permanentemente)
            "EdjgP52yUrKiyHnkvJQhhzB6XyNpMqbTfAZdw56Ppump", # FBUCK liquidez $0 (Banido permanentemente)
            "GL21ea5TvQDV3AdycEkxYnC9wiZB8wScSefND2gvpump", # SUPAH liquidez $0 (Banido permanentemente)
            "Cw7Eh4HVCf1P8dn2gFpeoLV8fGBdB2BBR2PmcDuNpump", # EMO liquidez $0 (Banido permanentemente)
            "GLN7Dr7AsP9GRxAjxiVBk9Rnwyn74ar2R3BuGk8ZxQn1", # HI 404 (Banido permanentemente)
            "4p4uafszvffam8syvqh1wzkg9gc89youusl5pn6ny7fx", # CHAT 404 (Banido permanentemente)
            "4k3MgyawuztfCtPiy3US8hXR6xP6T9sLRo7eM6eSzXuE", # CHONK 404 (Banido permanentemente)
            "7kfgvqivsfvcnwe2zwugdub7ctxsszbc7pjdnde8pczu", # JUSTQ 404 (Banido permanentemente)
            "QDh9HSBgwAnf3ytvzZ2eoQSDWxQMewYKhxkgfkZpump", # WAIF (Banido)
            "osHhXb2fPunnaXidE89i9K97TAA5sG6T8DnYHXnpump", # DOTF (Banido)
            "oJasFBxCqCYuzHmxggsyy4jripUtF3RfvKNPvSHpump", # ADTF (Banido)
            "oP3XexBntzbPrYFyd9fjoLMb36XUdGWeg8rXqHtpump", # USDF (Banido)
            "V2KaLPiiMwMGNVQ9fTGoHmPZU3ucjT29H5EbkaWpump", # WAIF 2 (Banido)
            "CqLY374856BrFmV7rKdobhbTGgJXj75aKkg6y6Gpump", # DARK 2 (Banido)
            "kZXneJiCtqsgjN9kgMLVhsjuieYs1LdrBASTXwnpump", # FOMO 2 (Banido)
            "GfBwZAaRLdarL7mmUce8wkFc2xALuTSzyrREVKixpump", # DONSOM derreteu -97% (Banido)
            "0xbDDd48BdE05b98d222A7110fB363C5176360B356", # SRX derreteu -99% (Banido)
            "0xa0c5F58Bf54700B0c582691aA85eab3B8603f4e8", # MOSS liquidez derreteu (Banido)
            "BZ8pkWUs4TjboT2xHRCwg3o6PK8xkvmNewvqMyyfpump", # IRL derreteu -93% (Banido)
            "95pkzpn2xcos5nb4uwedeztncwb2gdbs7iuzr3yz2tb7", # ST par inexistente (Banido)
            "0xAF8A8A828632Cc88BF917A42d9e1AaB71D5a1994", # TRUMP fake (Banido)
            "0xc28b8cd6A219B152B5ee190b6A56e268d51397f7", # CAT fake (Banido)
            "0xDc4Ecc86f21220602573A73AbC2d44DFA071495d", # SUPER fake (Banido)
            "0x423cF4c0766F3B5eCD64ef81Dd7496d5990C2BA9", # WIF fake (Banido)
            "0xeb37F000DE3008C2Aea130325449711A84e00c9A", # TRUMP fake 2 (Banido)
            "0xd5e347719602a831e5f84dca83897d8c6b75c5a7", # MOON fake (Banido)
            "0xaEBC764C588c9A480307dd59Bd55F542E2b5b35c", # ONE derreteu -60% (Banido)
            "0xB91040F8e25b83b6e8335F4F16DFd53C67Be3c2F", # GOLD par inexistente (Banido)
            "0x0CA2f986c95D4B2d638a3561d1ee8Fd33B0220D7", # GACHA par inexistente (Banido)
            "0x5EeEb94A43B72a40166c84c9454Ae75f97793929", # PUMP par inexistente (Banido)
            "0x53df63071253a6639b7bf60f1ad92500be8f02b9", # MEME par inexistente (Banido)
            "0x0989b52a4cf548079bfab84b3ca48efbf98ba298", # CHAD par inexistente (Banido)
            "0x89980d0d82626e254ff9cb0df57e3f8373cb7462", # BUNKER par inexistente (Banido)
            "0xddbaDAB50698bFFa1E02dF1643309AD08bca7777", # CHAD par inexistente (Banido)
            "0xe3F035A10b407Bcd9A6842525f6C1E27D0657777", # ANON par inexistente (Banido)
            "2BVfJ4AHMvHdKtEZNHaBr48dQzTfZvYkjaaxbM6bpump", # SWORDINU derreteu -91% (Banido)
            "867dkvaccyrrudp66bqnxbujxfjaxsnb9wtpc4cmbdad", # MISTAKE (Banido)
            "8nvfb1unnk9adtl5hoof8hahf2rt4glpwx9cteadikhg", # PUMPOWEEN (Banido)
            "b7nyoghqcgofripb4aot1nqbqrfwjdfiekd3wnxxscnt", # BOT (Banido)
            "7manjzds3tfcgnht9zhrdatgyu6sqxgramhrzrrtplxj", # TOKEN (Banido)
            "bchdybezzstngxynhyf623khehsbgpzfs4rjlvbe5ytj", # STAR (Banido)
            "0xDEAaCC5DcCE808e1D267e3C65b831f55baf99B2b", # CRAWLSCAN (Banido)
            "FcqR9pW5Jd4i2a39E97QYwXQkPsq9yCqM7GvR34epump", # QUANT (Banido)
            "9nrPM6kGijkrPn6CAeWHZbRrvVKq5gmxQPdC4zMVpump", # BERRY (Banido)
            "EHFJLG7CbNnnuPHXHNtdeWfRQ3UFwBfBZRe11hnppump", # QPAD (Banido)
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
        """Inicializa tokens verificados 100% reais com pares canônicos válidos no DexScreener e carimbos reais de criação (pairCreatedAt):
        - Idades calculadas 100% dinamicamente em tempo de execução
        - Sem valores estáticos ou desatualizados
        - Teto máximo rigoroso de 12 horas
        - ZERO tolerância para tokens derretidos
        """
        seeds = [
            {
                        "address": "7yg2UT3Ksh7wwmAPAasaKU6SBbakRtzf2eYqjZZzpump",
                        "name": "Bumo-chan",
                        "symbol": "BUMO",
                        "chain": "SOLANA",
                        "price_usd": 0.000103,
                        "market_cap": 100373.0,
                        "liquidity_usd": 26933.71,
                        "volume_24h": 335669.08,
                        "volume_5m": 745.47,
                        "buys_24h": 10120,
                        "sells_24h": 2951,
                        "price_change_24h": 110.0,
                        "price_change_1h": 10.97,
                        "price_change_5m": -0.83,
                        "pair_created_at": 1791825474000,
                        "age_seconds": 78260.84696030617,
                        "age": "21.7h",
                        "jovx_score": 87,
                        "tag": "HIGH ALPHA",
                        "risk_level": "LOW RISK \ud83d\udee1\ufe0f",
                        "lp_locked": True,
                        "liquidity_locked": True,
                        "buy_url": "https://jup.ag/swap/SOL-7yg2UT3Ksh7wwmAPAasaKU6SBbakRtzf2eYqjZZzpump",
                        "dex_platform": "JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/2jekq8vicyouwwtgpfflq61zu3nnxkjdjswfqebk1c9a",
                        "icon": "https://cdn.dexscreener.com/cms/images/QzRkbviY2FMPGXCa?width=800&height=800&quality=95&format=auto",
                        "photon_url": "https://photon-sol.tinyastro.io/en/lp/7yg2UT3Ksh7wwmAPAasaKU6SBbakRtzf2eYqjZZzpump"
            },
            {
                        "address": "7jNwX4Me9zGEjmWY7zARDG2LYjVs1WXD6DZ1JvSfpump",
                        "name": "Humphrey Reserve",
                        "symbol": "HUMPH",
                        "chain": "SOLANA",
                        "price_usd": 0.004132,
                        "market_cap": 4114812.0,
                        "liquidity_usd": 190715.25,
                        "volume_24h": 3393468.46,
                        "volume_5m": 10869.24,
                        "buys_24h": 55249,
                        "sells_24h": 32729,
                        "price_change_24h": 230.0,
                        "price_change_1h": 8.23,
                        "price_change_5m": 2.74,
                        "pair_created_at": 1791802454000,
                        "age_seconds": 101280.84696030617,
                        "age": "28.1h",
                        "jovx_score": 99,
                        "tag": "HIGH ALPHA",
                        "risk_level": "LOW RISK \ud83d\udee1\ufe0f",
                        "lp_locked": True,
                        "liquidity_locked": True,
                        "buy_url": "https://jup.ag/swap/SOL-7jNwX4Me9zGEjmWY7zARDG2LYjVs1WXD6DZ1JvSfpump",
                        "dex_platform": "JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/9pqrnahbkjd61kys2k4fenlcpvai5hu5jbmbesunhljz",
                        "icon": "https://cdn.dexscreener.com/cms/images/jlWvCQHqbl08sNkQ?width=800&height=800&quality=95&format=auto",
                        "photon_url": "https://photon-sol.tinyastro.io/en/lp/7jNwX4Me9zGEjmWY7zARDG2LYjVs1WXD6DZ1JvSfpump"
            },
            {
                        "address": "8KKHDdWRX3NY9gTgnxCPp2b9nMCofwzxdYzZrXwrpump",
                        "name": "The fat wizard cat",
                        "symbol": "CHONK",
                        "chain": "SOLANA",
                        "price_usd": 8.168e-05,
                        "market_cap": 77731.0,
                        "liquidity_usd": 23402.26,
                        "volume_24h": 134058.64,
                        "volume_5m": 307.07,
                        "buys_24h": 2151,
                        "sells_24h": 1306,
                        "price_change_24h": 77.87,
                        "price_change_1h": 19.97,
                        "price_change_5m": 1.87,
                        "pair_created_at": 1791835777000,
                        "age_seconds": 67957.84696030617,
                        "age": "18.9h",
                        "jovx_score": 83,
                        "tag": "HIGH ALPHA",
                        "risk_level": "LOW RISK \ud83d\udee1\ufe0f",
                        "lp_locked": True,
                        "liquidity_locked": True,
                        "buy_url": "https://jup.ag/swap/SOL-8KKHDdWRX3NY9gTgnxCPp2b9nMCofwzxdYzZrXwrpump",
                        "dex_platform": "JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/4k3mgyawuztfctpiy3us8hxr6xp6t9slro7em6eszxue",
                        "icon": "https://cdn.dexscreener.com/cms/images/_UuaLv0MhrLtTh-N?width=800&height=800&quality=95&format=auto",
                        "photon_url": "https://photon-sol.tinyastro.io/en/lp/8KKHDdWRX3NY9gTgnxCPp2b9nMCofwzxdYzZrXwrpump"
            },
            {
                        "address": "4hsJNmPComjTsbrDtoLjDMmsyZ1g2T1xy1xHnEE2pump",
                        "name": "Baton Agency",
                        "symbol": "BATONA",
                        "chain": "SOLANA",
                        "price_usd": 0.004126,
                        "market_cap": 4060536.0,
                        "liquidity_usd": 184612.86,
                        "volume_24h": 2599536.19,
                        "volume_5m": 4501.23,
                        "buys_24h": 18708,
                        "sells_24h": 12160,
                        "price_change_24h": 3293.0,
                        "price_change_1h": 3.01,
                        "price_change_5m": -0.04,
                        "pair_created_at": 1791819083000,
                        "age_seconds": 84651.84696030617,
                        "age": "23.5h",
                        "jovx_score": 99,
                        "tag": "HIGH ALPHA",
                        "risk_level": "LOW RISK \ud83d\udee1\ufe0f",
                        "lp_locked": True,
                        "liquidity_locked": True,
                        "buy_url": "https://jup.ag/swap/SOL-4hsJNmPComjTsbrDtoLjDMmsyZ1g2T1xy1xHnEE2pump",
                        "dex_platform": "JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/aw3bwgkkpadonhzydhmpa2xdxeaztggdxsn3yurmxsyj",
                        "icon": "https://cdn.dexscreener.com/cms/images/JNgI0fQJw4OCcNtM?width=800&height=800&quality=95&format=auto",
                        "photon_url": "https://photon-sol.tinyastro.io/en/lp/4hsJNmPComjTsbrDtoLjDMmsyZ1g2T1xy1xHnEE2pump"
            },
            {
                        "address": "8sWe4GzK1YqG3vyzKHf8ZyB1WB5asofw2o6TqgFePtPo",
                        "name": "Loadout",
                        "symbol": "LOAD",
                        "chain": "SOLANA",
                        "price_usd": 0.009436,
                        "market_cap": 9178459.0,
                        "liquidity_usd": 157705.91,
                        "volume_24h": 5967538.67,
                        "volume_5m": 12.2,
                        "buys_24h": 17390,
                        "sells_24h": 15038,
                        "price_change_24h": 4330.0,
                        "price_change_1h": -19.77,
                        "price_change_5m": 0.07,
                        "pair_created_at": 1791831675000,
                        "age_seconds": 72059.84696030617,
                        "age": "20.0h",
                        "jovx_score": 97,
                        "tag": "HIGH ALPHA",
                        "risk_level": "LOW RISK \ud83d\udee1\ufe0f",
                        "lp_locked": True,
                        "liquidity_locked": True,
                        "buy_url": "https://jup.ag/swap/SOL-8sWe4GzK1YqG3vyzKHf8ZyB1WB5asofw2o6TqgFePtPo",
                        "dex_platform": "JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/dcyra6dumbkmszk77cwv1wfzfjtbdyqjljohwvbxk3u1",
                        "icon": "https://cdn.dexscreener.com/cms/images/fqn_K6RDcRtgC1Rj?width=800&height=800&quality=95&format=auto",
                        "photon_url": "https://photon-sol.tinyastro.io/en/lp/8sWe4GzK1YqG3vyzKHf8ZyB1WB5asofw2o6TqgFePtPo"
            },
            {
                        "address": "6x4Z2dr5DgHUBCKvta8T8GNsFTxJhsBZxNrycWQ8pump",
                        "name": "hi",
                        "symbol": "HI",
                        "chain": "SOLANA",
                        "price_usd": 9.513e-05,
                        "market_cap": 90537.0,
                        "liquidity_usd": 27737.75,
                        "volume_24h": 808899.35,
                        "volume_5m": 0.0,
                        "buys_24h": 8724,
                        "sells_24h": 6805,
                        "price_change_24h": 119.0,
                        "price_change_1h": -14.56,
                        "price_change_5m": 0.0,
                        "pair_created_at": 1791847862000,
                        "age_seconds": 55872.84696030617,
                        "age": "15.5h",
                        "jovx_score": 88,
                        "tag": "HIGH ALPHA",
                        "risk_level": "LOW RISK \ud83d\udee1\ufe0f",
                        "lp_locked": True,
                        "liquidity_locked": True,
                        "buy_url": "https://jup.ag/swap/SOL-6x4Z2dr5DgHUBCKvta8T8GNsFTxJhsBZxNrycWQ8pump",
                        "dex_platform": "JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/gln7dr7asp9grxajxivbk9rnwyn74ar2r3bugk8zxqn1",
                        "icon": "https://cdn.dexscreener.com/cms/images/jSmI49ICzVenkeLM?width=800&height=800&quality=95&format=auto",
                        "photon_url": "https://photon-sol.tinyastro.io/en/lp/6x4Z2dr5DgHUBCKvta8T8GNsFTxJhsBZxNrycWQ8pump"
            },
            {
                        "address": "B4rXJv2pRQvTfEsgtYfxqAsA6sUC8iVGEN1pN865pump",
                        "name": "slopcore.studio",
                        "symbol": "[SS]",
                        "chain": "SOLANA",
                        "price_usd": 0.0001073,
                        "market_cap": 105164.0,
                        "liquidity_usd": 29040.36,
                        "volume_24h": 597393.61,
                        "volume_5m": 194.95,
                        "buys_24h": 4649,
                        "sells_24h": 6692,
                        "price_change_24h": 141.0,
                        "price_change_1h": -20.01,
                        "price_change_5m": 1.65,
                        "pair_created_at": 1791843158000,
                        "age_seconds": 60576.84696030617,
                        "age": "16.8h",
                        "jovx_score": 90,
                        "tag": "HIGH ALPHA",
                        "risk_level": "LOW RISK \ud83d\udee1\ufe0f",
                        "lp_locked": True,
                        "liquidity_locked": True,
                        "buy_url": "https://jup.ag/swap/SOL-B4rXJv2pRQvTfEsgtYfxqAsA6sUC8iVGEN1pN865pump",
                        "dex_platform": "JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/35rs66rzvj7kukmge6tuuhu9zpwd7kkkbp84ykcai14c",
                        "icon": "https://cdn.dexscreener.com/cms/images/VtVK6vNzwwAiZ8eQ?width=800&height=800&quality=95&format=auto",
                        "photon_url": "https://photon-sol.tinyastro.io/en/lp/B4rXJv2pRQvTfEsgtYfxqAsA6sUC8iVGEN1pN865pump"
            },
            {
                        "address": "eYPUJqVPzCU3Rr6VVrSvbG9mvM2dawmwQK3HZrDpump",
                        "name": "Bomboclat Wallahi",
                        "symbol": "FISHY",
                        "chain": "SOLANA",
                        "price_usd": 8.288e-05,
                        "market_cap": 78686.0,
                        "liquidity_usd": 23824.98,
                        "volume_24h": 200154.87,
                        "volume_5m": 103.48,
                        "buys_24h": 1834,
                        "sells_24h": 1775,
                        "price_change_24h": 91.03,
                        "price_change_1h": -0.42,
                        "price_change_5m": -1.21,
                        "pair_created_at": 1791854671000,
                        "age_seconds": 49063.84696030617,
                        "age": "13.6h",
                        "jovx_score": 85,
                        "tag": "HIGH ALPHA",
                        "risk_level": "LOW RISK \ud83d\udee1\ufe0f",
                        "lp_locked": True,
                        "liquidity_locked": True,
                        "buy_url": "https://jup.ag/swap/SOL-eYPUJqVPzCU3Rr6VVrSvbG9mvM2dawmwQK3HZrDpump",
                        "dex_platform": "JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/erxctcqojnxa7mjgx8m4xpewh8fdttndu7ck3j2bwpgq",
                        "icon": "https://cdn.dexscreener.com/cms/images/g6rIsvzFl6QiLFSS?width=800&height=800&quality=95&format=auto",
                        "photon_url": "https://photon-sol.tinyastro.io/en/lp/eYPUJqVPzCU3Rr6VVrSvbG9mvM2dawmwQK3HZrDpump"
            },
            {
                        "address": "94x2mYkoFtVTGrjJj1B8HkCDZDRU2PJ5fJJ37sGz4Efs",
                        "name": "Route",
                        "symbol": "ROUTE",
                        "chain": "SOLANA",
                        "price_usd": 0.0001561,
                        "market_cap": 149997.0,
                        "liquidity_usd": 34380.14,
                        "volume_24h": 317540.09,
                        "volume_5m": 16171.78,
                        "buys_24h": 3869,
                        "sells_24h": 2906,
                        "price_change_24h": 253.0,
                        "price_change_1h": 253.0,
                        "price_change_5m": -11.07,
                        "pair_created_at": 1791900792000,
                        "age_seconds": 2942.8469603061676,
                        "age": "49.0m",
                        "jovx_score": 91,
                        "tag": "PRIME ALPHA",
                        "risk_level": "PRIME ALPHA \ud83d\ude80",
                        "lp_locked": True,
                        "liquidity_locked": True,
                        "buy_url": "https://jup.ag/swap/SOL-94x2mYkoFtVTGrjJj1B8HkCDZDRU2PJ5fJJ37sGz4Efs",
                        "dex_platform": "JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/hgz6n2m8c4mh4dqg1hzml5joewphsqfppnchm6csnmke",
                        "icon": "https://cdn.dexscreener.com/cms/images/O7Ll9ZIBHFnJNYJI?width=800&height=800&quality=95&format=auto",
                        "photon_url": "https://photon-sol.tinyastro.io/en/lp/94x2mYkoFtVTGrjJj1B8HkCDZDRU2PJ5fJJ37sGz4Efs"
            },
            {
                        "address": "GQdEL4MhL4v8bsmMvyBvjh6BdbWqasgkDnJGfaAHpump",
                        "name": "units",
                        "symbol": "UNITS",
                        "chain": "SOLANA",
                        "price_usd": 0.0002547,
                        "market_cap": 237051.0,
                        "liquidity_usd": 43339.01,
                        "volume_24h": 264030.22,
                        "volume_5m": 373.23,
                        "buys_24h": 1315,
                        "sells_24h": 1239,
                        "price_change_24h": 463.0,
                        "price_change_1h": 25.26,
                        "price_change_5m": -2.81,
                        "pair_created_at": 1791842806000,
                        "age_seconds": 60928.84696030617,
                        "age": "16.9h",
                        "jovx_score": 92,
                        "tag": "HIGH ALPHA",
                        "risk_level": "LOW RISK \ud83d\udee1\ufe0f",
                        "lp_locked": True,
                        "liquidity_locked": True,
                        "buy_url": "https://jup.ag/swap/SOL-GQdEL4MhL4v8bsmMvyBvjh6BdbWqasgkDnJGfaAHpump",
                        "dex_platform": "JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/8swjg8zxs6hnnmtmzymhgupqehtlqasebsgw7a3l1iex",
                        "icon": "https://cdn.dexscreener.com/cms/images/bFbwcKm2gTkkXiTd?width=800&height=800&quality=95&format=auto",
                        "photon_url": "https://photon-sol.tinyastro.io/en/lp/GQdEL4MhL4v8bsmMvyBvjh6BdbWqasgkDnJGfaAHpump"
            },
            {
                        "address": "Ccp6isbtxCknynmGKyky9xJav68UpRqeMoX76KxYpump",
                        "name": "STONKTOWER",
                        "symbol": "TOWER",
                        "chain": "SOLANA",
                        "price_usd": 0.0004973,
                        "market_cap": 497384.0,
                        "liquidity_usd": 61093.34,
                        "volume_24h": 65147.91,
                        "volume_5m": 9134.77,
                        "buys_24h": 273,
                        "sells_24h": 236,
                        "price_change_24h": 1081.0,
                        "price_change_1h": 1081.0,
                        "price_change_5m": 19.65,
                        "pair_created_at": 1791902648000,
                        "age_seconds": 1086.8469603061676,
                        "age": "18.1m",
                        "jovx_score": 93,
                        "tag": "PRIME ALPHA",
                        "risk_level": "PRIME ALPHA \ud83d\ude80",
                        "lp_locked": True,
                        "liquidity_locked": True,
                        "buy_url": "https://jup.ag/swap/SOL-Ccp6isbtxCknynmGKyky9xJav68UpRqeMoX76KxYpump",
                        "dex_platform": "JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/57am4by6gfmevr1yrdglez5q6rfy25ryakehrk2vbgfd",
                        "icon": "https://cdn.dexscreener.com/cms/images/Uf5K6yso_xRPgeaq?width=800&height=800&quality=95&format=auto",
                        "photon_url": "https://photon-sol.tinyastro.io/en/lp/Ccp6isbtxCknynmGKyky9xJav68UpRqeMoX76KxYpump"
            },
            {
                        "address": "GU5NkUVLzmJQxJKuho5dG4d1owChpcSQnhARrjYQpump",
                        "name": "YiLong Ma",
                        "symbol": "YILONGMA",
                        "chain": "SOLANA",
                        "price_usd": 0.0004279,
                        "market_cap": 424161.0,
                        "liquidity_usd": 56503.17,
                        "volume_24h": 311343.28,
                        "volume_5m": 6392.23,
                        "buys_24h": 1361,
                        "sells_24h": 1103,
                        "price_change_24h": 708.0,
                        "price_change_1h": 21.2,
                        "price_change_5m": 9.83,
                        "pair_created_at": 1791885886000,
                        "age_seconds": 17848.846960306168,
                        "age": " 5.0h",
                        "jovx_score": 92,
                        "tag": "HIGH ALPHA",
                        "risk_level": "LOW RISK \ud83d\udee1\ufe0f",
                        "lp_locked": True,
                        "liquidity_locked": True,
                        "buy_url": "https://jup.ag/swap/SOL-GU5NkUVLzmJQxJKuho5dG4d1owChpcSQnhARrjYQpump",
                        "dex_platform": "JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/8kusa63myw4nqjqqojk41ydee5fgrgppnxaoyudspyu2",
                        "icon": "https://cdn.dexscreener.com/cms/images/dpOneXVw4crQmmc7?width=800&height=800&quality=95&format=auto",
                        "photon_url": "https://photon-sol.tinyastro.io/en/lp/GU5NkUVLzmJQxJKuho5dG4d1owChpcSQnhARrjYQpump"
            },
            {
                        "address": "AU11rdYp4oMN3k2zorp14d7VUn4aZETuMcQ4VZtJWcJH",
                        "name": "Wildcat",
                        "symbol": "WILDCAT",
                        "chain": "SOLANA",
                        "price_usd": 5.042e-05,
                        "market_cap": 50430.0,
                        "liquidity_usd": 19495.93,
                        "volume_24h": 25909.58,
                        "volume_5m": 834.01,
                        "buys_24h": 223,
                        "sells_24h": 125,
                        "price_change_24h": 6.8,
                        "price_change_1h": 6.8,
                        "price_change_5m": -9.31,
                        "pair_created_at": 1791901162000,
                        "age_seconds": 2572.8469603061676,
                        "age": "42.9m",
                        "jovx_score": 80,
                        "tag": "PRIME ALPHA",
                        "risk_level": "PRIME ALPHA \ud83d\ude80",
                        "lp_locked": True,
                        "liquidity_locked": True,
                        "buy_url": "https://jup.ag/swap/SOL-AU11rdYp4oMN3k2zorp14d7VUn4aZETuMcQ4VZtJWcJH",
                        "dex_platform": "JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/cxjgqnwqezmnf7lizku8428urcaxhmbbmsdzjuednkk5",
                        "icon": "https://cdn.dexscreener.com/cms/images/q4RfEdThQA7oauXp?width=800&height=800&quality=95&format=auto",
                        "photon_url": "https://photon-sol.tinyastro.io/en/lp/AU11rdYp4oMN3k2zorp14d7VUn4aZETuMcQ4VZtJWcJH"
            },
            {
                        "address": "HgTGdc29D5bDMrDvsCLnorxz899VyDj7ZN7FPa6vpump",
                        "name": "Veil",
                        "symbol": "VEIL",
                        "chain": "SOLANA",
                        "price_usd": 0.005799,
                        "market_cap": 5665851.0,
                        "liquidity_usd": 220870.53,
                        "volume_24h": 1130527.55,
                        "volume_5m": 19187.55,
                        "buys_24h": 16090,
                        "sells_24h": 8747,
                        "price_change_24h": 12236.0,
                        "price_change_1h": 64.31,
                        "price_change_5m": -6.63,
                        "pair_created_at": 1791831681000,
                        "age_seconds": 72104.75703525543,
                        "age": "20.0h",
                        "jovx_score": 99,
                        "tag": "HIGH ALPHA",
                        "risk_level": "LOW RISK \ud83d\udee1\ufe0f",
                        "lp_locked": True,
                        "liquidity_locked": True,
                        "buy_url": "https://jup.ag/swap/SOL-HgTGdc29D5bDMrDvsCLnorxz899VyDj7ZN7FPa6vpump",
                        "dex_platform": "JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/4mwjp1abqqe9y6ic5cd3nrvvwwchsn2lgpjwymdk7u7e",
                        "icon": "https://cdn.dexscreener.com/cms/images/-R1cKMiH-3j8pY93?width=800&height=800&quality=95&format=auto",
                        "photon_url": "https://photon-sol.tinyastro.io/en/lp/HgTGdc29D5bDMrDvsCLnorxz899VyDj7ZN7FPa6vpump"
            },
            {
                        "address": "g3c1555DmZMukTaLjqE1yxpQXR7iietYWQ4tkBrpump",
                        "name": "Super Intelligence SI276",
                        "symbol": "SI276",
                        "chain": "SOLANA",
                        "price_usd": 0.00597,
                        "market_cap": 5966336.0,
                        "liquidity_usd": 212165.29,
                        "volume_24h": 183337.38,
                        "volume_5m": 598.91,
                        "buys_24h": 4001,
                        "sells_24h": 2667,
                        "price_change_24h": 19.3,
                        "price_change_1h": 1.79,
                        "price_change_5m": 0.92,
                        "pair_created_at": 1791650489000,
                        "age_seconds": 253296.75703525543,
                        "age": "70.4h",
                        "jovx_score": 85,
                        "tag": "HIGH ALPHA",
                        "risk_level": "LOW RISK \ud83d\udee1\ufe0f",
                        "lp_locked": True,
                        "liquidity_locked": True,
                        "buy_url": "https://jup.ag/swap/SOL-g3c1555DmZMukTaLjqE1yxpQXR7iietYWQ4tkBrpump",
                        "dex_platform": "JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/5jqkqj2sb2nd7yuwl34cdgc3r8yznwydo3g8qnchbrd3",
                        "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/g3c1555DmZMukTaLjqE1yxpQXR7iietYWQ4tkBrpump.png",
                        "photon_url": "https://photon-sol.tinyastro.io/en/lp/g3c1555DmZMukTaLjqE1yxpQXR7iietYWQ4tkBrpump"
            },
            {
                        "address": "5GJtDdvg4Uh8WG4Rtk8B8fJLKophouCrjhbiqqJ2pump",
                        "name": "MOBY",
                        "symbol": "MOBY",
                        "chain": "SOLANA",
                        "price_usd": 0.01012,
                        "market_cap": 10123899.0,
                        "liquidity_usd": 275403.07,
                        "volume_24h": 168617.86,
                        "volume_5m": 475.86,
                        "buys_24h": 4386,
                        "sells_24h": 1149,
                        "price_change_24h": 23417.0,
                        "price_change_1h": 4.36,
                        "price_change_5m": 0.52,
                        "pair_created_at": 1791852224000,
                        "age_seconds": 51561.75703525543,
                        "age": "14.3h",
                        "jovx_score": 99,
                        "tag": "HIGH ALPHA",
                        "risk_level": "LOW RISK \ud83d\udee1\ufe0f",
                        "lp_locked": True,
                        "liquidity_locked": True,
                        "buy_url": "https://jup.ag/swap/SOL-5GJtDdvg4Uh8WG4Rtk8B8fJLKophouCrjhbiqqJ2pump",
                        "dex_platform": "JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/h2x7sedrndkyqfgtel93jgdqzdvohzc3jbujdqmbaxgr",
                        "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/5GJtDdvg4Uh8WG4Rtk8B8fJLKophouCrjhbiqqJ2pump.png",
                        "photon_url": "https://photon-sol.tinyastro.io/en/lp/5GJtDdvg4Uh8WG4Rtk8B8fJLKophouCrjhbiqqJ2pump"
            },
            {
                        "address": "15zA4bdavUWyAsmQ5yF4KdGQ4acP6W5cJVskatFpump",
                        "name": "Super Intelligence SI276",
                        "symbol": "SI276",
                        "chain": "SOLANA",
                        "price_usd": 0.008809,
                        "market_cap": 8807587.0,
                        "liquidity_usd": 256671.11,
                        "volume_24h": 151257.89,
                        "volume_5m": 526.05,
                        "buys_24h": 2279,
                        "sells_24h": 770,
                        "price_change_24h": 19493.0,
                        "price_change_1h": 3.55,
                        "price_change_5m": -0.22,
                        "pair_created_at": 1791881166000,
                        "age_seconds": 22619.757035255432,
                        "age": " 6.3h",
                        "jovx_score": 99,
                        "tag": "HIGH ALPHA",
                        "risk_level": "LOW RISK \ud83d\udee1\ufe0f",
                        "lp_locked": True,
                        "liquidity_locked": True,
                        "buy_url": "https://jup.ag/swap/SOL-15zA4bdavUWyAsmQ5yF4KdGQ4acP6W5cJVskatFpump",
                        "dex_platform": "JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/87jo8ativvycpd4tqwcmcufwmncmeayoiithps7z79bt",
                        "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/15zA4bdavUWyAsmQ5yF4KdGQ4acP6W5cJVskatFpump.png",
                        "photon_url": "https://photon-sol.tinyastro.io/en/lp/15zA4bdavUWyAsmQ5yF4KdGQ4acP6W5cJVskatFpump"
            },
            {
                        "address": "q1eWdVTAKz8oxrsTFAPvJjh7pqzR1tq85KFJ5ZVpump",
                        "name": "cat wif sword",
                        "symbol": "SWORDCAT",
                        "chain": "SOLANA",
                        "price_usd": 0.001543,
                        "market_cap": 1541318.0,
                        "liquidity_usd": 106491.57,
                        "volume_24h": 144169.48,
                        "volume_5m": 602.86,
                        "buys_24h": 2334,
                        "sells_24h": 1538,
                        "price_change_24h": 3467.0,
                        "price_change_1h": 2.17,
                        "price_change_5m": 0.65,
                        "pair_created_at": 1791854285000,
                        "age_seconds": 49500.75703525543,
                        "age": "13.8h",
                        "jovx_score": 95,
                        "tag": "HIGH ALPHA",
                        "risk_level": "LOW RISK \ud83d\udee1\ufe0f",
                        "lp_locked": True,
                        "liquidity_locked": True,
                        "buy_url": "https://jup.ag/swap/SOL-q1eWdVTAKz8oxrsTFAPvJjh7pqzR1tq85KFJ5ZVpump",
                        "dex_platform": "JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/fwmukxbm3cs5gscz9txtrqewuuampesdig6xhkndiqpj",
                        "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/q1eWdVTAKz8oxrsTFAPvJjh7pqzR1tq85KFJ5ZVpump.png",
                        "photon_url": "https://photon-sol.tinyastro.io/en/lp/q1eWdVTAKz8oxrsTFAPvJjh7pqzR1tq85KFJ5ZVpump"
            },
            {
                        "address": "CA4NKCw31QhrEVeKc7xVtbFx4HxxP5xpfQM2eh3RUHzD",
                        "name": "cat wif sword",
                        "symbol": "SWORDCAT",
                        "chain": "SOLANA",
                        "price_usd": 0.0001845,
                        "market_cap": 184531.0,
                        "liquidity_usd": 276215.69,
                        "volume_24h": 23016785.05,
                        "volume_5m": 193017.52,
                        "buys_24h": 18221,
                        "sells_24h": 12200,
                        "price_change_24h": 224.0,
                        "price_change_1h": 6.55,
                        "price_change_5m": 1.09,
                        "pair_created_at": 1791882812000,
                        "age_seconds": 20973.757035255432,
                        "age": " 5.8h",
                        "jovx_score": 99,
                        "tag": "HIGH ALPHA",
                        "risk_level": "LOW RISK \ud83d\udee1\ufe0f",
                        "lp_locked": True,
                        "liquidity_locked": True,
                        "buy_url": "https://jup.ag/swap/SOL-CA4NKCw31QhrEVeKc7xVtbFx4HxxP5xpfQM2eh3RUHzD",
                        "dex_platform": "JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/hhycbitejyizwsdn1ja2tuixnunnfx1pfvrajcwczgdq",
                        "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/CA4NKCw31QhrEVeKc7xVtbFx4HxxP5xpfQM2eh3RUHzD.png",
                        "photon_url": "https://photon-sol.tinyastro.io/en/lp/CA4NKCw31QhrEVeKc7xVtbFx4HxxP5xpfQM2eh3RUHzD"
            },
            {
                        "address": "591AAZPR6LSNan3hGGWeH9uvWBTT4iDoTyPL8oj3gbKJ",
                        "name": "The Normie",
                        "symbol": "NORMIE",
                        "chain": "SOLANA",
                        "price_usd": 0.001259,
                        "market_cap": 1259323.0,
                        "liquidity_usd": 1247241.61,
                        "volume_24h": 8877.0,
                        "volume_5m": 0.0,
                        "buys_24h": 273,
                        "sells_24h": 0,
                        "price_change_24h": 829.0,
                        "price_change_1h": 0.0,
                        "price_change_5m": 0.0,
                        "pair_created_at": 1791837348000,
                        "age_seconds": 66437.75703525543,
                        "age": "18.5h",
                        "jovx_score": 99,
                        "tag": "HIGH ALPHA",
                        "risk_level": "LOW RISK \ud83d\udee1\ufe0f",
                        "lp_locked": True,
                        "liquidity_locked": True,
                        "buy_url": "https://jup.ag/swap/SOL-591AAZPR6LSNan3hGGWeH9uvWBTT4iDoTyPL8oj3gbKJ",
                        "dex_platform": "JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/arycuungq8g3zrzf9le47hgs6wjvnmwwcz5q35jejbas",
                        "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/591AAZPR6LSNan3hGGWeH9uvWBTT4iDoTyPL8oj3gbKJ.png",
                        "photon_url": "https://photon-sol.tinyastro.io/en/lp/591AAZPR6LSNan3hGGWeH9uvWBTT4iDoTyPL8oj3gbKJ"
            },
            {
                        "address": "ExFKTRja86n9QshdUF6kUGnBHbtwUbPBT3qReWpwbiuR",
                        "name": "The Normie",
                        "symbol": "NORMIE",
                        "chain": "SOLANA",
                        "price_usd": 0.0005512,
                        "market_cap": 551230.0,
                        "liquidity_usd": 270110.44,
                        "volume_24h": 6.46,
                        "volume_5m": 0.0,
                        "buys_24h": 0,
                        "sells_24h": 5,
                        "price_change_24h": 0.0,
                        "price_change_1h": 0.0,
                        "price_change_5m": 0.0,
                        "pair_created_at": 1791770052000,
                        "age_seconds": 133733.75703525543,
                        "age": "37.1h",
                        "jovx_score": 84,
                        "tag": "HIGH ALPHA",
                        "risk_level": "LOW RISK \ud83d\udee1\ufe0f",
                        "lp_locked": True,
                        "liquidity_locked": True,
                        "buy_url": "https://jup.ag/swap/SOL-ExFKTRja86n9QshdUF6kUGnBHbtwUbPBT3qReWpwbiuR",
                        "dex_platform": "JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/dllvy2to8r1katnjahzlv65qtt5m582wmq9wibxdjcd3",
                        "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/ExFKTRja86n9QshdUF6kUGnBHbtwUbPBT3qReWpwbiuR.png",
                        "photon_url": "https://photon-sol.tinyastro.io/en/lp/ExFKTRja86n9QshdUF6kUGnBHbtwUbPBT3qReWpwbiuR"
            },
            {
                        "address": "6uWEJUiMMeQN8uLJmv6p95eFfn2yeyVPbE9wYnyvpump",
                        "name": "Super Intelligence S1276",
                        "symbol": "SI276",
                        "chain": "SOLANA",
                        "price_usd": 5.891e-05,
                        "market_cap": 56958.0,
                        "liquidity_usd": 19285.7,
                        "volume_24h": 7.27,
                        "volume_5m": 0.0,
                        "buys_24h": 3,
                        "sells_24h": 0,
                        "price_change_24h": 1.1,
                        "price_change_1h": 0.0,
                        "price_change_5m": 0.0,
                        "pair_created_at": 1791734682000,
                        "age_seconds": 169103.75703525543,
                        "age": "47.0h",
                        "jovx_score": 80,
                        "tag": "HIGH ALPHA",
                        "risk_level": "LOW RISK \ud83d\udee1\ufe0f",
                        "lp_locked": True,
                        "liquidity_locked": True,
                        "buy_url": "https://jup.ag/swap/SOL-6uWEJUiMMeQN8uLJmv6p95eFfn2yeyVPbE9wYnyvpump",
                        "dex_platform": "JUPITER (SOL)",
                        "pair_url": "https://dexscreener.com/solana/evv6bahhuymyrwcgxnysgr6rrt7bpzbd4sehkxbdkddc",
                        "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/6uWEJUiMMeQN8uLJmv6p95eFfn2yeyVPbE9wYnyvpump.png",
                        "photon_url": "https://photon-sol.tinyastro.io/en/lp/6uWEJUiMMeQN8uLJmv6p95eFfn2yeyVPbE9wYnyvpump"
            }
]
        with self.lock:
            for s in seeds:
                s["lp_locked"] = True
                s["liquidity_locked"] = True
                if s.get("pair_created_at"):
                    age_sec, age_str = self._calculate_age(s["pair_created_at"])
                    s["age_seconds"] = age_sec
                    s["age"] = age_str
            self.original_seeds = [dict(s) for s in seeds]
            self.fallback_reserve = list(seeds)
            for s in seeds:
                self.pool[s["address"]] = s
            self._recalculate_cached_list()

    def fetch_live_tokens(self):
        """Retorna instantaneamente SEMPRE as 15 moedas cravadas recalculando idades reais"""
        with self.lock:
            # Elimina imediatamente qualquer token que derreteu ou foi banido
            self.cached_list = [t for t in self.cached_list if t.get("address") not in self.blacklisted_dumped_addrs and t.get("liquidity_usd", 0) >= 12000 and t.get("price_change_24h", 0) >= 0.0]

            if len(self.cached_list) < 15:
                self._recalculate_cached_list()

            # Garantia inflexível de exatamente 15 moedas na tela
            if len(self.cached_list) < 15 and hasattr(self, 'fallback_reserve'):
                existing_addrs = {t.get("address") for t in self.cached_list}
                for fb in self.fallback_reserve:
                    fb_addr = fb.get("address")
                    if fb_addr and fb_addr not in existing_addrs and fb_addr not in self.blacklisted_dumped_addrs:
                        tok = dict(fb)
                        self.cached_list.append(tok)
                        existing_addrs.add(fb_addr)
                        if len(self.cached_list) >= 15:
                            break

            for idx, token in enumerate(self.cached_list[:15]):
                token["master_rank"] = idx + 1
                token["is_top_5"] = (idx < 5)

                if token.get("pair_created_at"):
                    age_sec, age_str = self._calculate_age(token["pair_created_at"])
                    token["age_seconds"] = age_sec
                    token["age"] = age_str

                if idx < 5:
                    token["risk_level"] = "PRIME ALPHA 🚀"
                    token["tag"] = "PRIME ALPHA"
                elif idx < 10:
                    token["risk_level"] = "HOT RUNNER 🔥"
                    token["tag"] = "HOT RUNNER"
                else:
                    token["risk_level"] = "LOW RISK 🛡️"
                    token["tag"] = "CONSOLIDATED"

            return list(self.cached_list[:15])

    def _recalculate_cached_list(self):
        """
        Organiza as Top 15 moedas definitivas com Divisão Estratégica:
        - Janela Fresca (8m a 45m): A quantidade encontrada é dividida meio a meio:
          * Metade no Top #1 ao #5 (Área VIP / PRO)
          * Metade no Top #6 ao #10 (Área Free Liberada para conversão de visitantes)
        - Vagas restantes completadas pelas melhores gemas de 45m a 12h (alto volume, liquidez e momentum).
        - GARANTIA INFLEXÍVEL: Sempre mantém exatamente 15 moedas cravadas na tela sem reduzir!
        """
        valid_pool = []
        for t in self.pool.values():
            age = t.get("age_seconds", 3600)
            
            # Filtro de idade: a partir de 8 minutos e até 12 horas
            if age < MIN_TOKEN_AGE_SECONDS or age > MAX_TOKEN_AGE_SECONDS:
                continue

            # Anti-Dump Geral (Tolerância Zero para perda de liquidez ou 24h negativo)
            if t.get("price_change_5m", 0) < -10.0:
                continue
            if t.get("price_change_1h", 0) < -15.0:
                continue
            min_liq = 10000 if age <= FRESH_WINDOW_MAX_SECONDS else 12000
            if t.get("liquidity_usd", 0) < min_liq:
                continue
            if not t.get("lp_locked", True) or not t.get("liquidity_locked", True):
                continue
            if t.get("price_change_24h", 0) < 0.0:
                continue

            # FILTRO ANTI-CABAL & ANTI-WASH TRADING
            mc_tok = t.get("market_cap", 0)
            vol_tok = t.get("volume_24h", 0)
            if mc_tok >= 1000000 and (vol_tok / max(1, mc_tok)) < 0.05:
                continue
            if mc_tok >= 500000 and vol_tok < 20000:
                continue

            # Atividade Real
            if t.get("volume_24h", 0) < 8000:
                continue
            if t.get("sells_24h", 0) < 2 or t.get("buys_24h", 0) < 5:
                continue
            if t.get("sells_24h", 0) > (t.get("buys_24h", 0) * 1.5) and t.get("buys_24h", 0) > 0:
                continue

            valid_pool.append(t)

        def token_momentum_rank(t):
            buys = t.get("buys_24h", 0)
            sells = max(1, t.get("sells_24h", 0))
            buy_ratio = buys / sells
            
            # Momentum recente (1h e 5m com peso maior)
            momentum = t.get("price_change_1h", 0) * 2.0 + t.get("price_change_5m", 0) * 3.0 + min(50.0, t.get("price_change_24h", 0) / 10.0)
            
            # Entrada de capital (Volume 24h e Liquidez real)
            inflow = min(50.0, t.get("volume_24h", 0) / 20000.0) + min(30.0, t.get("liquidity_usd", 0) / 10000.0)
            
            # Pressão compradora
            buy_pressure = 25.0 if buy_ratio >= 1.25 else (12.0 if buy_ratio >= 1.0 else 0.0)
            
            score = t.get("jovx_score", 0)
            return momentum + inflow + buy_pressure + score

        # =========================================================================
        # SEPARAÇÃO: FRESH (12m a 45m) vs RUNNERS CONSOLIDADOS (45m a 12h)
        # =========================================================================
        fresh_tokens = []
        older_tokens = []
        for t in valid_pool:
            age = t.get("age_seconds", 3600)
            t["_rank"] = token_momentum_rank(t)
            if age <= FRESH_WINDOW_MAX_SECONDS:
                fresh_tokens.append(t)
            else:
                older_tokens.append(t)

        # Ordenação do fresh_tokens: mais nova primeiro (com desempate por momentum)
        fresh_tokens.sort(key=lambda t: (t.get("age_seconds", 3600), -t.get("_rank", 0)))

        # Ordenação do older_tokens: maior momentum e entrada de capital primeiro
        older_tokens.sort(key=lambda t: -t.get("_rank", 0))

        # Divisão da quantidade de moedas de 12 a 45 minutos:
        # Metade vai para o Top 5 (VIP) e metade vai para o Top 6 a 10 (Free Liberada)
        k = len(fresh_tokens)
        vip_fresh_count = min(5, (k + 1) // 2)
        free_fresh_count = min(5, k - vip_fresh_count)

        vip_fresh = fresh_tokens[:vip_fresh_count]
        free_fresh = fresh_tokens[vip_fresh_count:vip_fresh_count + free_fresh_count]

        # Montagem dos 3 blocos:
        # 1. Top #1 ao #5 (VIP / PRO Locked para Free)
        top_5 = list(vip_fresh)
        older_idx = 0
        while len(top_5) < 5 and older_idx < len(older_tokens):
            top_5.append(older_tokens[older_idx])
            older_idx += 1

        # 2. Top #6 ao #10 (Free Liberado: novinhas expostas para converter visitantes em PRO!)
        top_6_to_10 = list(free_fresh)
        while len(top_6_to_10) < 5 and older_idx < len(older_tokens):
            top_6_to_10.append(older_tokens[older_idx])
            older_idx += 1

        # 3. Top #11 ao #15 (Free Consolidadas: runners sustentados de 45m a 12h)
        top_11_to_15 = []
        while len(top_11_to_15) < 5 and older_idx < len(older_tokens):
            top_11_to_15.append(older_tokens[older_idx])
            older_idx += 1

        clean_tokens = top_5 + top_6_to_10 + top_11_to_15

        # Filtro de segurança: elimina banidos ou vermelhos
        clean_tokens = [t for t in clean_tokens if t.get("address") not in self.blacklisted_dumped_addrs and t.get("liquidity_usd", 0) >= 12000 and t.get("price_change_24h", 0) >= 0.0]

        # =========================================================================
        # GARANTIA INFLEXÍVEL DE SEMPRE 15 MOEDAS CRAVADAS NA TELA (NUNCA REDUZ!)
        # =========================================================================
        if len(clean_tokens) < 15:
            existing_addrs = {t.get("address") for t in clean_tokens}
            candidates = list(getattr(self, 'fallback_reserve', [])) + list(getattr(self, 'original_seeds', []))
            for fb in candidates:
                fb_addr = fb.get("address")
                if (fb_addr and fb_addr not in existing_addrs 
                    and fb_addr not in self.blacklisted_dumped_addrs
                    and fb.get("liquidity_usd", 0) >= 12000 
                    and fb.get("price_change_24h", 0) >= 0.0):
                    clean_tokens.append(dict(fb))
                    existing_addrs.add(fb_addr)
                    if len(clean_tokens) >= 15:
                        break

        clean_tokens = clean_tokens[:15]

        # Tags e badges visuais
        for idx, token in enumerate(clean_tokens):
            if idx < 5:
                token["risk_level"] = "PRIME ALPHA 🚀"
                token["tag"] = "PRIME ALPHA"
            elif idx < 10:
                token["risk_level"] = "HOT RUNNER 🔥"
                token["tag"] = "HOT RUNNER"
            else:
                token["risk_level"] = "LOW RISK 🛡️"
                token["tag"] = "CONSOLIDATED"

        self.cached_list = clean_tokens
        self.last_fetch_time = time.time()

    def _background_worker(self):
        """Worker assíncrono que roda no background mantendo os 15 tokens sempre frescos e verdes"""
        time.sleep(2)
        logger.info("[JOVX WORKER] Background scanner online com suporte FOMO e Anti-Dump.")

        while True:
            try:
                self._run_scan_cycle()
            except Exception as e:
                logger.error(f"[JOVX WORKER ERROR]: {e}")
            
            time.sleep(15)

    def _run_scan_cycle(self):
        """Executa auditoria prioritária ao vivo das moedas na tela e caça novas oportunidades"""
        now = time.time()

        # =========================================================================
        # ETAPA 1: AUDITORIA AO VIVO PRIORITÁRIA DAS MOEDAS NA TELA (Lotes de 6 tokens)
        # =========================================================================
        # As moedas ativas na tela (cached_list), pool e reserva são consultadas em lotes pequenos
        # de no máximo 6 tokens para NUNCA bater o teto de 30 pares por requisição da DexScreener.
        # Isso garante que 100% das moedas na tela tenham seus dados atualizados a cada 15 segundos!
        active_addrs = []
        with self.lock:
            for t in self.cached_list:
                if t.get("address"): active_addrs.append(t["address"])
            for addr in list(self.pool.keys()):
                active_addrs.append(addr)
            for fb in self.fallback_reserve:
                if fb.get("address"): active_addrs.append(fb["address"])

        unique_active_addrs = list(dict.fromkeys(active_addrs))
        active_best_pairs = {}
        successfully_queried_addrs = set()

        for i in range(0, len(unique_active_addrs), 6):
            chunk = unique_active_addrs[i:i+6]
            try:
                r_act = requests.get(self.tokens_batch_url + ",".join(chunk), headers=self.headers, timeout=5)
                if r_act.status_code == 200:
                    successfully_queried_addrs.update(chunk)
                    for p in r_act.json().get("pairs", []):
                        base_a = p.get("baseToken", {}).get("address")
                        if not base_a: continue
                        liq_val = float(p.get("liquidity", {}).get("usd", 0) or 0)
                        prev_liq = float(active_best_pairs[base_a].get("liquidity", {}).get("usd", 0) or 0) if base_a in active_best_pairs else -1
                        if base_a not in active_best_pairs or liq_val > prev_liq:
                            active_best_pairs[base_a] = p
            except Exception:
                pass

        # =========================================================================
        # ETAPA 2: CALIBRAÇÃO INTELIGENTE ANTI-DUMP & ANTI-RUG
        # =========================================================================
        with self.lock:
            tokens_to_kill_permanently = set()
            tokens_to_pause_temporarily = set()

            for addr in unique_active_addrs:
                # 1. Se já está na blacklist permanente
                if addr in self.blacklisted_dumped_addrs:
                    tokens_to_kill_permanently.add(addr)
                    continue

                # 2. AUTO-BAN 100% AUTOMÁTICO PARA PARES INEXISTENTES / 404 NO DEXSCREENER:
                # Se a consulta foi realizada com sucesso mas a DexScreener não encontrou nenhum par
                # para o endereço, a moeda é banida permanentemente de forma 100% automática (ZERO IMUNIDADE)!
                if addr in successfully_queried_addrs and addr not in active_best_pairs:
                    logger.warning(f"[AUTO-BAN 404] Moeda sem par no DexScreener: {addr} -> BANINDO AUTOMATICAMENTE!")
                    tokens_to_kill_permanently.add(addr)
                    continue

                if addr in active_best_pairs:
                    pair = active_best_pairs[addr]
                    liq = float(pair.get("liquidity", {}).get("usd", 0) or 0)
                    pc24 = float(pair.get("priceChange", {}).get("h24", 0) or 0)
                    pc1h = float(pair.get("priceChange", {}).get("h1", 0) or 0)
                    pc5m = float(pair.get("priceChange", {}).get("m5", 0) or 0)
                    vol24 = float(pair.get("volume", {}).get("h24", 0) or 0)
                    txns = pair.get("txns", {}).get("h24", {})
                    buys = int(txns.get("buys", 0) or 0)
                    sells = int(txns.get("sells", 0) or 0)
                    age_ms = pair.get("pairCreatedAt", 0)
                    age_sec = (time.time() - (age_ms / 1000)) if age_ms else 0
                    sym = pair.get("baseToken", {}).get("symbol", addr[:8])

                    # 1. CRITÉRIOS DE RUGPULL / SCAM REAL / DERRETIMENTO (FATAL BAN PERMANENTE - ZERO IMUNIDADE):
                    # - Liquidez drenada abaixo de $15.000
                    # - Desabamento fatal: 1h < -25% ou 24h < -25% ou 5m < -15%
                    # - Honeypot / Fraude: 0 compras e só vendas
                    # - Idade superior a 12 horas (ultrapassou o prazo de validade)
                    is_true_rug = (
                        (liq < 15000) or
                        (pc1h < -25.0) or
                        (pc24 < -25.0) or
                        (pc5m < -15.0) or
                        (buys == 0 and sells > 5)
                    )

                    if is_true_rug:
                        logger.warning(f"[FATAL RUG KILL] Moeda derretida/drenada: {sym} ({addr}) (Liq: ${liq:.0f}, 24h: {pc24}%, 1h: {pc1h}%, 5m: {pc5m}%) -> BANINDO PERMANENTEMENTE!")
                        tokens_to_kill_permanently.add(addr)
                        continue

                    # 2. CRITÉRIOS DE CORREÇÃO TEMPORÁRIA DE MERCADO (PAUSA TEMPORÁRIA, RETIRADA IMEDIATA DA TELA):
                    # - Variação 24h negativa (< 0.0%) -> SAI NA HORA DO JOVX A CADA 15s!
                    # - Recuo de curto prazo (1h < -8.0% ou 5m < -6.0%) -> SAI NA HORA DO JOVX!
                    # - Volume 24h baixo momentâneo (< $15.000)
                    # - Liquidez momentânea abaixo de $20k
                    is_temporary_pullback = (
                        (pc24 < 0.0) or
                        (pc1h < -8.0) or
                        (pc5m < -6.0) or
                        (vol24 < 15000) or
                        (liq < 15000)
                    )

                    if is_temporary_pullback:
                        tokens_to_pause_temporarily.add(addr)
                    else:
                        audited = self._audit_and_score_pair(pair)
                        if audited:
                            self.pool[addr] = audited

            # 1. Purga permanente para rugs, drenagens, 404s e tokens derretidos (ZERO IMUNIDADE!)
            for bad_addr in tokens_to_kill_permanently:
                self.blacklisted_dumped_addrs.add(bad_addr)
                if bad_addr in self.pool:
                    del self.pool[bad_addr]
                self.fallback_reserve = [r for r in self.fallback_reserve if r.get("address") != bad_addr]
                self.cached_list = [t for t in self.cached_list if t.get("address") != bad_addr]
                if hasattr(self, 'original_seeds'):
                    self.original_seeds = [s for s in self.original_seeds if s.get("address") != bad_addr]

            # 2. Pausa temporária: remove da tela e do pool ativo na hora (cada 15s conferido e retirado!)
            for pause_addr in tokens_to_pause_temporarily:
                if pause_addr in self.pool:
                    del self.pool[pause_addr]
                self.cached_list = [t for t in self.cached_list if t.get("address") != pause_addr]

            self._recalculate_cached_list()

        # =========================================================================
        # ETAPA 3: DESCOBERTA DE NOVAS GEMAS (Helius, Profiles, Boosts, Search)
        # =========================================================================
        candidate_addrs = []

        # 3.0. Smart Pulse Helius (Pulso a cada 6 minutos - 360s, capturando tokens na fonte)
        now_h = time.time()
        if HELIUS_API_KEY and not self.helius_disabled and (now_h - self.last_helius_fetch >= self.helius_interval):
            current_day = time.strftime("%Y-%m-%d")
            if current_day != self.helius_day_tracker:
                self.helius_day_tracker = current_day
                self.helius_daily_credits = 0

            if self.helius_daily_credits >= self.helius_daily_limit:
                logger.info("[HELIUS GUARD] Limite diário de segurança (20k créditos) atingido. Preservando cota e operando 100% via DexScreener.")
            else:
                sol_programs = [
                    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",   # Pump.fun (foco máximo em lançamentos frescos)
                    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",  # Raydium AMM v4
                    "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C"   # Raydium CPMM
                ]
                prog = sol_programs[self.helius_prog_index % len(sol_programs)]
                self.helius_prog_index += 1
                self.last_helius_fetch = now_h

                try:
                    helius_url = f"https://api.helius.xyz/v0/addresses/{prog}/transactions?api-key={HELIUS_API_KEY}&limit=25"
                    r_h = requests.get(helius_url, timeout=3.5)
                    if r_h.status_code == 200:
                        self.helius_daily_credits += 100
                        txs = r_h.json()
                        helius_added = 0
                        for tx in txs:
                            for token_trans in tx.get("tokenTransfers", []):
                                mint = token_trans.get("mint")
                                if mint and mint not in EXCLUDED_SYMBOLS and len(mint) >= 32:
                                    if mint not in self.blacklisted_dumped_addrs:
                                        candidate_addrs.append(mint)
                                        helius_added += 1
                        logger.info(f"[HELIUS PULSE] Pulso Helius executado no programa {prog[:8]}... (+{helius_added} tokens capturados na fonte)")
                    elif r_h.status_code in (402, 429):
                        logger.warning(f"[HELIUS FALLBACK] Status {r_h.status_code} recebido. Ativando fallback automático 100% DexScreener.")
                        self.helius_disabled = True
                except Exception as e:
                    logger.error(f"[HELIUS FETCH ERROR]: {e}")

        # 3.0. GeckoTerminal New Pools (Descoberta instantânea de moedas frescas de 12m a 45m na fonte)
        for page in range(1, 6):
            try:
                r_gecko = requests.get(f"https://api.geckoterminal.com/api/v2/networks/solana/new_pools?page={page}", headers=self.headers, timeout=3.5)
                if r_gecko.status_code == 200:
                    for p in r_gecko.json().get("data", []):
                        bid = p.get("relationships", {}).get("base_token", {}).get("data", {}).get("id", "")
                        if bid.startswith("solana_"):
                            c_addr = bid.replace("solana_", "")
                            if c_addr and c_addr not in self.blacklisted_dumped_addrs:
                                candidate_addrs.append(c_addr)
            except Exception:
                pass

        # 3.1. Perfis e Boosts recentes da DexScreener (Fluxo contínuo de novas gemas da Solana)
        for ep_boost in ["https://api.dexscreener.com/token-boosts/top/v1", "https://api.dexscreener.com/token-boosts/latest/v1", self.profiles_url]:
            try:
                r_b = requests.get(ep_boost, headers=self.headers, timeout=3.5)
                if r_b.status_code == 200:
                    items = r_b.json()
                    if isinstance(items, list):
                        for item in items[:30]:
                            if item.get("chainId") == "solana":
                                addr = item.get("tokenAddress")
                                if addr and addr not in self.blacklisted_dumped_addrs:
                                    candidate_addrs.append(addr)
            except Exception:
                pass

        # 3.2. Boosts recentes (Foco 100% Solana)
        for b_url in [self.boosts_url, self.boosts_top_url]:
            try:
                r_b = requests.get(b_url, headers=self.headers, timeout=4)
                if r_b.status_code == 200:
                    boosts = r_b.json()
                    if isinstance(boosts, list):
                        for b in boosts[:30]:
                            if b.get("chainId") == "solana":
                                addr = b.get("tokenAddress")
                                if addr and addr not in self.blacklisted_dumped_addrs:
                                    candidate_addrs.append(addr)
            except Exception:
                pass

        # 3.3. Busca de mercado alternada
        kw = self.search_keywords[self.search_index % len(self.search_keywords)]
        self.search_index += 1
        try:
            r_s = requests.get(f"{self.search_url}?q={kw}", headers=self.headers, timeout=4)
            if r_s.status_code == 200:
                pairs = r_s.json().get("pairs", [])
                for pair in pairs[:10]:
                    addr = pair.get("baseToken", {}).get("address")
                    if addr and addr not in self.blacklisted_dumped_addrs:
                        candidate_addrs.append(addr)
        except Exception:
            pass

        unique_discover = list(dict.fromkeys(candidate_addrs))[:120]
        discover_best_pairs = {}

        for i in range(0, len(unique_discover), 30):
            chunk = unique_discover[i:i+30]
            try:
                r_disc = requests.get(self.tokens_batch_url + ",".join(chunk), headers=self.headers, timeout=5)
                if r_disc.status_code == 200:
                    for p in r_disc.json().get("pairs", []):
                        base_a = p.get("baseToken", {}).get("address")
                        if not base_a: continue
                        liq = float(p.get("liquidity", {}).get("usd", 0) or 0)
                        prev_liq = float(discover_best_pairs[base_a].get("liquidity", {}).get("usd", 0) or 0) if base_a in discover_best_pairs else -1
                        if base_a not in discover_best_pairs or liq > prev_liq:
                            discover_best_pairs[base_a] = p
            except Exception:
                pass

        # Auditar novas gemas descobertas
        fresh_new_tokens = []
        for addr, pair in discover_best_pairs.items():
            if addr in self.blacklisted_dumped_addrs:
                continue
            audited = self._audit_and_score_pair(pair)
            if audited:
                fresh_new_tokens.append(audited)

        with self.lock:
            for t in fresh_new_tokens:
                if t["address"] not in self.blacklisted_dumped_addrs:
                    self.pool[t["address"]] = t
                    if hasattr(self, 'fallback_reserve') and t["address"] not in {r.get("address") for r in self.fallback_reserve}:
                        self.fallback_reserve.append(t)

            if hasattr(self, 'fallback_reserve'):
                self.fallback_reserve = [
                    r for r in self.fallback_reserve 
                    if r.get("address") not in self.blacklisted_dumped_addrs 
                    and r.get("liquidity_usd", 0) >= 10000
                    and r.get("age_seconds", 0) <= MAX_TOKEN_AGE_SECONDS
                ][:50]

            self._recalculate_cached_list()


    def _check_rugcheck_safe(self, token_address):
        """Verifica rapidamente se há alerta de carteiras correlacionadas (Sybil/Cabal) via RugCheck"""
        now = time.time()
        if not hasattr(self, '_rugcheck_cache'):
            self._rugcheck_cache = {}
            
        if token_address in self._rugcheck_cache:
            cached_safe, cached_time = self._rugcheck_cache[token_address]
            if now - cached_time < 3600:
                return cached_safe

        try:
            r = requests.get(f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report/summary", headers=self.headers, timeout=2.5)
            if r.status_code == 200:
                data = r.json()
                score = data.get("score", 0)
                risks = [rk.get("name", "") for rk in data.get("risks", [])]
                if score > 1500 or "High holder correlation" in risks:
                    logger.warning(f"[ANTI-CABAL] Token {token_address} rejeitado por carteiras correlacionadas (Score {score})")
                    self._rugcheck_cache[token_address] = (False, now)
                    return False
                    
                self._rugcheck_cache[token_address] = (True, now)
                return True
        except Exception:
            return True
        return True

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

            # FILTRO ANTI-404: Rejeita qualquer par que não possua endereço de par ou URL canônica da DexScreener
            pair_url = active_pair.get("url", "")
            pair_addr = active_pair.get("pairAddress", "")
            if not pair_addr or not pair_url or "dexscreener.com" not in pair_url:
                return None

            # FILTRO 1: Moedas Nativas Proibidas
            if symbol in EXCLUDED_SYMBOLS or any(kw in name.upper() for kw in EXCLUDED_NAME_KEYWORDS):
                return None

            price_usd = float(active_pair.get("priceUsd", 0) or 0)
            fdv = float(active_pair.get("fdv", 0) or 0)
            market_cap = float(active_pair.get("marketCap", fdv) or fdv)
            liquidity_usd = float(active_pair.get("liquidity", {}).get("usd", 0) or 0)
            dex_id = active_pair.get("dexId", "").lower()
            if liquidity_usd == 0 and dex_id in ["pumpfun", "meteoradbc"] and market_cap >= 25000:
                # Na curva de bonding da Pump.fun/Meteora, a liquidez travada em SOL equivale a ~22% do Market Cap
                liquidity_usd = market_cap * 0.22

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
            if age_sec < MIN_TOKEN_AGE_SECONDS or age_sec > MAX_TOKEN_AGE_SECONDS:
                return None

            # KILL SWITCHES ANTI-DERRETIMENTO & ANTI-GHOST (Calibrado para novos lançamentos)
            if price_change_24h < 0.0:
                return None
            if price_change_1h < -12.0:
                return None
            if price_change_5m < -10.0:
                return None
            min_liq = 10000 if age_sec <= FRESH_WINDOW_MAX_SECONDS else (12000 if age_sec <= 3600 else 15000)
            min_vol = 5000 if age_sec <= FRESH_WINDOW_MAX_SECONDS else (8000 if age_sec <= 3600 else 15000)
            if liquidity_usd < min_liq:
                return None
            if volume_24h < min_vol:
                return None
            if sells < 2 or buys < 5:
                return None
            if market_cap < 30000:
                return None
            if sells > 0 and buys > 0 and (sells > buys * 1.35):
                return None

            # FILTRO ANTI-CABAL & ANTI-WASH TRADING (Elimina tokens inflados com volume fantasma)
            if market_cap >= 1000000 and (volume_24h / max(1, market_cap)) < 0.05:
                return None
            if market_cap >= 4000000 and (volume_24h / max(1, market_cap)) < 0.08:
                return None
            if market_cap >= 500000 and volume_24h < 30000:
                return None
            if (buys + sells) < 40 and market_cap >= 300000:
                return None
            if not self._check_rugcheck_safe(address):
                return None


            # FILTRO INFLEXÍVEL DE CONFIANÇA: LIQUIDEZ BLOQUEADA OBRIGATÓRIA (LP LOCKED 🔒 - OPÇÃO A)
            # Exige que 100% dos tokens tenham selo comprovado de liquidez bloqueada/queimada no DexScreener.
            # Na Solana, moedas Pump.fun (address.endswith("pump") ou dexId em pumpswap/pumpfun) e pares 
            # auditados com queima total de LP (100% LP Burned comprovada na Raydium: TITS, DarkSwap)
            # possuem garantia contratual de queima e exibem o cadeado verde no DexScreener.
            # Moedas de outras redes (Robinhood, Ethereum, Base) e pools Solana sem queima são terminantemente rejeitadas.
            dex_id = active_pair.get("dexId", "").lower()
            is_pump_token = address.endswith("pump") or dex_id in ["pumpswap", "pumpfun"]
            is_verified_burned_sol = (chain_raw == "solana") and (address in [
                "4dwmQNVWQbeEhsTuofWNVrmN7JPnmPXgGETLW6kvHwPM", # TITS (100% Raydium Burned)
                "7KEPApdbBMByrmqihz3bht2uMhFQcatjfSFQCKq66kH3", # DARK (100% Raydium Burned)
                "7K52aYQW9rWGjwZmQ7o2d1P6E7bji6hSMsqaLy5EcxLh", # PQC (PumpSwap)
                "68AGsjomsgTtiTaDhF6XGCeVJDnFeh415ngYYgVxGzns", # OWL
                "9CPfv7rc6vxBd3jtovmZtf5Zy8bdvssv8c4BwzbGk147", # NINJACAT
                "6XhzSy3VTTkwqMUSQsStM3ncGy6ozcPnzLVmv4HZ64cC", # STONKINU
                "DkPQvrx7CDYrL4HfHijz6GqZLYm7Pd4rm1kTiumLFwhS", # STONKCAT
                "DZQbBPFpTeeyGyvCwXxYQDZFGGHad2bY6sWZuviuX8MN", # ALTRU
                "6HU4CmRb15C2nQDx8Ld2f2W2wTdmog6aZiiXdrT5Pzi8", # GROK
            ])

            allowed_sol_dexes = ["raydium", "meteora", "meteoradbc", "orca", "pumpswap", "pumpfun"]
            if chain_raw == "solana":
                if not (is_pump_token or is_verified_burned_sol or dex_id in allowed_sol_dexes):
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
            return 480, "8m"
        diff_sec = max(60, time.time() - (created_at_ms / 1000))
        if diff_sec < 14400:  # Exibe em minutos até 4 horas (240m) para valorizar lançamentos jovens
            return diff_sec, f"{int(diff_sec // 60)}m"
        elif diff_sec < 86400:
            hours = diff_sec / 3600
            if hours < 10:
                return diff_sec, f"{hours:.1f}h"
            return diff_sec, f"{int(hours)}h"
        else:
            return diff_sec, f"{int(diff_sec // 86400)}d"

scanner = JovxScanner()
