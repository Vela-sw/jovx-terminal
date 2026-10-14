import os

# Configurações do JOVX Terminal (100% Isolado da VELA)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Servidor
PORT = int(os.environ.get("PORT", os.environ.get("JOVX_PORT", 5050)))
DEBUG = os.environ.get("JOVX_DEBUG", "True").lower() == "true"

# Stripe (Link de Pagamento Oficial Mensal Configurado)
STRIPE_PAYMENT_LINK = os.environ.get("STRIPE_PAYMENT_LINK", "https://buy.stripe.com/6oU3co1LR3Uf7Od9KY0co0a")
STRIPE_PUBLIC_KEY = os.environ.get("STRIPE_PUBLIC_KEY", "pk_test_sample_jovx")
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "sk_test_sample_jovx")
STRIPE_PRICE_ID_PRO = os.environ.get("STRIPE_PRICE_ID_PRO", "price_pro_monthly_19_90usd")
PRO_PRICE_USD = 19.90
PRO_ACCESS_MONTHS = 1

# Regras do Algoritmo de Probabilidade JOVX (Top 20 Moedas Definitivo)
TOTAL_DISPLAY_TOKENS = 20             # 20 moedas cravadas no total
MIN_TOKEN_AGE_SECONDS = 480          # 8 minutos (proteção contra snipers de berçário)
FRESH_WINDOW_MAX_SECONDS = 2700       # 45 minutos (janela de moedas ultra-frescas)
MAX_TOKEN_AGE_DAYS = 1                # Máximo absoluto de 24 horas (1 dia)
MAX_TOKEN_AGE_SECONDS = 86400        # 24 horas cravadas (86.400 segundos)
MIN_LIQUIDITY_USD = 10000           # Permite entrada de lançamentos frescos a partir de $10k
MAX_TOP10_HOLDERS_PCT = 25.0        # Alerta se Top 10 tiver mais de 25%
MIN_MARKET_CAP_USD = 30000          # Descarta micro-lixo abaixo de $30k
TARGET_CHAINS = ["solana", "base", "ethereum", "robinhood"]

# Filtros Anti-Manipulação e Anti-Wash Trading (Gemas Orgânicas de Longa Duração)
MIN_AVG_TRADE_TICKET_USD = 14.0       # Descarta bots de micro-swaps (0.02 - 0.04 SOL / $3-$6)
MAX_VOL_LIQUIDITY_RATIO = 35.0        # Descarta anomalias de churn artificial em pools rasos
MIN_LIQ_MC_RATIO = 0.025              # Mínimo de 2.5% de liquidez real para microcaps
MAX_SELL_BUY_RATIO = 1.35             # Descarta moedas com pressão vendedora de dev dump

# Helius Infrastructure (Solana Real-Time Sub-Second Feed)
HELIUS_API_KEY = os.environ.get("HELIUS_API_KEY", "793ee1a9-6bef-48b2-bfa9-f0270ad46857")
HELIUS_RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}" if HELIUS_API_KEY else ""
HELIUS_WS_URL = f"wss://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}" if HELIUS_API_KEY else ""
