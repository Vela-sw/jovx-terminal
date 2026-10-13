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

# Regras do Algoritmo de Probabilidade JOVX (Top 20 Explosivo & Inflow a partir de 12 minutos)
MIN_TOKEN_AGE_SECONDS = 720          # 12 minutos (proteção contra snipers de berçário)
MAX_TOKEN_AGE_HOURS = 72             # 3 dias (72 horas) para ampla seleção de gemas explosivas
MAX_TOKEN_AGE_SECONDS = 72 * 3600   # 259.200 segundos
MIN_LIQUIDITY_USD = 12000           # Permite entrada de lançamentos frescos a partir de $12k
MAX_TOP10_HOLDERS_PCT = 25.0        # Alerta se Top 10 tiver mais de 25%
MIN_MARKET_CAP_USD = 30000          # Descarta micro-lixo abaixo de $30k
TARGET_CHAINS = ["solana", "base", "ethereum", "robinhood"]

# Helius Infrastructure (Solana Real-Time Sub-Second Feed)
HELIUS_API_KEY = os.environ.get("HELIUS_API_KEY", "793ee1a9-6bef-48b2-bfa9-f0270ad46857")
HELIUS_RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}" if HELIUS_API_KEY else ""
HELIUS_WS_URL = f"wss://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}" if HELIUS_API_KEY else ""
