const http = require('http');
const fs = require('fs');
const path = require('path');
const { DatabaseSync } = require('node:sqlite');

const PORT = process.env.PORT || 8080;
const DB_PATH = path.join(__dirname, 'desafio_cofre.db');

// Inicializa Banco de Dados SQLite Nativo
const db = new DatabaseSync(DB_PATH);

db.exec(`
  CREATE TABLE IF NOT EXISTS game_state (
    id INTEGER PRIMARY KEY,
    jackpot REAL,
    secret_code TEXT,
    total_arrecadado REAL
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

// Estado inicial
const stateCheck = db.prepare('SELECT * FROM game_state WHERE id = 1').get();
if (!stateCheck) {
  db.prepare('INSERT INTO game_state (id, jackpot, secret_code, total_arrecadado) VALUES (1, 3424.50, ?, 0.0)').run('72039');
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
  res.writeHead(statusCode, {
    'Content-Type': 'application/json; charset=utf-8',
    'Access-Control-Allow-Origin': '*'
  });
  res.end(JSON.stringify(data));
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
  const parsedUrl = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const pathname = parsedUrl.pathname;

  // ROTAS DE API
  if (req.method === 'GET' && pathname === '/api/game/state') {
    const row = db.prepare('SELECT jackpot FROM game_state WHERE id = 1').get();
    return sendJson(res, { jackpot: row ? row.jackpot : 3424.50 });
  }

  if (req.method === 'POST' && pathname === '/api/auth/register') {
    const data = await parseJsonBody(req);
    const { name, cpf, phone, pixType = 'cpf', pixKey, password } = data;
    if (!cpf || !name) {
      return sendJson(res, { error: 'Dados incompletos' }, 400);
    }
    db.prepare(`
      INSERT INTO competitors (cpf, name, phone, pix_type, pix_key, password, chances, attempts)
      VALUES (?, ?, ?, ?, ?, ?, 0, 0)
      ON CONFLICT(cpf) DO UPDATE SET
        name = excluded.name,
        phone = excluded.phone,
        pix_type = excluded.pix_type,
        pix_key = excluded.pix_key,
        password = excluded.password
    `).run(cpf, name, phone, pixType, pixKey, password);
    return sendJson(res, { success: true, message: 'Competidor registrado' });
  }

  if (req.method === 'POST' && pathname === '/api/auth/login') {
    const data = await parseJsonBody(req);
    const { cpf, password } = data;
    const user = db.prepare('SELECT * FROM competitors WHERE cpf = ?').get(cpf);
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
    db.prepare('INSERT INTO transactions (cpf, amount, status) VALUES (?, ?, ?)')
      .run(cpf, amount, 'PENDING');
    return sendJson(res, { success: true, amount, pix_code: pixCode });
  }

  if (req.method === 'POST' && pathname === '/api/pix/webhook') {
    const data = await parseJsonBody(req);
    const { cpf, amount = 4.99 } = data;
    db.prepare('UPDATE competitors SET chances = chances + 5 WHERE cpf = ?').run(cpf);
    db.prepare('UPDATE game_state SET jackpot = jackpot + 1.50, total_arrecadado = total_arrecadado + ? WHERE id = 1').run(amount);
    db.prepare('INSERT INTO transactions (cpf, amount, status) VALUES (?, ?, ?)')
      .run(cpf, amount, 'PAID');
    return sendJson(res, { success: true, message: 'Chaves creditadas e jackpot atualizado' });
  }

  if (req.method === 'POST' && pathname === '/api/game/guess') {
    const data = await parseJsonBody(req);
    const { cpf, guess } = data;
    const user = db.prepare('SELECT chances, attempts FROM competitors WHERE cpf = ?').get(cpf);
    if (!user || user.chances <= 0) {
      return sendJson(res, { error: 'Sem chaves disponíveis' }, 403);
    }
    const game = db.prepare('SELECT secret_code FROM game_state WHERE id = 1').get();
    const secret = game ? game.secret_code : '72039';

    const newChances = user.chances - 1;
    const newAttempts = user.attempts + 1;
    const isCorrect = guess === secret ? 1 : 0;

    db.prepare('UPDATE competitors SET chances = ?, attempts = ? WHERE cpf = ?').run(newChances, newAttempts, cpf);
    db.prepare('INSERT INTO attempts (cpf, guess, is_correct) VALUES (?, ?, ?)').run(cpf, guess, isCorrect);

    return sendJson(res, {
      success: true,
      won: Boolean(isCorrect),
      chancesLeft: newChances,
      attemptsCount: newAttempts
    });
  }

  if (req.method === 'POST' && pathname === '/api/admin/config') {
    const data = await parseJsonBody(req);
    const { secret_code, jackpot } = data;
    if (secret_code && secret_code.length === 5) {
      db.prepare('UPDATE game_state SET secret_code = ? WHERE id = 1').run(secret_code);
    }
    if (jackpot !== undefined && !isNaN(jackpot)) {
      db.prepare('UPDATE game_state SET jackpot = ? WHERE id = 1').run(parseFloat(jackpot));
    }
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
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`🚀 Desafio do Cofre rodando na porta ${PORT}`);
});
