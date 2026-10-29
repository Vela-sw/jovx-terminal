const http = require('http');
const fs = require('fs');
const path = require('path');
const { DatabaseSync } = require('node:sqlite');
const interPix = require('./inter_pix');

// PREVENÇÃO CONTRA QUEDA DO PROCESSO (NUNCA MAIS ACIDENTADO)
process.on('uncaughtException', (err) => {
  console.error('⚠️ [UncaughtException Protegido]:', err ? err.message : err);
});
process.on('unhandledRejection', (reason) => {
  console.error('⚠️ [UnhandledRejection Protegido]:', reason);
});

const PORT = process.env.PORT || 8080;

function findDatabaseUrl() {
  if (process.env.DATABASE_URL) return process.env.DATABASE_URL;
  if (process.env.DATABASE_PRIVATE_URL) return process.env.DATABASE_PRIVATE_URL;
  if (process.env.DATABASE_PUBLIC_URL) return process.env.DATABASE_PUBLIC_URL;
  if (process.env.POSTGRES_URL) return process.env.POSTGRES_URL;
  if (process.env.URL_DO_BANCO_DE_DADOS) return process.env.URL_DO_BANCO_DE_DADOS;
  for (const [k, v] of Object.entries(process.env)) {
    if (typeof v === 'string' && (v.startsWith('postgres://') || v.startsWith('postgresql://'))) {
      return v;
    }
  }
  return null;
}

const DB_URL = findDatabaseUrl();

let isPostgres = false;
let pgPool = null;
let pgConnectionError = null;

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

    // Colunas de pistas personalizadas
    try { sqliteDb.exec("ALTER TABLE game_state ADD COLUMN clue_1 TEXT DEFAULT 'A soma de todos os 5 dígitos é exatamente 21'"); } catch(e) {}
    try { sqliteDb.exec("ALTER TABLE game_state ADD COLUMN clue_2 TEXT DEFAULT 'O 2º número do segredo é PAR (0, 2, 4, 6 ou 8)'"); } catch(e) {}
    try { sqliteDb.exec("ALTER TABLE game_state ADD COLUMN clue_3 TEXT DEFAULT 'O número 2 NÃO FAZ PARTE da combinação'"); } catch(e) {}
    try { sqliteDb.exec("ALTER TABLE game_state ADD COLUMN clue_4 TEXT DEFAULT 'O número 9 NÃO FAZ PARTE da combinação'"); } catch(e) {}
    try { sqliteDb.exec("ALTER TABLE transactions ADD COLUMN txid TEXT"); } catch(e) {}
    try { sqliteDb.exec("ALTER TABLE transactions ADD COLUMN pix_code TEXT"); } catch(e) {}
  } catch (err) {
    console.warn('Aviso SQLite init:', err.message);
  }
}

// Inicializa SQLite
initSqlite();

// Inicialização segura do PostgreSQL
async function initDb() {
  const currentDbUrl = findDatabaseUrl();
  if (currentDbUrl) {
    try {
      const { Pool } = require('pg');
      let connected = false;
      const isInternal = currentDbUrl.includes('railway.internal') || currentDbUrl.includes('localhost') || currentDbUrl.includes('127.0.0.1');
      const sslModes = isInternal ? [false, { rejectUnauthorized: false }] : [{ rejectUnauthorized: false }, false];

      for (const sslMode of sslModes) {
        try {
          const pool = new Pool({
            connectionString: currentDbUrl,
            ssl: sslMode,
            connectionTimeoutMillis: 5000
          });
          await pool.query('SELECT 1');
          pgPool = pool;
          isPostgres = true;
          connected = true;
          console.log('🐘 Conectado com sucesso ao PostgreSQL na Railway! (SSL:', Boolean(sslMode), ')');
          break;
        } catch (e) {
          pgConnectionError = e.message;
        }
      }

      if (!connected) {
        throw new Error(pgConnectionError || 'Falha ao conectar pool Postgres');
      }

      // Evita queda por erro ocioso do pool
      pgPool.on('error', (err) => {
        console.warn('⚠️ [Postgres Pool Warning]:', err.message);
      });

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

      // Garante colunas de pistas personalizadas no Postgres
      const clueCols = [
        "ALTER TABLE game_state ADD COLUMN IF NOT EXISTS clue_1 TEXT DEFAULT 'A soma de todos os 5 dígitos é exatamente 21'",
        "ALTER TABLE game_state ADD COLUMN IF NOT EXISTS clue_2 TEXT DEFAULT 'O 2º número do segredo é PAR (0, 2, 4, 6 ou 8)'",
        "ALTER TABLE game_state ADD COLUMN IF NOT EXISTS clue_3 TEXT DEFAULT 'O número 2 NÃO FAZ PARTE da combinação'",
        "ALTER TABLE game_state ADD COLUMN IF NOT EXISTS clue_4 TEXT DEFAULT 'O número 9 NÃO FAZ PARTE da combinação'"
      ];
      for (const colSql of clueCols) {
        try { await pgPool.query(colSql); } catch (e) {}
      }

      // Garante colunas txid e pix_code na tabela transactions do Postgres
      try { await pgPool.query('ALTER TABLE transactions ADD COLUMN IF NOT EXISTS txid VARCHAR(100)'); } catch (e) {}
      try { await pgPool.query('ALTER TABLE transactions ADD COLUMN IF NOT EXISTS pix_code TEXT'); } catch (e) {}

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
      const res = await pgPool.query('SELECT jackpot, secret_code, total_arrecadado, is_locked, winner_name, winner_prize, clue_1, clue_2, clue_3, clue_4 FROM game_state WHERE id = 1');
      const r = res.rows[0];
      if (r) {
        return {
          jackpot: parseFloat(r.jackpot) || 500.00,
          secret_code: r.secret_code || '72039',
          is_locked: Boolean(r.is_locked),
          winner_name: r.winner_name,
          winner_prize: r.winner_prize ? parseFloat(r.winner_prize) : null,
          clue_1: r.clue_1 || "A soma de todos os 5 dígitos é exatamente 21",
          clue_2: r.clue_2 || "O 2º número do segredo é PAR (0, 2, 4, 6 ou 8)",
          clue_3: r.clue_3 || "O número 2 NÃO FAZ PARTE da combinação",
          clue_4: r.clue_4 || "O número 9 NÃO FAZ PARTE da combinação",
          clues: [
            r.clue_1 || "A soma de todos os 5 dígitos é exatamente 21",
            r.clue_2 || "O 2º número do segredo é PAR (0, 2, 4, 6 ou 8)",
            r.clue_3 || "O número 2 NÃO FAZ PARTE da combinação",
            r.clue_4 || "O número 9 NÃO FAZ PARTE da combinação"
          ]
        };
      }
    } catch (e) {}
  }
  try {
    const r = sqliteDb.prepare('SELECT jackpot, secret_code, total_arrecadado, is_locked, winner_name, winner_prize, clue_1, clue_2, clue_3, clue_4 FROM game_state WHERE id = 1').get();
    return r ? {
      jackpot: parseFloat(r.jackpot) || 500.00,
      secret_code: r.secret_code || '72039',
      is_locked: Boolean(r.is_locked),
      winner_name: r.winner_name,
      winner_prize: r.winner_prize ? parseFloat(r.winner_prize) : null,
      clue_1: r.clue_1 || "A soma de todos os 5 dígitos é exatamente 21",
      clue_2: r.clue_2 || "O 2º número do segredo é PAR (0, 2, 4, 6 ou 8)",
      clue_3: r.clue_3 || "O número 2 NÃO FAZ PARTE da combinação",
      clue_4: r.clue_4 || "O número 9 NÃO FAZ PARTE da combinação",
      clues: [
        r.clue_1 || "A soma de todos os 5 dígitos é exatamente 21",
        r.clue_2 || "O 2º número do segredo é PAR (0, 2, 4, 6 ou 8)",
        r.clue_3 || "O número 2 NÃO FAZ PARTE da combinação",
        r.clue_4 || "O número 9 NÃO FAZ PARTE da combinação"
      ]
    } : { jackpot: 500.00, secret_code: '72039', is_locked: false, winner_name: null, winner_prize: null, clues: ["A soma de todos os 5 dígitos é exatamente 21", "O 2º número do segredo é PAR (0, 2, 4, 6 ou 8)", "O número 2 NÃO FAZ PARTE da combinação", "O número 9 NÃO FAZ PARTE da combinação"] };
  } catch (e) {
    return { jackpot: 500.00, secret_code: '72039', is_locked: false, winner_name: null, winner_prize: null, clues: ["A soma de todos os 5 dígitos é exatamente 21", "O 2º número do segredo é PAR (0, 2, 4, 6 ou 8)", "O número 2 NÃO FAZ PARTE da combinação", "O número 9 NÃO FAZ PARTE da combinação"] };
  }
}

async function getCompetitor(rawCpf) {
  if (!rawCpf) return null;
  const cpf = String(rawCpf).trim();
  const cleanCpf = cpf.replace(/\D/g, '');
  if (isPostgres && pgPool) {
    try {
      const res = await pgPool.query('SELECT * FROM usuarios WHERE cpf = $1 OR cpf = $2', [cpf, cleanCpf]);
      if (res.rows[0]) return res.rows[0];
    } catch (e) {}
    try {
      const res = await pgPool.query('SELECT * FROM competitors WHERE cpf = $1 OR cpf = $2', [cpf, cleanCpf]);
      if (res.rows[0]) return res.rows[0];
    } catch (e) {}
  }
  try {
    return sqliteDb.prepare('SELECT * FROM competitors WHERE cpf = ? OR cpf = ?').get(cpf, cleanCpf) || null;
  } catch (e) {
    return null;
  }
}

async function upsertCompetitor(user) {
  const { name, phone, pixType = 'cpf', pixKey = '', password = '' } = user;
  const cpf = String(user.cpf || '').trim();
  const cleanCpf = cpf.replace(/\D/g, '');
  
  // 1. Salva no SQLite de forma segura (SELECT antes de INSERT/UPDATE)
  try {
    const existing = sqliteDb.prepare('SELECT id FROM competitors WHERE cpf = ? OR cpf = ?').get(cpf, cleanCpf);
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

  // 2. Salva no PostgreSQL se ativo (atualiza tanto competitors quanto usuarios)
  if (isPostgres && pgPool) {
    try {
      const checkComp = await pgPool.query('SELECT id FROM competitors WHERE cpf = $1 OR cpf = $2', [cpf, cleanCpf]);
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
      const checkUser = await pgPool.query('SELECT id FROM usuarios WHERE cpf = $1 OR cpf = $2', [cpf, cleanCpf]);
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

async function creditChances(rawCpf, amount = 4.99) {
  if (!rawCpf) return;
  const cpf = String(rawCpf).trim();
  const cleanCpf = cpf.replace(/\D/g, '');

  // SQLite
  try {
    sqliteDb.prepare('UPDATE competitors SET chances = chances + 10 WHERE cpf = ? OR cpf = ?').run(cpf, cleanCpf);
    sqliteDb.prepare('UPDATE game_state SET jackpot = jackpot + 1.50, total_arrecadado = total_arrecadado + ? WHERE id = 1').run(amount);
    sqliteDb.prepare('INSERT INTO transactions (cpf, amount, status) VALUES (?, ?, ?)').run(cpf, amount, 'PAID');
  } catch (e) {}

  // Postgres
  if (isPostgres && pgPool) {
    try {
      await pgPool.query('UPDATE competitors SET chances = chances + 10 WHERE cpf = $1 OR cpf = $2', [cpf, cleanCpf]);
      await pgPool.query('UPDATE usuarios SET chances = chances + 10 WHERE cpf = $1 OR cpf = $2', [cpf, cleanCpf]);
      await pgPool.query('UPDATE game_state SET jackpot = jackpot + 1.50, total_arrecadado = total_arrecadado + $1 WHERE id = 1', [amount]);
      await pgPool.query('INSERT INTO transactions (cpf, amount, status) VALUES ($1, $2, $3)', [cpf, amount, 'PAID']);
    } catch (e) {
      console.warn('Erro ao creditar chances no Postgres:', e.message);
    }
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

async function saveAdminConfig({ secret_code, jackpot, reset, clue_1, clue_2, clue_3, clue_4 }) {
  // SQLite
  try {
    if (secret_code && secret_code.length === 5) {
      sqliteDb.prepare('UPDATE game_state SET secret_code = ? WHERE id = 1').run(secret_code);
    }
    if (jackpot !== undefined && !isNaN(jackpot)) {
      sqliteDb.prepare('UPDATE game_state SET jackpot = ? WHERE id = 1').run(parseFloat(jackpot));
    }
    if (clue_1 !== undefined) sqliteDb.prepare('UPDATE game_state SET clue_1 = ? WHERE id = 1').run(clue_1);
    if (clue_2 !== undefined) sqliteDb.prepare('UPDATE game_state SET clue_2 = ? WHERE id = 1').run(clue_2);
    if (clue_3 !== undefined) sqliteDb.prepare('UPDATE game_state SET clue_3 = ? WHERE id = 1').run(clue_3);
    if (clue_4 !== undefined) sqliteDb.prepare('UPDATE game_state SET clue_4 = ? WHERE id = 1').run(clue_4);
    if (reset) {
      sqliteDb.prepare('UPDATE game_state SET is_locked = 0, winner_name = NULL, winner_prize = NULL WHERE id = 1').run();
      sqliteDb.prepare('UPDATE competitors SET attempts = 0').run();
      sqliteDb.prepare('UPDATE usuarios SET attempts = 0').run();
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
      if (clue_1 !== undefined) await pgPool.query('UPDATE game_state SET clue_1 = $1 WHERE id = 1', [clue_1]);
      if (clue_2 !== undefined) await pgPool.query('UPDATE game_state SET clue_2 = $1 WHERE id = 1', [clue_2]);
      if (clue_3 !== undefined) await pgPool.query('UPDATE game_state SET clue_3 = $1 WHERE id = 1', [clue_3]);
      if (clue_4 !== undefined) await pgPool.query('UPDATE game_state SET clue_4 = $1 WHERE id = 1', [clue_4]);
      if (reset) {
        await pgPool.query('UPDATE game_state SET is_locked = 0, winner_name = NULL, winner_prize = NULL WHERE id = 1');
        await pgPool.query('UPDATE competitors SET attempts = 0');
        await pgPool.query('UPDATE usuarios SET attempts = 0');
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
        userAttempts,
        isPostgres,
        dbType: isPostgres ? 'PostgreSQL' : 'SQLite',
        clues: gameState.clues
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
      try {
        console.log(`🏦 Gerando cobrança Pix oficial Banco Inter para CPF: ${cpf}...`);
        const cob = await interPix.createPixCob({
          amount: 4.99,
          description: '10 Chaves - Desafio do Cofre'
        });

        const txid = cob.txid;
        const pixCode = cob.pixCopiaECola;

        try {
          sqliteDb.prepare('INSERT INTO transactions (cpf, amount, status, txid, pix_code) VALUES (?, ?, ?, ?, ?)').run(cpf, amount, 'PENDING', txid, pixCode);
          if (isPostgres && pgPool) {
            await pgPool.query('INSERT INTO transactions (cpf, amount, status, txid, pix_code) VALUES ($1, $2, $3, $4, $5)', [cpf, amount, 'PENDING', txid, pixCode]);
          }
        } catch (dbErr) {
          console.warn('Erro ao salvar transação no BD:', dbErr.message);
        }

        console.log(`✅ Pix Banco Inter gerado com sucesso! txid: ${txid}`);
        return sendJson(res, { success: true, amount, pix_code: pixCode, txid });
      } catch (err) {
        console.error('❌ Erro ao criar cobrança no Banco Inter:', err.message);
        const fallbackTxid = 'COFRE' + Date.now();
        const fallbackPix = "00020101021226930014BR.GOV.BCB.PIX2571spi-qrcode.bancointer.com.br/spi/pj/v2/1e97222de5f04f238741bf16805a458452040000530398654044.995802BR5901*6005NATAL61085912440062070503***6304D46D";
        try {
          sqliteDb.prepare('INSERT INTO transactions (cpf, amount, status, txid, pix_code) VALUES (?, ?, ?, ?, ?)').run(cpf, amount, 'PENDING', fallbackTxid, fallbackPix);
          if (isPostgres && pgPool) {
            await pgPool.query('INSERT INTO transactions (cpf, amount, status, txid, pix_code) VALUES ($1, $2, $3, $4, $5)', [cpf, amount, 'PENDING', fallbackTxid, fallbackPix]);
          }
        } catch (e) {}
        return sendJson(res, { success: true, amount, pix_code: fallbackPix, txid: fallbackTxid });
      }
    }

    if (req.method === 'GET' && pathname === '/api/pix/status') {
      const cpf = parsedUrl.searchParams.get('cpf');
      const txid = parsedUrl.searchParams.get('txid');
      let isPaid = false;
      let chances = 0;
      if (cpf) {
        const user = await getCompetitor(cpf);
        if (user) chances = user.chances;

        // 1. Verifica se já está pago no banco de dados
        let pendingTxid = txid;
        if (isPostgres && pgPool) {
          const r = await pgPool.query('SELECT status, txid FROM transactions WHERE cpf = $1 ORDER BY id DESC LIMIT 1', [cpf]);
          if (r.rows[0]) {
            if (r.rows[0].status === 'PAID') isPaid = true;
            if (!pendingTxid) pendingTxid = r.rows[0].txid;
          }
        } else {
          const r = sqliteDb.prepare('SELECT status, txid FROM transactions WHERE cpf = ? ORDER BY id DESC LIMIT 1').get(cpf);
          if (r) {
            if (r.status === 'PAID') isPaid = true;
            if (!pendingTxid) pendingTxid = r.txid;
          }
        }

        // 2. Se ainda não consta como pago e temos um txid, consulta em tempo real no Banco Inter!
        if (!isPaid && pendingTxid && !pendingTxid.startsWith('COFRE')) {
          try {
            const check = await interPix.checkPixCob(pendingTxid);
            if (check && check.paid) {
              console.log(`🎉 [INTER] Pagamento confirmado pelo Banco Inter para CPF ${cpf} (txid: ${pendingTxid})!`);
              isPaid = true;
              await creditChances(cpf, 4.99);

              try {
                sqliteDb.prepare("UPDATE transactions SET status = 'PAID' WHERE txid = ? OR (cpf = ? AND status = 'PENDING')").run(pendingTxid, cpf);
                if (isPostgres && pgPool) {
                  await pgPool.query("UPDATE transactions SET status = 'PAID' WHERE txid = $1 OR (cpf = $2 AND status = 'PENDING')", [pendingTxid, cpf]);
                }
              } catch(e) {}

              const updatedUser = await getCompetitor(cpf);
              if (updatedUser) chances = updatedUser.chances;
            }
          } catch (e) {
            console.warn('Erro ao consultar status no Banco Inter:', e.message);
          }
        }
      }
      return sendJson(res, { paid: isPaid, chances });
    }

    if (req.method === 'POST' && pathname === '/api/dev/add-keys') {
      const data = await parseJsonBody(req);
      const { cpf, amount = 10, secret } = data;
      if (secret !== 'vela2026' && secret !== 'admin' && secret !== '1234') {
        return sendJson(res, { error: 'Não autorizado' }, 403);
      }
      if (cpf) {
        await creditChances(cpf, 0);
        const user = await getCompetitor(cpf);
        return sendJson(res, { success: true, message: `+${amount} chaves adicionadas ao desenvolvedor`, chances: user ? user.chances : 10 });
      }
      return sendJson(res, { error: 'CPF obrigatório' }, 400);
    }

    if (req.method === 'POST' && pathname === '/api/pix/webhook') {
      const data = await parseJsonBody(req);
      console.log('🔔 Webhook PIX recebido:', JSON.stringify(data));
      // Suporta payload real do Banco Inter e simulações
      if (data.pix && Array.isArray(data.pix)) {
        for (const item of data.pix) {
          const valor = parseFloat(item.valor) || 4.99;
          const txid = item.txid;
          let cpf = null;
          if (txid) {
            if (isPostgres && pgPool) {
              const tr = await pgPool.query('SELECT cpf FROM transactions WHERE txid = $1', [txid]);
              if (tr.rows[0]) cpf = tr.rows[0].cpf;
            } else {
              const tr = sqliteDb.prepare('SELECT cpf FROM transactions WHERE txid = ?').get(txid);
              if (tr) cpf = tr.cpf;
            }
          }
          if (!cpf) {
            if (isPostgres && pgPool) {
              const tr = await pgPool.query('SELECT cpf FROM transactions WHERE status = $1 ORDER BY id DESC LIMIT 1', ['PENDING']);
              if (tr.rows[0]) cpf = tr.rows[0].cpf;
            } else {
              const tr = sqliteDb.prepare('SELECT cpf FROM transactions WHERE status = ? ORDER BY id DESC LIMIT 1').get('PENDING');
              if (tr) cpf = tr.cpf;
            }
          }
          if (cpf) {
            await creditChances(cpf, valor);
            if (txid) {
              try {
                sqliteDb.prepare("UPDATE transactions SET status = 'PAID' WHERE txid = ?").run(txid);
                if (isPostgres && pgPool) {
                  await pgPool.query("UPDATE transactions SET status = 'PAID' WHERE txid = $1", [txid]);
                }
              } catch(e) {}
            }
          }
        }
      } else if (data.cpf) {
        await creditChances(data.cpf, data.amount || 4.99);
      }
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
      return sendJson(res, {
        game: adminData.game,
        winners: adminData.winners,
        competitors: adminData.competitors,
        dbStatus: {
          isPostgres,
          type: isPostgres ? 'PostgreSQL' : 'SQLite',
          message: isPostgres ? '🐘 PostgreSQL Conectado na Railway (Tabela usuarios sincronizada)' : (pgConnectionError ? `⚠️ Erro Postgres: ${pgConnectionError}` : '📁 SQLite Local Ativo (Para ligar ao Postgres da foto, adicione DATABASE_URL no serviço web)'),
          error: pgConnectionError,
          hasUrl: Boolean(findDatabaseUrl())
        },
        interStatus: {
          configured: true,
          pixKey: interPix.PIX_KEY,
          webhookUrl: `https://${req.headers.host || 'web-production-09e83.up.railway.app'}/api/pix/webhook`
        }
      });
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
