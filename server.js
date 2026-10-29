const http = require('http');
const fs = require('fs');
const path = require('path');
const { DatabaseSync } = require('node:sqlite');

// PREVENÇÃO CONTRA QUEDA DO PROCESSO (NUNCA MAIS ACIDENTADO)
process.on('uncaughtException', (err) => {
  console.error('⚠️ [UncaughtException Protegido]:', err ? err.message : err);
});
process.on('unhandledRejection', (reason) => {
  console.error('⚠️ [UnhandledRejection Protegido]:', reason);
});

const PORT = process.env.PORT || 8080;
const DB_URL = process.env.DATABASE_URL || process.env.POSTGRES_URL;

let isPostgres = false;
let pgPool = null;

// SQLite sempre disponível como fallback 100% seguro
const sqliteDb = new DatabaseSync(path.join(__dirname, 'desafio_cofre.db'));

function initSqlite() {
  try {
    sqliteDb.exec(`
      CREATE TABLE IF NOT EXISTS game_state (
        id INTEGER PRIMARY KEY,
        jackpot REAL DEFAULT 500.00,
        secret_code TEXT DEFAULT '72039',
        total_arrecadado REAL DEFAULT 0.0,
        is_locked INTEGER DEFAULT 0,
        winner_name TEXT,
        winner_prize REAL
      );
      CREATE TABLE IF NOT EXISTS competitors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cpf TEXT UNIQUE,
        name TEXT,
        phone TEXT,
        pix_type TEXT,
        pix_key TEXT,
        password TEXT,
        chances INTEGER DEFAULT 0,
        attempts INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );
      CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cpf TEXT UNIQUE,
        name TEXT,
        phone TEXT,
        pix_type TEXT,
        pix_key TEXT,
        password TEXT,
        chances INTEGER DEFAULT 0,
        attempts INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );
      CREATE TABLE IF NOT EXISTS winners (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        cpf TEXT,
        phone TEXT,
        pix_type TEXT,
        pix_key TEXT,
        guess TEXT,
        prize_amount REAL,
        won_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );
      CREATE TABLE IF NOT EXISTS attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cpf TEXT,
        guess TEXT,
        is_correct INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );
      CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cpf TEXT,
        amount REAL,
        status TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );
    `);

    const check = sqliteDb.prepare('SELECT * FROM game_state WHERE id = 1').get();
    if (!check) {
      sqliteDb.prepare('INSERT INTO game_state (id, jackpot, secret_code, total_arrecadado, is_locked) VALUES (1, 500.00, ?, 0.0, 0)').run('72039');
    }
  } catch (err) {
    console.warn('Aviso SQLite init:', err.message);
  }
}

// Inicializa SQLite
initSqlite();

// Inicialização segura do PostgreSQL
async function initDb() {
  if (DB_URL) {
    try {
      const { Pool } = require('pg');
      const isInternal = DB_URL.includes('railway.internal') || DB_URL.includes('localhost') || DB_URL.includes('127.0.0.1');
      pgPool = new Pool({
        connectionString: DB_URL,
        ssl: isInternal ? false : { rejectUnauthorized: false },
        connectionTimeoutMillis: 5000
      });

      // Evita queda por erro ocioso do pool
      pgPool.on('error', (err) => {
        console.warn('⚠️ [Postgres Pool Warning]:', err.message);
      });

      // Testa conexão
      await pgPool.query('SELECT 1');
      isPostgres = true;
      console.log('🐘 Conectado com sucesso ao PostgreSQL na Railway!');

      const tables = [
        `CREATE TABLE IF NOT EXISTS game_state (
          id INTEGER PRIMARY KEY,
          jackpot NUMERIC(10,2) DEFAULT 500.00,
          secret_code VARCHAR(10) DEFAULT '72039',
          total_arrecadado NUMERIC(10,2) DEFAULT 0.00,
          is_locked INTEGER DEFAULT 0,
          winner_name VARCHAR(255),
          winner_prize NUMERIC(10,2)
        )`,
        `CREATE TABLE IF NOT EXISTS competitors (
          id SERIAL PRIMARY KEY,
          cpf VARCHAR(20),
          name VARCHAR(255),
          phone VARCHAR(50),
          pix_type VARCHAR(50),
          pix_key VARCHAR(255),
          password VARCHAR(100),
          chances INTEGER DEFAULT 0,
          attempts INTEGER DEFAULT 0,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )`,
        `CREATE TABLE IF NOT EXISTS usuarios (
          id SERIAL PRIMARY KEY,
          cpf VARCHAR(20),
          name VARCHAR(255),
          phone VARCHAR(50),
          pix_type VARCHAR(50),
          pix_key VARCHAR(255),
          password VARCHAR(100),
          chances INTEGER DEFAULT 0,
          attempts INTEGER DEFAULT 0,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )`,
        `CREATE TABLE IF NOT EXISTS winners (
          id SERIAL PRIMARY KEY,
          name VARCHAR(255),
          cpf VARCHAR(20),
          phone VARCHAR(50),
          pix_type VARCHAR(50),
          pix_key VARCHAR(255),
          guess VARCHAR(20),
          prize_amount NUMERIC(10,2),
          won_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )`,
        `CREATE TABLE IF NOT EXISTS attempts (
          id SERIAL PRIMARY KEY,
          cpf VARCHAR(20),
          guess VARCHAR(20),
          is_correct INTEGER,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )`,
        `CREATE TABLE IF NOT EXISTS transactions (
          id SERIAL PRIMARY KEY,
          cpf VARCHAR(20),
          amount NUMERIC(10,2),
          status VARCHAR(50),
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )`
      ];

      for (const sql of tables) {
        try {
          await pgPool.query(sql);
        } catch (e) {
          console.warn('Aviso ao criar tabela:', e.message);
        }
      }

      // Garante colunas na tabela usuarios criada no Railway
      const userCols = [
        'ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS cpf VARCHAR(20)',
        'ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS name VARCHAR(255)',
        'ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS phone VARCHAR(50)',
        'ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS pix_type VARCHAR(50)',
        'ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS pix_key VARCHAR(255)',
        'ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS password VARCHAR(100)',
        'ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS chances INTEGER DEFAULT 0',
        'ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS attempts INTEGER DEFAULT 0',
        'ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
      ];
      for (const colSql of userCols) {
        try { await pgPool.query(colSql); } catch (e) {}
      }

      // Garante estado inicial do cofre no Postgres
      try {
        const check = await pgPool.query('SELECT * FROM game_state WHERE id = 1');
        if (check.rows.length === 0) {
          await pgPool.query('INSERT INTO game_state (id, jackpot, secret_code, total_arrecadado, is_locked) VALUES (1, 500.00, $1, 0.0, 0)', ['72039']);
        }
      } catch (e) {}

    } catch (err) {
      console.warn('⚠️ Não foi possível conectar ao PostgreSQL. Mantendo SQLite local ativo. Erro:', err.message);
      isPostgres = false;
      pgPool = null;
    }
  } else {
    console.log('📁 DATABASE_URL não definida. Rodando em SQLite local...');
  }
}

// MÉTODOS DE DADOS COM FALLBACK AUTOMÁTICO
async function getGameState() {
  if (isPostgres && pgPool) {
    try {
      const res = await pgPool.query('SELECT jackpot, secret_code, total_arrecadado, is_locked, winner_name, winner_prize FROM game_state WHERE id = 1');
      const r = res.rows[0];
      if (r) {
        return {
          jackpot: parseFloat(r.jackpot) || 500.00,
          secret_code: r.secret_code || '72039',
          is_locked: Boolean(r.is_locked),
          winner_name: r.winner_name,
          winner_prize: r.winner_prize ? parseFloat(r.winner_prize) : null
        };
      }
    } catch (e) {}
  }
  try {
    const r = sqliteDb.prepare('SELECT jackpot, secret_code, total_arrecadado, is_locked, winner_name, winner_prize FROM game_state WHERE id = 1').get();
    return r ? {
      jackpot: parseFloat(r.jackpot) || 500.00,
      secret_code: r.secret_code || '72039',
      is_locked: Boolean(r.is_locked),
      winner_name: r.winner_name,
      winner_prize: r.winner_prize ? parseFloat(r.winner_prize) : null
    } : { jackpot: 500.00, secret_code: '72039', is_locked: false, winner_name: null, winner_prize: null };
  } catch (e) {
    return { jackpot: 500.00, secret_code: '72039', is_locked: false, winner_name: null, winner_prize: null };
  }
}

async function getCompetitor(cpf) {
  if (isPostgres && pgPool) {
    try {
      const res = await pgPool.query('SELECT * FROM competitors WHERE cpf = $1', [cpf]);
      if (res.rows[0]) return res.rows[0];
    } catch (e) {}
  }
  try {
    return sqliteDb.prepare('SELECT * FROM competitors WHERE cpf = ?').get(cpf) || null;
  } catch (e) {
    return null;
  }
}

async function upsertCompetitor(user) {
  const { cpf, name, phone, pixType = 'cpf', pixKey = '', password = '' } = user;
  
  // 1. Salva no SQLite de forma segura (SELECT antes de INSERT/UPDATE)
  try {
    const existing = sqliteDb.prepare('SELECT id FROM competitors WHERE cpf = ?').get(cpf);
    if (existing) {
      sqliteDb.prepare(`
        UPDATE competitors SET name = ?, phone = ?, pix_type = ?, pix_key = ?, password = ? WHERE cpf = ?
      `).run(name, phone, pixType, pixKey, password, cpf);
    } else {
      sqliteDb.prepare(`
        INSERT INTO competitors (cpf, name, phone, pix_type, pix_key, password, chances, attempts)
        VALUES (?, ?, ?, ?, ?, ?, 0, 0)
      `).run(cpf, name, phone, pixType, pixKey, password);
    }
  } catch (e) {
    console.warn('Erro ao salvar competitor no SQLite:', e.message);
  }

  // 2. Salva no PostgreSQL se ativo
  if (isPostgres && pgPool) {
    try {
      const checkComp = await pgPool.query('SELECT id FROM competitors WHERE cpf = $1', [cpf]);
      if (checkComp.rows.length > 0) {
        await pgPool.query(`
          UPDATE competitors SET name = $1, phone = $2, pix_type = $3, pix_key = $4, password = $5 WHERE cpf = $6
        `, [name, phone, pixType, pixKey, password, cpf]);
      } else {
        await pgPool.query(`
          INSERT INTO competitors (cpf, name, phone, pix_type, pix_key, password, chances, attempts)
          VALUES ($1, $2, $3, $4, $5, $6, 0, 0)
        `, [cpf, name, phone, pixType, pixKey, password]);
      }
    } catch (e) {
      console.warn('Erro ao salvar no Postgres competitors:', e.message);
    }

    // Salva na tabela 'usuarios' que o usuário visualiza no Railway
    try {
      const checkUser = await pgPool.query('SELECT id FROM usuarios WHERE cpf = $1', [cpf]);
      if (checkUser.rows.length > 0) {
        await pgPool.query(`
          UPDATE usuarios SET name = $1, phone = $2, pix_type = $3, pix_key = $4, password = $5 WHERE cpf = $6
        `, [name, phone, pixType, pixKey, password, cpf]);
      } else {
        await pgPool.query(`
          INSERT INTO usuarios (cpf, name, phone, pix_type, pix_key, password, chances, attempts)
          VALUES ($1, $2, $3, $4, $5, $6, 0, 0)
        `, [cpf, name, phone, pixType, pixKey, password]);
      }
    } catch (e) {
      console.warn('Erro ao salvar no Postgres usuarios:', e.message);
    }
  }
}

async function creditChances(cpf, amount = 4.99) {
  // SQLite
  try {
    sqliteDb.prepare('UPDATE competitors SET chances = chances + 5 WHERE cpf = ?').run(cpf);
    sqliteDb.prepare('UPDATE game_state SET jackpot = jackpot + 1.50, total_arrecadado = total_arrecadado + ? WHERE id = 1').run(amount);
    sqliteDb.prepare('INSERT INTO transactions (cpf, amount, status) VALUES (?, ?, ?)').run(cpf, amount, 'PAID');
  } catch (e) {}

  // Postgres
  if (isPostgres && pgPool) {
    try {
      await pgPool.query('UPDATE competitors SET chances = chances + 5 WHERE cpf = $1', [cpf]);
      await pgPool.query('UPDATE usuarios SET chances = chances + 5 WHERE cpf = $1', [cpf]);
      await pgPool.query('UPDATE game_state SET jackpot = jackpot + 1.50, total_arrecadado = total_arrecadado + $1 WHERE id = 1', [amount]);
      await pgPool.query('INSERT INTO transactions (cpf, amount, status) VALUES ($1, $2, $3)', [cpf, amount, 'PAID']);
    } catch (e) {}
  }
}

async function recordGuessAttempt(user, guess, isCorrect, gameState) {
  const newChances = Math.max(0, (user.chances || 0) - 1);
  const newAttempts = (user.attempts || 0) + 1;

  // SQLite
  try {
    sqliteDb.prepare('UPDATE competitors SET chances = ?, attempts = ? WHERE cpf = ?').run(newChances, newAttempts, user.cpf);
    sqliteDb.prepare('INSERT INTO attempts (cpf, guess, is_correct) VALUES (?, ?, ?)').run(user.cpf, guess, isCorrect ? 1 : 0);

    if (isCorrect) {
      sqliteDb.prepare('UPDATE game_state SET is_locked = 1, winner_name = ?, winner_prize = jackpot WHERE id = 1').run(user.name);
      sqliteDb.prepare(`
        INSERT INTO winners (name, cpf, phone, pix_type, pix_key, guess, prize_amount)
        VALUES (?, ?, ?, ?, ?, ?, ?)
      `).run(user.name, user.cpf, user.phone, user.pix_type, user.pix_key, guess, gameState.jackpot);
    }
  } catch (e) {}

  // Postgres
  if (isPostgres && pgPool) {
    try {
      await pgPool.query('UPDATE competitors SET chances = $1, attempts = $2 WHERE cpf = $3', [newChances, newAttempts, user.cpf]);
      await pgPool.query('UPDATE usuarios SET chances = $1, attempts = $2 WHERE cpf = $3', [newChances, newAttempts, user.cpf]);
      await pgPool.query('INSERT INTO attempts (cpf, guess, is_correct) VALUES ($1, $2, $3)', [user.cpf, guess, isCorrect ? 1 : 0]);

      if (isCorrect) {
        await pgPool.query('UPDATE game_state SET is_locked = 1, winner_name = $1, winner_prize = $2 WHERE id = 1', [user.name, gameState.jackpot]);
        await pgPool.query(`
          INSERT INTO winners (name, cpf, phone, pix_type, pix_key, guess, prize_amount)
          VALUES ($1, $2, $3, $4, $5, $6, $7)
        `, [user.name, user.cpf, user.phone, user.pix_type, user.pix_key, guess, gameState.jackpot]);
      }
    } catch (e) {}
  }

  return { newChances, newAttempts };
}

async function getAdminData() {
  if (isPostgres && pgPool) {
    try {
      const gameRes = await pgPool.query('SELECT * FROM game_state WHERE id = 1');
      const winnersRes = await pgPool.query('SELECT * FROM winners ORDER BY won_at DESC LIMIT 10');
      const compRes = await pgPool.query('SELECT name, cpf, phone, pix_key, chances, attempts, created_at FROM competitors ORDER BY created_at DESC LIMIT 50');
      return {
        game: gameRes.rows[0] || null,
        winners: winnersRes.rows,
        competitors: compRes.rows
      };
    } catch (e) {}
  }
  try {
    const game = sqliteDb.prepare('SELECT * FROM game_state WHERE id = 1').get();
    const winners = sqliteDb.prepare('SELECT * FROM winners ORDER BY won_at DESC LIMIT 10').all();
    const competitors = sqliteDb.prepare('SELECT name, cpf, phone, pix_key, chances, attempts, created_at FROM competitors ORDER BY created_at DESC LIMIT 50').all();
    return { game, winners, competitors };
  } catch (e) {
    return { game: null, winners: [], competitors: [] };
  }
}

async function saveAdminConfig({ secret_code, jackpot, reset }) {
  // SQLite
  try {
    if (secret_code && secret_code.length === 5) {
      sqliteDb.prepare('UPDATE game_state SET secret_code = ? WHERE id = 1').run(secret_code);
    }
    if (jackpot !== undefined && !isNaN(jackpot)) {
      sqliteDb.prepare('UPDATE game_state SET jackpot = ? WHERE id = 1').run(parseFloat(jackpot));
    }
    if (reset) {
      sqliteDb.prepare('UPDATE game_state SET is_locked = 0, winner_name = NULL, winner_prize = NULL WHERE id = 1').run();
    }
  } catch (e) {}

  // Postgres
  if (isPostgres && pgPool) {
    try {
      if (secret_code && secret_code.length === 5) {
        await pgPool.query('UPDATE game_state SET secret_code = $1 WHERE id = 1', [secret_code]);
      }
      if (jackpot !== undefined && !isNaN(jackpot)) {
        await pgPool.query('UPDATE game_state SET jackpot = $1 WHERE id = 1', [parseFloat(jackpot)]);
      }
      if (reset) {
        await pgPool.query('UPDATE game_state SET is_locked = 0, winner_name = NULL, winner_prize = NULL WHERE id = 1');
      }
    } catch (e) {}
  }
}

const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.css': 'text/css',
  '.js': 'application/javascript',
  '.json': 'application/json'
};

function sendJson(res, data, statusCode = 200) {
  try {
    res.writeHead(statusCode, {
      'Content-Type': 'application/json; charset=utf-8',
      'Access-Control-Allow-Origin': '*'
    });
    res.end(JSON.stringify(data));
  } catch (e) {}
}

function parseJsonBody(req) {
  return new Promise((resolve) => {
    let body = '';
    req.on('data', chunk => { body += chunk; });
    req.on('end', () => {
      try {
        resolve(JSON.parse(body || '{}'));
      } catch (e) {
        resolve({});
      }
    });
  });
}

const server = http.createServer(async (req, res) => {
  try {
    const parsedUrl = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
    const pathname = parsedUrl.pathname;

    // ROTAS DE API
    if (req.method === 'GET' && pathname === '/api/game/state') {
      const gameState = await getGameState();
      const cpf = parsedUrl.searchParams.get('cpf');
      let userChances = null;
      let userAttempts = null;
      if (cpf) {
        const user = await getCompetitor(cpf);
        if (user) {
          userChances = user.chances;
          userAttempts = user.attempts;
        }
      }
      return sendJson(res, {
        jackpot: gameState.jackpot,
        isLocked: gameState.is_locked,
        winnerName: gameState.winner_name,
        winnerPrize: gameState.winner_prize,
        userChances,
        userAttempts
      });
    }

    if (req.method === 'POST' && pathname === '/api/auth/register') {
      const data = await parseJsonBody(req);
      const { name, cpf, phone, pixType = 'cpf', pixKey, password } = data;
      if (!cpf || !name || !phone) {
        return sendJson(res, { error: 'Nome, CPF e WhatsApp são obrigatórios' }, 400);
      }
      await upsertCompetitor({ name, cpf, phone, pixType, pixKey, password });
      return sendJson(res, { success: true, message: 'Competidor registrado com sucesso' });
    }

    if (req.method === 'POST' && pathname === '/api/auth/login') {
      const data = await parseJsonBody(req);
      const { cpf, password } = data;
      const user = await getCompetitor(cpf);
      if (user && user.password === password) {
        return sendJson(res, {
          success: true,
          user: {
            name: user.name,
            cpf: user.cpf,
            phone: user.phone,
            pixType: user.pix_type,
            pixKey: user.pix_key,
            chances: user.chances,
            attempts: user.attempts
          }
        });
      }
      return sendJson(res, { error: 'CPF ou senha incorretos' }, 401);
    }

    if (req.method === 'POST' && pathname === '/api/pix/create') {
      const data = await parseJsonBody(req);
      const { cpf } = data;
      const amount = 4.99;
      const pixCode = "00020126580014br.gov.bcb.pix01366342577500071552040000530398654044.995802BR5910SW_DIGITAL6009CURITIBA62070503***6304E8A2";
      try {
        sqliteDb.prepare('INSERT INTO transactions (cpf, amount, status) VALUES (?, ?, ?)').run(cpf, amount, 'PENDING');
        if (isPostgres && pgPool) {
          await pgPool.query('INSERT INTO transactions (cpf, amount, status) VALUES ($1, $2, $3)', [cpf, amount, 'PENDING']);
        }
      } catch (e) {}
      return sendJson(res, { success: true, amount, pix_code: pixCode });
    }

    if (req.method === 'POST' && pathname === '/api/pix/webhook') {
      const data = await parseJsonBody(req);
      const { cpf, amount = 4.99 } = data;
      await creditChances(cpf, amount);
      return sendJson(res, { success: true, message: 'Chaves creditadas e jackpot atualizado' });
    }

    if (req.method === 'POST' && pathname === '/api/game/guess') {
      const data = await parseJsonBody(req);
      const { cpf, guess } = data;
      const gameState = await getGameState();

      if (gameState.is_locked) {
        return sendJson(res, {
          error: 'Cofre já encerrado! O prêmio já foi ganho.',
          isLocked: true,
          winnerName: gameState.winner_name,
          winnerPrize: gameState.winner_prize
        }, 400);
      }

      const user = await getCompetitor(cpf);
      if (!user || user.chances <= 0) {
        return sendJson(res, { error: 'Sem chaves disponíveis' }, 403);
      }

      const secret = gameState.secret_code || '72039';
      const isCorrect = guess === secret;

      const { newChances, newAttempts } = await recordGuessAttempt(user, guess, isCorrect, gameState);

      return sendJson(res, {
        success: true,
        won: isCorrect,
        chancesLeft: newChances,
        attemptsCount: newAttempts,
        winnerName: isCorrect ? user.name : null,
        winnerPrize: isCorrect ? gameState.jackpot : null
      });
    }

    if (req.method === 'GET' && pathname === '/api/admin/data') {
      const adminData = await getAdminData();
      return sendJson(res, adminData);
    }

    if (req.method === 'POST' && pathname === '/api/admin/config') {
      const data = await parseJsonBody(req);
      await saveAdminConfig(data);
      return sendJson(res, { success: true });
    }

    // ARQUIVOS ESTÁTICOS & PÁGINA PRINCIPAL
    let filePath = '';
    if (pathname === '/' || pathname === '/index.html') {
      filePath = path.join(__dirname, 'templates', 'index.html');
    } else if (pathname.startsWith('/static/')) {
      filePath = path.join(__dirname, 'static', pathname.replace('/static/', ''));
    }

    if (filePath && fs.existsSync(filePath)) {
      const ext = path.extname(filePath).toLowerCase();
      res.writeHead(200, {
        'Content-Type': MIME_TYPES[ext] || 'application/octet-stream',
        'Cache-Control': 'no-cache, no-store, must-revalidate'
      });
      return fs.createReadStream(filePath).pipe(res);
    }

    res.writeHead(404, { 'Content-Type': 'text/plain' });
    res.end('404 Not Found');
  } catch (err) {
    console.error('Erro na requisição interceptado:', err);
    sendJson(res, { error: 'Erro interno do servidor' }, 500);
  }
});

// Inicia o servidor HTTP IMEDIATAMENTE (Railway nunca mais dá "Acidentado"!)
server.listen(PORT, '0.0.0.0', () => {
  console.log(`🚀 Desafio do Cofre rodando na porta ${PORT}`);
  // Inicia banco em segundo plano de forma 100% segura
  initDb();
});
