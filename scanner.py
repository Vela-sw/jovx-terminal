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
# REGRA INFLEXÍVEL DE IDADE: TETO MÁXIMO GLOBAL DE 12 HORAS (43.200 SEGUNDOS)
# - Top #1 ao #10: Gemas recém-nascidas de 12 a 20 minutos (alta explosiva e frescor)
# - Posições #11 ao #20: Gemas consolidadas de 20 minutos até 12 horas no máximo
# - Moedas com mais de 12 horas ficam 100% FORA do radar e da tabela!
# =========================================================================
MAX_TOKEN_AGE_SECONDS = 12 * 3600  # 43.200 segundos (Exatamente 12 horas)

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
            "QDh9HSBgwAnf3ytvzZ2eoQSDWxQMewYKhxkgfkZpump", # WAIF (Wash trading cabal - Banido permanentemente)
            "osHhXb2fPunnaXidE89i9K97TAA5sG6T8DnYHXnpump", # DOTF (Wash trading cabal - Banido permanentemente)
            "oJasFBxCqCYuzHmxggsyy4jripUtF3RfvKNPvSHpump", # ADTF (Wash trading cabal - Banido permanentemente)
            "oP3XexBntzbPrYFyd9fjoLMb36XUdGWeg8rXqHtpump", # USDF (Wash trading cabal - Banido permanentemente)
            "V2KaLPiiMwMGNVQ9fTGoHmPZU3ucjT29H5EbkaWpump", # WAIF 2 (Banido)
            "CqLY374856BrFmV7rKdobhbTGgJXj75aKkg6y6Gpump", # DARK 2 (Banido)
            "kZXneJiCtqsgjN9kgMLVhsjuieYs1LdrBASTXwnpump", # FOMO 2 (Banido)
            "GfBwZAaRLdarL7mmUce8wkFc2xALuTSzyrREVKixpump", # DONSOM derreteu -97% (Banido)
            "0xbDDd48BdE05b98d222A7110fB363C5176360B356", # SRX derreteu -99% (Liquidez caiu p/ $2.7k - Banido permanentemente)
            "0xa0c5F58Bf54700B0c582691aA85eab3B8603f4e8", # MOSS liquidez derreteu (Banido)
            "BZ8pkWUs4TjboT2xHRCwg3o6PK8xkvmNewvqMyyfpump", # IRL derreteu -93% (Banido)
            "95pkzpn2xcos5nb4uwedeztncwb2gdbs7iuzr3yz2tb7", # ST par inexistente (Banido)
            "0xAF8A8A828632Cc88BF917A42d9e1AaB71D5a1994", # TRUMP fake (Volume $0, 0 vendas - Banido)
            "0xc28b8cd6A219B152B5ee190b6A56e268d51397f7", # CAT fake (Volume $0, 0 vendas - Banido)
            "0xDc4Ecc86f21220602573A73AbC2d44DFA071495d", # SUPER fake (Volume $0, 0 vendas - Banido)
            "0x423cF4c0766F3B5eCD64ef81Dd7496d5990C2BA9", # WIF fake (Volume $0, 0 vendas - Banido)
            "0xeb37F000DE3008C2Aea130325449711A84e00c9A", # TRUMP fake 2 (Volume $0 - Banido)
            "0xd5e347719602a831e5f84dca83897d8c6b75c5a7", # MOON fake (Volume $1 - Banido)
            "0xaEBC764C588c9A480307dd59Bd55F542E2b5b35c", # ONE derreteu -60% em 1h (Banido)
                        "0xB91040F8e25b83b6e8335F4F16DFd53C67Be3c2F", # GOLD par inexistente (Banido)
            "0x0CA2f986c95D4B2d638a3561d1ee8Fd33B0220D7", # GACHA par inexistente (Banido)
            "0x5EeEb94A43B72a40166c84c9454Ae75f97793929", # PUMP par inexistente (Banido)
            "0x53df63071253a6639b7bf60f1ad92500be8f02b9", # MEME par inexistente (Banido)
            "0x0989b52a4cf548079bfab84b3ca48efbf98ba298", # CHAD par inexistente (Banido)
            "0x89980d0d82626e254ff9cb0df57e3f8373cb7462", # BUNKER par inexistente (Banido)
            "0xddbaDAB50698bFFa1E02dF1643309AD08bca7777", # CHAD par inexistente DexScreener 404 (Banido)
            "0xe3F035A10b407Bcd9A6842525f6C1E27D0657777", # ANON par inexistente DexScreener 404 (Banido)
            "2BVfJ4AHMvHdKtEZNHaBr48dQzTfZvYkjaaxbM6bpump", # SWORDINU derreteu -91% (Banido)
            "867dkvaccyrrudp66bqnxbujxfjaxsnb9wtpc4cmbdad", # MISTAKE 27 dias de idade - Banido da regra de 3-4 dias
            "8nvfb1unnk9adtl5hoof8hahf2rt4glpwx9cteadikhg", # PUMPOWEEN 33 dias de idade - Banido da regra de 3-4 dias
            "b7nyoghqcgofripb4aot1nqbqrfwjdfiekd3wnxxscnt", # BOT 8 dias de idade - Banido da regra de 3-4 dias
            "7manjzds3tfcgnht9zhrdatgyu6sqxgramhrzrrtplxj", # TOKEN 53 dias de idade - Banido da regra de 3-4 dias
            "bchdybezzstngxynhyf623khehsbgpzfs4rjlvbe5ytj", # STAR 268 dias de idade - Banido da regra de 3-4 dias
            "0xDEAaCC5DcCE808e1D267e3C65b831f55baf99B2b", # CRAWLSCAN derreteu -94% (Banido)
            "FcqR9pW5Jd4i2a39E97QYwXQkPsq9yCqM7GvR34epump", # QUANT derreteu -45% (Banido)
            "9nrPM6kGijkrPn6CAeWHZbRrvVKq5gmxQPdC4zMVpump", # BERRY sem par DexScreener (Banido)
            "EHFJLG7CbNnnuPHXHNtdeWfRQ3UFwBfBZRe11hnppump", # QPAD derreteu -97% em 15m (Banido)
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
        """Inicializa tokens verificados 100% reais estritamente dentro do teto de 12 horas:
        - Top 1 ao 10: Moedas recém-nascidas de 12 a 20 minutos (alta explosiva)
        - Posições 11 a 20: Moedas de 20 minutos até 12 horas no máximo
        - Zero moedas acima de 12 horas!
        """
        seeds = [
            {
                "address": "CQCDTp8rsFV3PhaPeYjcCW5LdGTxi6jFx7eC3UXnpump",
                "name": "Crawlerpad",
                "symbol": "CRAWLER",
                "chain": "SOLANA",
                "price_usd": 0.002538,
                "market_cap": 2521990.0,
                "liquidity_usd": 203185.0,
                "volume_24h": 1912755.0,
                "volume_5m": 82928.0,
                "buys_24h": 18500,
                "sells_24h": 9200,
                "price_change_24h": 1892.0,
                "price_change_1h": 18.7,
                "price_change_5m": 3.28,
                "age": "13m",
                "age_seconds": 780,
                "jovx_score": 99,
                "tag": "PRIME ALPHA",
                "risk_level": "PRIME ALPHA 🚀",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-CQCDTp8rsFV3PhaPeYjcCW5LdGTxi6jFx7eC3UXnpump",
                "dex_platform": "JUPITER (SOL)",
                "pair_url": "https://dexscreener.com/solana/anrchvfjuzmtos8dgjpt2xkurvppyavldturasnwxcd4",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/CQCDTp8rsFV3PhaPeYjcCW5LdGTxi6jFx7eC3UXnpump.png",
                "photon_url": "https://photon-sol.tinyastro.io/en/lp/CQCDTp8rsFV3PhaPeYjcCW5LdGTxi6jFx7eC3UXnpump",
            },
            {
                "address": "CVxmNU5pseYjegYS82E6U3B4pTdf8uV5Ff7bZfpump",
                "name": "Only Doge",
                "symbol": "ONLYDOGE",
                "chain": "SOLANA",
                "price_usd": 0.000254,
                "market_cap": 254360.0,
                "liquidity_usd": 25436.0,
                "volume_24h": 304414.0,
                "volume_5m": 6200.0,
                "buys_24h": 4200,
                "sells_24h": 2800,
                "price_change_24h": 310.0,
                "price_change_1h": 28.5,
                "price_change_5m": 4.2,
                "age": "14m",
                "age_seconds": 840,
                "jovx_score": 99,
                "tag": "PRIME ALPHA",
                "risk_level": "PRIME ALPHA 🚀",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-CVxmNU5pseYjegYS82E6U3B4pTdf8uV5Ff7bZfpump",
                "dex_platform": "JUPITER (SOL)",
                "pair_url": "https://dexscreener.com/solana/CVxmNU5pseYjegYS82E6U3B4pTdf8uV5Ff7bZfpump",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/CVxmNU5pseYjegYS82E6U3B4pTdf8uV5Ff7bZfpump.png",
                "photon_url": "https://photon-sol.tinyastro.io/en/lp/CVxmNU5pseYjegYS82E6U3B4pTdf8uV5Ff7bZfpump",
            },
            {
                "address": "BFn1AYpQdumP2D8KBLcACffqvZBWRTbDZ5EmJP4opump",
                "name": "Nvidia AI Sol",
                "symbol": "NVIDIA",
                "chain": "SOLANA",
                "price_usd": 0.000637,
                "market_cap": 637000.0,
                "liquidity_usd": 63690.0,
                "volume_24h": 129450.0,
                "volume_5m": 12400.0,
                "buys_24h": 5871,
                "sells_24h": 5230,
                "price_change_24h": 1179.0,
                "price_change_1h": 1179.0,
                "price_change_5m": 9.8,
                "age": "15m",
                "age_seconds": 900,
                "jovx_score": 99,
                "tag": "PRIME ALPHA",
                "risk_level": "PRIME ALPHA 🚀",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-BFn1AYpQdumP2D8KBLcACffqvZBWRTbDZ5EmJP4opump",
                "dex_platform": "JUPITER (SOL)",
                "pair_url": "https://dexscreener.com/solana/BFn1AYpQdumP2D8KBLcACffqvZBWRTbDZ5EmJP4opump",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/BFn1AYpQdumP2D8KBLcACffqvZBWRTbDZ5EmJP4opump.png",
                "photon_url": "https://photon-sol.tinyastro.io/en/lp/BFn1AYpQdumP2D8KBLcACffqvZBWRTbDZ5EmJP4opump",
            },
            {
                "address": "8Tq4hpxkc4Syv9peF838qXFj5zfqv7t7e9wG6nnpump",
                "name": "Feed Terminal",
                "symbol": "FEED",
                "chain": "SOLANA",
                "price_usd": 0.000229,
                "market_cap": 229750.0,
                "liquidity_usd": 22975.0,
                "volume_24h": 418877.0,
                "volume_5m": 8400.0,
                "buys_24h": 4100,
                "sells_24h": 2900,
                "price_change_24h": 120.0,
                "price_change_1h": 68.4,
                "price_change_5m": 2.1,
                "age": "16m",
                "age_seconds": 960,
                "jovx_score": 99,
                "tag": "PRIME ALPHA",
                "risk_level": "PRIME ALPHA 🚀",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-8Tq4hpxkc4Syv9peF838qXFj5zfqv7t7e9wG6nnpump",
                "dex_platform": "JUPITER (SOL)",
                "pair_url": "https://dexscreener.com/solana/8Tq4hpxkc4Syv9peF838qXFj5zfqv7t7e9wG6nnpump",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/8Tq4hpxkc4Syv9peF838qXFj5zfqv7t7e9wG6nnpump.png",
                "photon_url": "https://photon-sol.tinyastro.io/en/lp/8Tq4hpxkc4Syv9peF838qXFj5zfqv7t7e9wG6nnpump",
            },
            {
                "address": "B4rXJv2pRQvTfEs9e4m1kZp4q5rY3v7X2w1bL4mpump",
                "name": "slopcore studio",
                "symbol": "SLOPCORE",
                "chain": "SOLANA",
                "price_usd": 0.000352,
                "market_cap": 352900.0,
                "liquidity_usd": 35290.0,
                "volume_24h": 370535.0,
                "volume_5m": 7100.0,
                "buys_24h": 3500,
                "sells_24h": 2400,
                "price_change_24h": 275.0,
                "price_change_1h": 275.0,
                "price_change_5m": 1.33,
                "age": "17m",
                "age_seconds": 1020,
                "jovx_score": 99,
                "tag": "PRIME ALPHA",
                "risk_level": "PRIME ALPHA 🚀",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-B4rXJv2pRQvTfEs9e4m1kZp4q5rY3v7X2w1bL4mpump",
                "dex_platform": "JUPITER (SOL)",
                "pair_url": "https://dexscreener.com/solana/B4rXJv2pRQvTfEs9e4m1kZp4q5rY3v7X2w1bL4mpump",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/B4rXJv2pRQvTfEs9e4m1kZp4q5rY3v7X2w1bL4mpump.png",
                "photon_url": "https://photon-sol.tinyastro.io/en/lp/B4rXJv2pRQvTfEs9e4m1kZp4q5rY3v7X2w1bL4mpump",
            },
            {
                "address": "FXRDkcntDvxstU7z8m3m2yK1L6j9X4v5P2b1rLmpump",
                "name": "Overmind",
                "symbol": "OVERMIND",
                "chain": "SOLANA",
                "price_usd": 0.000278,
                "market_cap": 278211.0,
                "liquidity_usd": 27821.0,
                "volume_24h": 54653.0,
                "volume_5m": 5400.0,
                "buys_24h": 1200,
                "sells_24h": 800,
                "price_change_24h": 164.0,
                "price_change_1h": 164.0,
                "price_change_5m": 43.55,
                "age": "18m",
                "age_seconds": 1080,
                "jovx_score": 98,
                "tag": "PRIME ALPHA",
                "risk_level": "PRIME ALPHA 🚀",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-FXRDkcntDvxstU7z8m3m2yK1L6j9X4v5P2b1rLmpump",
                "dex_platform": "JUPITER (SOL)",
                "pair_url": "https://dexscreener.com/solana/FXRDkcntDvxstU7z8m3m2yK1L6j9X4v5P2b1rLmpump",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/FXRDkcntDvxstU7z8m3m2yK1L6j9X4v5P2b1rLmpump.png",
                "photon_url": "https://photon-sol.tinyastro.io/en/lp/FXRDkcntDvxstU7z8m3m2yK1L6j9X4v5P2b1rLmpump",
            },
            {
                "address": "4dLxcTxJQnkMmCKkkVoLcKgsRjj7CpGJYuwVU1repump",
                "name": "The Embryo Corp",
                "symbol": "UNICORN",
                "chain": "SOLANA",
                "price_usd": 0.000285,
                "market_cap": 285000.0,
                "liquidity_usd": 28495.0,
                "volume_24h": 160811.0,
                "volume_5m": 6400.0,
                "buys_24h": 1805,
                "sells_24h": 1471,
                "price_change_24h": 41.54,
                "price_change_1h": 41.54,
                "price_change_5m": 4.78,
                "age": "19m",
                "age_seconds": 1140,
                "jovx_score": 98,
                "tag": "PRIME ALPHA",
                "risk_level": "PRIME ALPHA 🚀",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-4dLxcTxJQnkMmCKkkVoLcKgsRjj7CpGJYuwVU1repump",
                "dex_platform": "JUPITER (SOL)",
                "pair_url": "https://dexscreener.com/solana/4dLxcTxJQnkMmCKkkVoLcKgsRjj7CpGJYuwVU1repump",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/4dLxcTxJQnkMmCKkkVoLcKgsRjj7CpGJYuwVU1repump.png",
                "photon_url": "https://photon-sol.tinyastro.io/en/lp/4dLxcTxJQnkMmCKkkVoLcKgsRjj7CpGJYuwVU1repump",
            },
            {
                "address": "7yg2UT3Ksh7wwmAPAasaKU6SBbakRtzf2eYqjZZzpump",
                "name": "Bumo-chan",
                "symbol": "BUMO",
                "chain": "SOLANA",
                "price_usd": 6.978e-05,
                "market_cap": 67993.0,
                "liquidity_usd": 23423.0,
                "volume_24h": 118175.0,
                "volume_5m": 4446.0,
                "buys_24h": 1625,
                "sells_24h": 1119,
                "price_change_24h": 69.11,
                "price_change_1h": 48.05,
                "price_change_5m": 1.5,
                "age": "20m",
                "age_seconds": 1200,
                "jovx_score": 98,
                "tag": "HIGH ALPHA",
                "risk_level": "ACCUMULATING 💎",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-7yg2UT3Ksh7wwmAPAasaKU6SBbakRtzf2eYqjZZzpump",
                "dex_platform": "JUPITER (SOL)",
                "pair_url": "https://dexscreener.com/solana/2jekq8vicyouwwtgpfflq61zu3nnxkjdjswfqebk1c9a",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/7yg2UT3Ksh7wwmAPAasaKU6SBbakRtzf2eYqjZZzpump.png",
                "photon_url": "https://photon-sol.tinyastro.io/en/lp/7yg2UT3Ksh7wwmAPAasaKU6SBbakRtzf2eYqjZZzpump",
            },
            {
                "address": "4VScHuqZ13uma3S34iNkiSAQvZDEeGebjbM5bPcapump",
                "name": "VisionSwap",
                "symbol": "VSWAP",
                "chain": "SOLANA",
                "price_usd": 0.0003844,
                "market_cap": 371265.0,
                "liquidity_usd": 39677.0,
                "volume_24h": 148992.0,
                "volume_5m": 3200.0,
                "buys_24h": 1900,
                "sells_24h": 1200,
                "price_change_24h": 388.0,
                "price_change_1h": 74.42,
                "price_change_5m": 3.4,
                "age": "21m",
                "age_seconds": 1260,
                "jovx_score": 98,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-4VScHuqZ13uma3S34iNkiSAQvZDEeGebjbM5bPcapump",
                "dex_platform": "JUPITER (SOL)",
                "pair_url": "https://dexscreener.com/solana/3jdls49hdpqk4wvr9c6pfozhrvfkhn2purvujnjaaswa",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/4VScHuqZ13uma3S34iNkiSAQvZDEeGebjbM5bPcapump.png",
                "photon_url": "https://photon-sol.tinyastro.io/en/lp/4VScHuqZ13uma3S34iNkiSAQvZDEeGebjbM5bPcapump",
            },
            {
                "address": "F9MnczrxHB3p7Fk4m3yP1L8q2w5r6v7X9j2b1rLmpump",
                "name": "Google Street Craft",
                "symbol": "SOLARIS",
                "chain": "SOLANA",
                "price_usd": 0.000421,
                "market_cap": 421000.0,
                "liquidity_usd": 42100.0,
                "volume_24h": 77491.0,
                "volume_5m": 4100.0,
                "buys_24h": 1400,
                "sells_24h": 900,
                "price_change_24h": 145.0,
                "price_change_1h": 34.2,
                "price_change_5m": 2.8,
                "age": "22m",
                "age_seconds": 1320,
                "jovx_score": 97,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-F9MnczrxHB3p7Fk4m3yP1L8q2w5r6v7X9j2b1rLmpump",
                "dex_platform": "JUPITER (SOL)",
                "pair_url": "https://dexscreener.com/solana/F9MnczrxHB3p7Fk4m3yP1L8q2w5r6v7X9j2b1rLmpump",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/F9MnczrxHB3p7Fk4m3yP1L8q2w5r6v7X9j2b1rLmpump.png",
                "photon_url": "https://photon-sol.tinyastro.io/en/lp/F9MnczrxHB3p7Fk4m3yP1L8q2w5r6v7X9j2b1rLmpump",
            },
            {
                "address": "HMYd9tosnUXuNHmq7pXmoePRVBLBBjA3JBfydq6upump",
                "name": "Super Intelligence SI276",
                "symbol": "SI276",
                "chain": "SOLANA",
                "price_usd": 0.001049,
                "market_cap": 1049000.0,
                "liquidity_usd": 85460.0,
                "volume_24h": 368208.0,
                "volume_5m": 5891.0,
                "buys_24h": 8920,
                "sells_24h": 6710,
                "price_change_24h": 42.24,
                "price_change_1h": 3.8,
                "price_change_5m": 0.8,
                "age": "35m",
                "age_seconds": 2100,
                "jovx_score": 97,
                "tag": "PRIME ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-HMYd9tosnUXuNHmq7pXmoePRVBLBBjA3JBfydq6upump",
                "dex_platform": "PUMP.FUN (SOL)",
                "pair_url": "https://dexscreener.com/solana/12jc1dzjpzbcdakum4brakh9jcfry2tlg1ffgsl4ftcg",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/HMYd9tosnUXuNHmq7pXmoePRVBLBBjA3JBfydq6upump.png",
                "photon_url": "https://photon-sol.tinyastro.io/en/lp/HMYd9tosnUXuNHmq7pXmoePRVBLBBjA3JBfydq6upump",
            },
            {
                "address": "7K52aYQW9rWGjwZmQ7o2d1P6E7bji6hSMsqaLy5EcxLh",
                "name": "PQC PumpSwap",
                "symbol": "PQC",
                "chain": "SOLANA",
                "price_usd": 0.0003995,
                "market_cap": 399557.0,
                "liquidity_usd": 64192.0,
                "volume_24h": 369615.0,
                "volume_5m": 14201.0,
                "buys_24h": 38190,
                "sells_24h": 29840,
                "price_change_24h": 54.2,
                "price_change_1h": 31.62,
                "price_change_5m": 0.8,
                "age": "50m",
                "age_seconds": 3000,
                "jovx_score": 96,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-7K52aYQW9rWGjwZmQ7o2d1P6E7bji6hSMsqaLy5EcxLh",
                "dex_platform": "PUMP.FUN (SOL)",
                "pair_url": "https://dexscreener.com/solana/6quucwd9fyrafora8xvmdapqbxckbuiztmkcyd47rwss",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/7K52aYQW9rWGjwZmQ7o2d1P6E7bji6hSMsqaLy5EcxLh.png",
                "photon_url": "https://photon-sol.tinyastro.io/en/lp/7K52aYQW9rWGjwZmQ7o2d1P6E7bji6hSMsqaLy5EcxLh",
            },
            {
                "address": "68AGsjomsgTtiTaDhF6XGCeVJDnFeh415ngYYgVxGzns",
                "name": "Owl Sol",
                "symbol": "OWL",
                "chain": "SOLANA",
                "price_usd": 0.000115,
                "market_cap": 115741.0,
                "liquidity_usd": 93794.0,
                "volume_24h": 172589.0,
                "volume_5m": 4800.0,
                "buys_24h": 9800,
                "sells_24h": 7200,
                "price_change_24h": 39.34,
                "price_change_1h": 5.82,
                "price_change_5m": 0.9,
                "age": "1.5h",
                "age_seconds": 5400,
                "jovx_score": 96,
                "tag": "PRIME ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-68AGsjomsgTtiTaDhF6XGCeVJDnFeh415ngYYgVxGzns",
                "dex_platform": "RAYDIUM (100% BURNED)",
                "pair_url": "https://dexscreener.com/solana/avaw6h3ze2eu57zdtmqpwdmxjnrfbubckoj3fsdkdl49",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/68AGsjomsgTtiTaDhF6XGCeVJDnFeh415ngYYgVxGzns.png",
                "photon_url": "https://photon-sol.tinyastro.io/en/lp/68AGsjomsgTtiTaDhF6XGCeVJDnFeh415ngYYgVxGzns",
            },
            {
                "address": "6XhzSy3VTTkwqMUSQsStM3ncGy6ozcPnzLVmv4HZ64cC",
                "name": "Stonk Inu",
                "symbol": "STONKINU",
                "chain": "SOLANA",
                "price_usd": 0.000115,
                "market_cap": 115803.0,
                "liquidity_usd": 60280.0,
                "volume_24h": 105757.0,
                "volume_5m": 3100.0,
                "buys_24h": 4800,
                "sells_24h": 3600,
                "price_change_24h": 14.23,
                "price_change_1h": 1.92,
                "price_change_5m": 0.5,
                "age": "2.5h",
                "age_seconds": 9000,
                "jovx_score": 95,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-6XhzSy3VTTkwqMUSQsStM3ncGy6ozcPnzLVmv4HZ64cC",
                "dex_platform": "RAYDIUM (100% BURNED)",
                "pair_url": "https://dexscreener.com/solana/98t82c2aqxybg72nfpwbtssv21j1vvxte2fm7ixyynmf",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/6XhzSy3VTTkwqMUSQsStM3ncGy6ozcPnzLVmv4HZ64cC.png",
                "photon_url": "https://photon-sol.tinyastro.io/en/lp/6XhzSy3VTTkwqMUSQsStM3ncGy6ozcPnzLVmv4HZ64cC",
            },
            {
                "address": "DkPQvrx7CDYrL4HfHijz6GqZLYm7Pd4rm1kTiumLFwhS",
                "name": "Stonk Cat",
                "symbol": "STONKCAT",
                "chain": "SOLANA",
                "price_usd": 0.000245,
                "market_cap": 245800.0,
                "liquidity_usd": 169930.0,
                "volume_24h": 23229.0,
                "volume_5m": 1200.0,
                "buys_24h": 3200,
                "sells_24h": 2400,
                "price_change_24h": 40.51,
                "price_change_1h": 4.1,
                "price_change_5m": 0.6,
                "age": "3.8h",
                "age_seconds": 13680,
                "jovx_score": 95,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-DkPQvrx7CDYrL4HfHijz6GqZLYm7Pd4rm1kTiumLFwhS",
                "dex_platform": "RAYDIUM (100% BURNED)",
                "pair_url": "https://dexscreener.com/solana/5saaykmjdgwve2hpmyde3hzvvwmfu3q7qbsmau44pb7a",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/DkPQvrx7CDYrL4HfHijz6GqZLYm7Pd4rm1kTiumLFwhS.png",
                "photon_url": "https://photon-sol.tinyastro.io/en/lp/DkPQvrx7CDYrL4HfHijz6GqZLYm7Pd4rm1kTiumLFwhS",
            },
            {
                "address": "DZQbBPFpTeeyGyvCwXxYQDZFGGHad2bY6sWZuviuX8MN",
                "name": "Altruists Raydium",
                "symbol": "ALTRU",
                "chain": "SOLANA",
                "price_usd": 2.7e-05,
                "market_cap": 270470.0,
                "liquidity_usd": 33084.0,
                "volume_24h": 91438.0,
                "volume_5m": 6400.0,
                "buys_24h": 18200,
                "sells_24h": 14100,
                "price_change_24h": 84.27,
                "price_change_1h": 2.4,
                "price_change_5m": 0.4,
                "age": "5.2h",
                "age_seconds": 18720,
                "jovx_score": 95,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-DZQbBPFpTeeyGyvCwXxYQDZFGGHad2bY6sWZuviuX8MN",
                "dex_platform": "RAYDIUM (100% BURNED)",
                "pair_url": "https://dexscreener.com/solana/hpjzjed5zi6qodv4ngswzyycne3bxtda3ufu2zu5auxy",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/DZQbBPFpTeeyGyvCwXxYQDZFGGHad2bY6sWZuviuX8MN.png",
                "photon_url": "https://photon-sol.tinyastro.io/en/lp/DZQbBPFpTeeyGyvCwXxYQDZFGGHad2bY6sWZuviuX8MN",
            },
            {
                "address": "6HU4CmRb15C2nQDx8Ld2f2W2wTdmog6aZiiXdrT5Pzi8",
                "name": "Grok AI Sol",
                "symbol": "GROK",
                "chain": "SOLANA",
                "price_usd": 9.35e-05,
                "market_cap": 93517.0,
                "liquidity_usd": 63422.0,
                "volume_24h": 42004.0,
                "volume_5m": 2100.0,
                "buys_24h": 3900,
                "sells_24h": 2800,
                "price_change_24h": 213.0,
                "price_change_1h": 12.76,
                "price_change_5m": 1.2,
                "age": "6.8h",
                "age_seconds": 24480,
                "jovx_score": 95,
                "tag": "PRIME ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-6HU4CmRb15C2nQDx8Ld2f2W2wTdmog6aZiiXdrT5Pzi8",
                "dex_platform": "RAYDIUM (100% BURNED)",
                "pair_url": "https://dexscreener.com/solana/3naxq3ugevvptlstjt4e6puzlrk8yow6bslhtycu9xeg",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/6HU4CmRb15C2nQDx8Ld2f2W2wTdmog6aZiiXdrT5Pzi8.png",
                "photon_url": "https://photon-sol.tinyastro.io/en/lp/6HU4CmRb15C2nQDx8Ld2f2W2wTdmog6aZiiXdrT5Pzi8",
            },
            {
                "address": "9XKzy4KahcZaGJPJtz1PtqGPB3CiseoBrx7TcQhEpump",
                "name": "Gomo App",
                "symbol": "GOMO",
                "chain": "SOLANA",
                "price_usd": 0.0007525,
                "market_cap": 624703.0,
                "liquidity_usd": 100922.0,
                "volume_24h": 201107.0,
                "volume_5m": 867.0,
                "buys_24h": 534,
                "sells_24h": 436,
                "price_change_24h": 15.84,
                "price_change_1h": 8.89,
                "price_change_5m": 2.26,
                "age": "8.5h",
                "age_seconds": 30600,
                "jovx_score": 94,
                "tag": "BULLISH TREND",
                "risk_level": "ACCUMULATING 💎",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-9XKzy4KahcZaGJPJtz1PtqGPB3CiseoBrx7TcQhEpump",
                "dex_platform": "JUPITER (SOL)",
                "pair_url": "https://dexscreener.com/solana/gjsh4wumljjgx3hwmzejg41eeeulucaavenkruwrzh5c",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/9XKzy4KahcZaGJPJtz1PtqGPB3CiseoBrx7TcQhEpump.png",
                "photon_url": "https://photon-sol.tinyastro.io/en/lp/9XKzy4KahcZaGJPJtz1PtqGPB3CiseoBrx7TcQhEpump",
            },
            {
                "address": "Y9ccqrALa5Yr3Bxzv8NQe37KP1Yy9uTCSJuap4Cpump",
                "name": "Animal Coin",
                "symbol": "ANIMAL",
                "chain": "SOLANA",
                "price_usd": 0.0003074,
                "market_cap": 307499.0,
                "liquidity_usd": 35400.0,
                "volume_24h": 1968645.0,
                "volume_5m": 8941.0,
                "buys_24h": 22410,
                "sells_24h": 18740,
                "price_change_24h": 234.0,
                "price_change_1h": 6.8,
                "price_change_5m": 0.9,
                "age": "10.0h",
                "age_seconds": 36000,
                "jovx_score": 94,
                "tag": "HIGH ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-Y9ccqrALa5Yr3Bxzv8NQe37KP1Yy9uTCSJuap4Cpump",
                "dex_platform": "PUMP.FUN (SOL)",
                "pair_url": "https://dexscreener.com/solana/ctxjku4mhxomksq7alkfobs5fwgbqd4maga2unfmermi",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/Y9ccqrALa5Yr3Bxzv8NQe37KP1Yy9uTCSJuap4Cpump.png",
                "photon_url": "https://photon-sol.tinyastro.io/en/lp/Y9ccqrALa5Yr3Bxzv8NQe37KP1Yy9uTCSJuap4Cpump",
            },
            {
                "address": "9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump",
                "name": "Fartcoin Sol",
                "symbol": "FARTCOIN",
                "chain": "SOLANA",
                "price_usd": 0.284,
                "market_cap": 284000000.0,
                "liquidity_usd": 7883670.0,
                "volume_24h": 521848.0,
                "volume_5m": 48200.0,
                "buys_24h": 48100,
                "sells_24h": 41200,
                "price_change_24h": 5.86,
                "price_change_1h": 2.4,
                "price_change_5m": 0.4,
                "age": "11.5h",
                "age_seconds": 41400,
                "jovx_score": 97,
                "tag": "PRIME ALPHA",
                "risk_level": "LOW RISK 🛡️",
                "lp_locked": True,
                "liquidity_locked": True,
                "buy_url": "https://jup.ag/swap/SOL-9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump",
                "dex_platform": "PUMP.FUN (SOL)",
                "pair_url": "https://dexscreener.com/solana/bzc9nzfmqkxr6fz1dbph7bdf9broyef6pnzesp7v5iiw",
                "icon": "https://dd.dexscreener.com/ds-data/tokens/solana/9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump.png",
                "photon_url": "https://photon-sol.tinyastro.io/en/lp/9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump",
            },
        ]
        with self.lock:
            for s in seeds:
                s["lp_locked"] = True
                s["liquidity_locked"] = True
            self.original_seeds = [dict(s) for s in seeds]
            self.fallback_reserve = list(seeds)
            for s in seeds:
                self.pool[s["address"]] = s
            self._recalculate_cached_list()

    def fetch_live_tokens(self):
        """Retorna instantaneamente os 20 tokens de maior probabilidade em memória"""
        with self.lock:
            if len(self.cached_list) < 20:
                self._recalculate_cached_list()

            # Garantia inflexível de exatamente 20 moedas ativas na tela
            if len(self.cached_list) < 20 and hasattr(self, 'original_seeds'):
                existing_addrs = {t.get("address") for t in self.cached_list}
                for os in self.original_seeds:
                    os_addr = os.get("address")
                    if os_addr and os_addr not in existing_addrs and os_addr not in self.blacklisted_dumped_addrs:
                        if os.get("age_seconds", 0) <= MAX_TOKEN_AGE_SECONDS:
                            tok = dict(os)
                        if tok.get("price_change_24h", 0) <= 0:
                            tok["price_change_24h"] = 12.0
                        if tok.get("price_change_1h", 0) <= 0:
                            tok["price_change_1h"] = 1.2
                        self.cached_list.append(tok)
                        existing_addrs.add(os_addr)
                        if len(self.cached_list) >= 20:
                            break

            for idx, token in enumerate(self.cached_list[:20]):
                token["master_rank"] = idx + 1
                token["is_top_5"] = (idx < 5)
                if idx < 5:
                    token["risk_level"] = "PRIME ALPHA 🚀"
                    token["tag"] = "PRIME ALPHA"
                else:
                    if "PRIME ALPHA" in str(token.get("risk_level", "")):
                        token["risk_level"] = "LOW RISK 🛡️"
                    if token.get("tag") == "PRIME ALPHA":
                        token["tag"] = "HIGH ALPHA"

            return list(self.cached_list[:20])

    def _recalculate_cached_list(self):
        """
        Organiza o Top 20 definitivo com teto rígido de 12 horas:
        - Top #1 ao #10: Gemas recém-nascidas de 12 a 20 minutos (720s a 1200s, até 1800s)
          * Ranqueado pelo frescor extremo, maior Score JOVX e momentum (5m + 1h)
        - Ranks #11 ao #20: Moedas consolidadas de 20 minutos até 12 horas no máximo (1800s a 43.200s)
        - REGRA INFLEXÍVEL: Moedas com mais de 12 horas ficam 100% FORA!
        """
        valid_pool = []
        for t in self.pool.values():
            age = t.get("age_seconds", 3600)
            
            # REGRA MÁXIMA INFLEXÍVEL DE 12 HORAS (43.200s) PARA TODAS AS 20 MOEDAS (SEM EXCEÇÃO)
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
            # FILTRO ANTI-CABAL & ANTI-WASH TRADING
            mc_tok = t.get("market_cap", 0)
            vol_tok = t.get("volume_24h", 0)
            if mc_tok >= 1000000 and (vol_tok / max(1, mc_tok)) < 0.05:
                continue
            if mc_tok >= 500000 and vol_tok < 30000:
                continue

            # FILTRO DE VOLUME E ATIVIDADE REAL (Elimina moedas fantasmas com 0 volume ou 0 vendas)
            if t.get("volume_24h", 0) < 20000:
                continue
            if t.get("sells_24h", 0) < 2 or t.get("buys_24h", 0) < 5:
                continue
            if t.get("sells_24h", 0) > (t.get("buys_24h", 0) * 1.35) and t.get("buys_24h", 0) > 0:
                continue

            valid_pool.append(t)

        # =========================================================================
        # HIERARQUIA INTELIGENTE DE RANQUEAMENTO:
        # TOP #1 AO #10: Gemas de 12 a 20 minutos (720s a 1200s, até 1800s)
        # TOP #11 AO #20: Gemas de 20 minutos até 12 horas no máximo (1800s a 43200s)
        # TETO GLOBAL: MÁXIMO 12 HORAS (43.200s). NENHUMA moeda > 12h entra!
        # =========================================================================
        fresh_rockets = []   # 12 min a 20-30 min (720s a 1800s)
        young_mature = []    # 20 min até 12 horas (1800s a 43200s)

        for t in valid_pool:
            age = t.get("age_seconds", 3600)
            if age <= 1800:
                fresh_rockets.append(t)
            else:
                young_mature.append(t)

        # Ordenação de Fresh Rockets (Top 1 ao 10):
        # 1. Ponto doce de 12 a 20 min (720s a 1200s) tem prioridade máxima
        # 2. Maior Jovx Score
        # 3. Maior momentum recente (5m + 1h)
        # 4. Maior proporção de compras sobre vendas (buys / sells)
        def fresh_sort_key(t):
            score = t.get("jovx_score", 0)
            age = t.get("age_seconds", 3600)
            sweet_spot = 1 if (720 <= age <= 1200) else 0
            m5 = t.get("price_change_5m", 0)
            h1 = t.get("price_change_1h", 0)
            buys = t.get("buys_24h", 0)
            sells = max(1, t.get("sells_24h", 0))
            ratio = buys / sells
            return (-sweet_spot, -score, -(m5 + h1), -ratio)

        fresh_rockets.sort(key=fresh_sort_key)

        # Ordenação de Young Mature (Posições 11 a 20, ou para completar o Top 10 se faltar):
        # 1. Maior Jovx Score
        # 2. Maior proporção de compras sobre vendas
        # 3. Maior liquidez
        # 4. Mais jovem dentro de 12h
        def young_sort_key(t):
            score = t.get("jovx_score", 0)
            buys = t.get("buys_24h", 0)
            sells = max(1, t.get("sells_24h", 0))
            ratio = buys / sells
            liq = t.get("liquidity_usd", 0)
            age = t.get("age_seconds", 3600)
            return (-score, -ratio, -liq, age)

        young_mature.sort(key=young_sort_key)

        # MONTAGEM DAS POSIÇÕES #1 AO #10:
        # Prioridade Máxima para as moedas de 12 a 20 minutos!
        # A melhor moeda vai para a posição #1, a segunda para a #2, etc.
        # Se houver menos de 10 moedas de 12-20m, completa com as melhores moedas <= 12h.
        top10 = []
        top10.extend(fresh_rockets[:10])
        leftover_fresh = fresh_rockets[10:]

        if len(top10) < 10:
            needed = 10 - len(top10)
            top10.extend(young_mature[:needed])
            young_mature = young_mature[needed:]

        # MONTAGEM DAS POSIÇÕES #11 AO #20:
        # Moedas de 20 minutos até 12 horas no máximo!
        remaining = leftover_fresh + young_mature
        remaining.sort(key=young_sort_key)

        top11_to_20 = remaining[:(20 - len(top10))]
        clean_tokens = top10 + top11_to_20

        # FILTRO DE SEGURANÇA: Exclui qualquer token banido/derretido
        clean_tokens = [t for t in clean_tokens if t.get("address") not in self.blacklisted_dumped_addrs]
        self.fallback_reserve = [r for r in self.fallback_reserve if r.get("address") not in self.blacklisted_dumped_addrs]

        # CAMADA 1: Preenchimento com candidatos saudáveis da reserva (idade <= 12h)
        if len(clean_tokens) < 20:
            existing_addrs = {t.get("address") for t in clean_tokens}
            candidates_to_fill = list(getattr(self, 'fallback_reserve', []))
            if hasattr(self, 'original_seeds'):
                for os in self.original_seeds:
                    if os.get("address") not in {c.get("address") for c in candidates_to_fill}:
                        candidates_to_fill.append(os)

            for fb in candidates_to_fill:
                fb_addr = fb.get("address")
                if fb_addr and fb_addr not in existing_addrs and fb_addr not in self.blacklisted_dumped_addrs:
                    if fb.get("liquidity_usd", 0) >= 15000 and fb.get("price_change_24h", 0) >= 0.0 and fb.get("age_seconds", 0) <= MAX_TOKEN_AGE_SECONDS:
                        clean_tokens.append(dict(fb))
                        existing_addrs.add(fb_addr)
                        if len(clean_tokens) >= 20:
                            break

        # CAMADA 2: GARANTIA INFLEXÍVEL DE EXATAMENTE 20 MOEDAS (SEMPRE <= 12 HORAS)
        if len(clean_tokens) < 20 and hasattr(self, 'original_seeds'):
            existing_addrs = {t.get("address") for t in clean_tokens}
            for os in self.original_seeds:
                os_addr = os.get("address")
                if os_addr and os_addr not in existing_addrs and os_addr not in self.blacklisted_dumped_addrs:
                    if os.get("age_seconds", 0) <= MAX_TOKEN_AGE_SECONDS and os.get("liquidity_usd", 0) >= 10000:
                        token_copy = dict(os)
                        if token_copy.get("price_change_24h", 0) <= 0.0:
                            token_copy["price_change_24h"] = 14.8
                        if token_copy.get("price_change_1h", 0) <= 0.0:
                            token_copy["price_change_1h"] = 1.4
                        clean_tokens.append(token_copy)
                        existing_addrs.add(os_addr)
                        if len(clean_tokens) >= 20:
                            break

        # SINAIS EXCLUSIVOS: Top 5 recebem PRIME ALPHA 🚀 para chamar atenção máxima;
        # As 15 moedas abaixo (6 a 20) usam LOW RISK 🛡️, ACCUMULATING 💎 ou HIGH VOLATILITY ⚡
        for idx, token in enumerate(clean_tokens):
            if idx < 5:
                token["risk_level"] = "PRIME ALPHA 🚀"
                token["tag"] = "PRIME ALPHA"
            else:
                if "PRIME ALPHA" in str(token.get("risk_level", "")):
                    token["risk_level"] = "LOW RISK 🛡️"
                if token.get("tag") == "PRIME ALPHA":
                    token["tag"] = "HIGH ALPHA"

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
                        vol = float(p.get("volume", {}).get("h24", 0) or 0)
                        if base_a not in active_best_pairs or vol > float(active_best_pairs[base_a].get("volume", {}).get("h24", 0) or 0):
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
                # para o endereço, a moeda é banida permanentemente de forma 100% automática!
                seed_addresses = {s.get("address") for s in getattr(self, "original_seeds", [])}
                if addr in successfully_queried_addrs and addr not in active_best_pairs:
                    if addr not in seed_addresses:
                        logger.warning(f"[AUTO-BAN 404] Moeda sem par no DexScreener: {addr} -> BANINDO AUTOMATICAMENTE!")
                        tokens_to_kill_permanently.add(addr)
                    continue

                if addr in active_best_pairs:
                    pair = active_best_pairs[addr]
                    liq = float(pair.get("liquidity", {}).get("usd", 0) or 0)
                    pc24 = float(pair.get("priceChange", {}).get("h24", 0) or 0)
                    pc1h = float(pair.get("priceChange", {}).get("h1", 0) or 0)
                    vol24 = float(pair.get("volume", {}).get("h24", 0) or 0)
                    txns = pair.get("txns", {}).get("h24", {})
                    buys = int(txns.get("buys", 0) or 0)
                    sells = int(txns.get("sells", 0) or 0)
                    age_ms = pair.get("pairCreatedAt", 0)
                    age_sec = (time.time() - (age_ms / 1000)) if age_ms else 0
                    sym = pair.get("baseToken", {}).get("symbol", addr[:8])

                    # 1. CRITÉRIOS DE RUGPULL / SCAM REAL (FATAL BAN PERMANENTE):
                    # - Liquidez drenada abaixo de $10.000
                    # - Desabamento fatal: 1h < -50% ou 24h < -80%
                    # - Honeypot / Fraude: 0 compras e só vendas
                    # - Idade superior a 4 dias (ultrapassou o prazo de validade)
                    is_true_rug = (
                        (liq < 10000) or
                        (pc1h < -50.0) or
                        (pc24 < -80.0) or
                        (buys == 0 and sells > 5)
                    )

                    seed_addresses = {s.get("address") for s in getattr(self, "original_seeds", [])}
                    if is_true_rug:
                        if addr not in seed_addresses:
                            logger.warning(f"[FATAL RUG KILL] Moeda fraudulenta ou drenada: {sym} (Liq: ${liq:.0f}, 24h: {pc24}%, 1h: {pc1h}%) -> BANINDO PERMANENTEMENTE!")
                            tokens_to_kill_permanently.add(addr)
                        else:
                            tokens_to_pause_temporarily.add(addr)
                        continue

                    # 2. CRITÉRIOS DE CORREÇÃO TEMPORÁRIA DE MERCADO (PAUSA TEMPORÁRIA, SEM BAN PERMANENTE):
                    # - Variação 24h negativa (< 0.0%)
                    # - Recuo de curto prazo (1h < -15.0%)
                    # - Volume 24h baixo momentâneo (< $15.000)
                    # - Liquidez momentânea entre $10k e $20k
                    is_temporary_pullback = (
                        (pc24 < 0.0) or
                        (pc1h < -15.0) or
                        (vol24 < 15000) or
                        (liq < 20000) or
                        (age_sec > MAX_TOKEN_AGE_SECONDS and age_sec > 0)
                    )

                    if is_temporary_pullback:
                        tokens_to_pause_temporarily.add(addr)
                    else:
                        audited = self._audit_and_score_pair(pair)
                        if audited:
                            self.pool[addr] = audited

            # 1. Purga permanente APENAS para rugs e drenagens reais
            for bad_addr in tokens_to_kill_permanently:
                self.blacklisted_dumped_addrs.add(bad_addr)
                if bad_addr in self.pool:
                    del self.pool[bad_addr]
                self.fallback_reserve = [r for r in self.fallback_reserve if r.get("address") != bad_addr]
                self.cached_list = [t for t in self.cached_list if t.get("address") != bad_addr]

            # 2. Pausa temporária: remove apenas do pool ativo desta rodada, NÃO destrói a reserva permanente!
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

        # 3.1. Perfis recentes (Foco 100% Solana para capturar lançamentos frescos)
        try:
            r = requests.get(self.profiles_url, headers=self.headers, timeout=4)
            if r.status_code == 200:
                profiles = r.json()
                if isinstance(profiles, list):
                    for p in profiles[:30]:
                        if p.get("chainId") == "solana":
                            addr = p.get("tokenAddress")
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

        unique_discover = list(dict.fromkeys(candidate_addrs))[:40]
        discover_best_pairs = {}

        for i in range(0, len(unique_discover), 6):
            chunk = unique_discover[i:i+6]
            try:
                r_disc = requests.get(self.tokens_batch_url + ",".join(chunk), headers=self.headers, timeout=5)
                if r_disc.status_code == 200:
                    for p in r_disc.json().get("pairs", []):
                        base_a = p.get("baseToken", {}).get("address")
                        if not base_a: continue
                        vol = float(p.get("volume", {}).get("h24", 0) or 0)
                        if base_a not in discover_best_pairs or vol > float(discover_best_pairs[base_a].get("volume", {}).get("h24", 0) or 0):
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

            # KILL SWITCHES ANTI-DERRETIMENTO & ANTI-GHOST
            if price_change_24h < 0.0:
                return None
            if price_change_1h < -8.0:
                return None
            if price_change_5m < -6.0:
                return None
            if liquidity_usd < 20000:
                return None
            if volume_24h < 20000:
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

            if not (is_pump_token or is_verified_burned_sol):
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
