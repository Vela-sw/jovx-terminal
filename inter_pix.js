const https = require('https');
const fs = require('fs');
const path = require('path');
const querystring = require('querystring');

const CLIENT_ID = process.env.INTER_CLIENT_ID || '6eb53c2e-4991-4d5f-91d3-232bedca0c02';
const CLIENT_SECRET = process.env.INTER_CLIENT_SECRET || '19e34b0c-7e36-4378-922c-1db1707f601f';
const PIX_KEY = process.env.INTER_PIX_KEY || '5a50408a-7b74-4db6-959b-11369a0e14c0';

const FALLBACK_CERT_B64 = 'LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0tCk1JSUViakNDQTFhZ0F3SUJBZ0lSQUpvVDczOUM2MVQ0R3o0T3VhcTg0R293RFFZSktvWklodmNOQVFFTEJRQXcKZ1lveEN6QUpCZ05WQkFZVEFrSlNNUlV3RXdZRFZRUUlEQXhOYVc1aGN5QkhaWEpoYVhNeEZ6QVZCZ05WQkFjTQpEa0psYkc4Z1NHOXlhWHB2Ym5SbE1Rd3dDZ1lEVlFRS0RBTkJVRWt4Q3pBSkJnTlZCQXNNQWtsVU1UQXdMZ1lEClZRUUREQ2RCVUVrZ1NXNTBaWEp0WldScFlYUmxJRU5sY25ScFptbGpZWFJsSUVGMWRHaHZjbWwwZVFrd0hoY04KTWpZeE1ESTVNakF5TWpFMFdoY05NamN4TURJNU1qRXlNakUwV2pDQmdqRUxNQWtHQTFVRUJoTUNRbEl4Q3pBSgpCZ05WQkFnVEFsSk9NUTR3REFZRFZRUUhFd1ZPUVZSQlRERXRNQ3NHQTFVRUN4TWtNelJtTURCbU4ySXRabU5tCk1TMDBOREE1TFRneU1tTXRabVkyTkRKbE1USmlNMlUyTVEwd0N3WURWUVFLRXdSdWRXeHNNUmd3RmdZRFZRUUQKRXc5VFZ5QkVTVWRKVkVGTUlFeFVSRUV3Z2dFaU1BMEdDU3FHU0liM0RRRUJBUVVBQTRJQkR3QXdnZ0VLQW9JQgpBUUN0Z0h3clN4LytJUXlQVXEzSlJHUVFWR2YwZ0x5Kzg4ODEraUdtdTc4TGhOZVZtVU9tbkFvT3REOGg0bG5CCkNDU3pIb1FxcFFYTHJrUUh6Mkw4dHg3emwvL2Q4L1dlTkQ1ZEp3djZZMnVSc1dKc0FGK0FqTmZ0Y043NnpSa1MKUGVKMThacU1zQjJvMy9lYUE1cFlzRGxJS1Q1WXNXbzlxYmtudHNsQ0kybG1WQW5tRXRhTUtIb1o0c3NoUVBwSQpGNkIrRFNXb0w2enNidHJ2dWt1bmNIbTdJbGcvcHcrVVB1SzBYTjJ6VmtvdHQxMlRWWjFrVHg1S1RHeThrZjJECjR1c3lpaFZGOUxYQ3ZncEdVSWdDejJma0g1Nkw2cGJmZlF2SzdFdTkvTzV6bjNwR3lvQTl0OWpaY3BwK2N1SHIKYXAzaE9sUzJvYXYwUUhKU25yWGFKU0wvQWdNQkFBR2pnZFF3Z2RFd0NRWURWUjBUQkFJd0FEQWZCZ05WSFNNRQpHREFXZ0JRVUZXbjlOUFFSQ1A5WnUwNFp6SldYSW9yZ1BEQWRCZ05WSFE0RUZnUVV1disra1k2Vy9Gdzk3bS9UCitFdUdRdkUzOXd3d0RnWURWUjBQQVFIL0JBUURBZ1dnTUIwR0ExVWRKUVFXTUJRR0NDc0dBUVVGQndNQkJnZ3IKQmdFRkJRY0RBakJWQmdOVkhSOEVUakJNTUVxZ1NLQkdoa1JvZEhSd09pOHZZM0pzTFdGd2FTNWlhUzVzYjJOaApiQzlqY213dk1Ua3pOalJsNnpZdFl6UmlaUzAwTUdJMkxUbGpOekV0WVROaE4ySTBNRFEzTkdFMExtTnliREFOCkJna3Foa2lHOXcwQkFRc0ZBQU9DQVFFQTFvd1N2MkhQcVRyc0JwWDNBQmtYUUhjSDlCalBQcFgyRnBFTlZRUlEKWUtlcCsxZDRIc2ZWNkhNNDliZ2t5SDJIK1lzSjhDakQwMGtmUnVaMVpiQzdyeHJZLzRua3FzZnk5MitibDdOTwpVTmR0V1VaSEdZR044aGI2dWMxVjE2SDBraGN0ajlwcjlXTWxodkdwTG5URGpsWXJFSkxRVVJVVHBWS0JoRWNWCmE2S0pYbHFVNEtTWUdseVlZdjhYSkFnRk1DOWZJeEZsZ1pSTmEyUlFJc0xKQjQ0YXhQRFhHUTU4UmRMcWZQa1cKOXhyWHR6RnA0Z1o2Z0ErWjlpOGt3WFFpZFY2YkFnYUZKRGhTSUpTZU9EZXJiUG5mcWE0bjVJeTdNSCsvT1RNVwpIbUN0SUZZUDlRS1czd2hhS3VuUnRVODNZcjVZYTgvMWQyN0hHaFBaT3NXdlVnPT0KLS0tLS1FTkQgQ0VSVElGSUNBVEUtLS0tLQ==';
const FALLBACK_KEY_B64 = 'LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0tCk1JSUV2UUlCQURBTkJna3Foa2lHOXcwQkFRRUZBQVNDQktjd2dnU2pBZ0VBQW9JQkFRQ3RnSHdyU3gvK0lReVAKVXEzSlJHUVFWR2YwZ0x5Kzg4ODEraUdtdTc4TGhOZVZtVU9tbkFvT3REOGg0bG5CQ0NTekhvUXFwUVhMcmtRSAp6Mkw4dHg3emwvL2Q4L1dlTkQ1ZEp3djZZMnVSc1dKc0FGK0FqTmZ0Y043NnpSa1NQZUoxOFpxTXNCMm8zL2VhCkE1cFlzRGxJS1Q1WXNXbzlxYmtudHNsQ0kybG1WQW5tRXRhTUtIb1o0c3NoUVBwSUY2QitEU1dvTDZ6c2J0cnYKdWt1bmNIbTdJbGcvcHcrVVB1SzBYTjJ6VmtvdHQxMlRWWjFrVHg1S1RHeThrZjJENHVzeWloVkY5TFhDdmdwRwpVSWdDejJma0g1Nkw2cGJmZlF2SzdFdTkvTzV6bjNwR3lvQTl0OWpaY3BwK2N1SHJhcDNoT2xTMm9hdjBRSEpTCm5yWGFKU0wvQWdNQkFBRUNnZ0VBSkU2L2JVWG0xNFR0L200a1hQcDVZQ3R4cDZwckZTQ3JTNVhoQmVYREdITi8KczlnalhwSEh6d1RzTXppTlpNWkIrOVBXZjZBU0F1b2daV3dDUUhWSHZsMGdGNy91TmVHajdWVjIvYnBoYjljcApqQVZWOXU1Q1gzZGZ5aWN5YUcxWDN5dWtsbTFpZjQwQzRSR0E4cTlLQlc1UUZEcG9TNmdoVFl6RU9CbDEvSW9nClpUQ1lESW9UK1NkaGxySlVPeU9qUkYvaXNsMnRWejQyOFg2dHZJS0pneU1uSEdvZHNWQnVzdVpPYUozNXNpZWoKNVdZMlNnOFgyYzRGdHUxRmhOU21ldGFPRUswdlc0TkMveWQreDY2ZFBiT3dtSTJXb0pPdTA1M3llSHdzeS80MwpVTGNIazdtVVBObG5FUXl5OGxNMVVGSndZOE5pMjROcXNCTUdkZGlXaVFLQmdRRFNYK3JwN2JFS0U4U1NtR051Cmp2MU1YN2RtUVNQNTA4OWpaeWdxKzczYzhFRkphcVNOZ3hRMVJoaTRBYU9TbUJWOXlhZmtiem1LdUNZeWo0ckgKcFkwVVJQZG9GU3RHbk5QTjg5VXFDSERFQzJnVExUcm5GSXVUZkdhdy9SSnN1RXZiZE9JYXB6WFdTWGpVQnl2RQpOelJudkhHQVRkZFEzMmxmRTRjUmFjS0pPUUtCZ1FEVElXQmJqUUIxTjlrVjNFSk1oUEV1S1FKZmV3eVFVQmt0CmM3by9KanpEQzhVTFhrSnBFSk9ONHorUEU1cjhmNUpjaU5IODNFNk9wM3BmK2V0OTZ6WkNkTFVnaTJFaW1scUYKNWJRcEtIOEwyWVZhczd4MTRKSmdPeGdyMXRpb0RQa2V1NG4rMms5LzN3R3Awc0c1NTFyUVRLUk9GUk54Rk9RWgp2aFhHYWdtbDl3S0JnSDBTWDRSU055WUptSjJiRWNwaUluK3NqRW16d3FLOTVaZHdkZllRRXRIdTJMSEFRREtOCjBvN1ZyTTZBMHZITmowRm9pWE9MR01lN01hSnZxbytGZ2ptaHd3RlRUSlkvbU1EaURVSmZJRU85a0ZPT1dXMlcKem1DUjNpK3RWYTNqWjk0Q1FJYWVFS2prcDN4UEF4czF3dWRGcHFra0hqWExqVWJrUWpIOUVaWXBBb0dBYndsMwpwczV5TmpPbi9RSTQ4QXRlMkZzQy8zbzBjbFZkMkhTcnQvaUJMa2NyV3o0NGlROEp1eTZQeDh5VXowUzhrZVAzCkpCZ3RUSU15TGZXL2J4cmNEM2xYcFFVSWtlMUJ2SGZCRjRCUHlNaWVoTVJRVW1KSU9VbjYvVnRoMklmeUlNS2EKNGFpbzlPUXcrTUo1MWk2aHFUa1ZsR2NyTVdhK1MvZVhkaUZnYjZNQ2dZRUFrdXFiWmNUK1Z1SVBCRmowd3hUZQpWRUYxUmE1dHFzZEhkYkFxdE93UHBMa0p1dXlMc0MxNEVXNVY0alRpcjI0WkoyOEtjZmEzVUlvUSt2ZmxOVVMwCmFzK1o2OWdVZjV6SUJ2bmV1NlZiL09mTVp5ekJhV2I4bG1obmthMGd3UW5BTWo3Ui9qUENCY0t4eWdWOHRrN0QKSjdxMWtjVVE3WE5NNWVqaWFZMnZGK2s9Ci0tLS0tRU5EIFBSSVZBVEUgS0VZLS0tLS0=';

function getCertificate() {
  if (process.env.INTER_CERT_BASE64) {
    return Buffer.from(process.env.INTER_CERT_BASE64, 'base64');
  }
  const certFilePath = path.join(__dirname, 'certs', 'Inter_API_Certificado.crt');
  if (fs.existsSync(certFilePath)) {
    return fs.readFileSync(certFilePath);
  }
  return Buffer.from(FALLBACK_CERT_B64, 'base64');
}

function getPrivateKey() {
  if (process.env.INTER_KEY_BASE64) {
    return Buffer.from(process.env.INTER_KEY_BASE64, 'base64');
  }
  const keyFilePath = path.join(__dirname, 'certs', 'Inter_API_Chave.key');
  if (fs.existsSync(keyFilePath)) {
    return fs.readFileSync(keyFilePath);
  }
  return Buffer.from(FALLBACK_KEY_B64, 'base64');
}

let cachedAgent = null;
function getHttpsAgent() {
  if (!cachedAgent) {
    cachedAgent = new https.Agent({
      cert: getCertificate(),
      key: getPrivateKey(),
      rejectUnauthorized: true,
      keepAlive: true
    });
  }
  return cachedAgent;
}

let cachedToken = null;
let tokenExpiresAt = 0;

async function getInterToken() {
  const now = Date.now();
  if (cachedToken && now < tokenExpiresAt - 60000) {
    return cachedToken;
  }

  const postData = querystring.stringify({
    client_id: CLIENT_ID,
    client_secret: CLIENT_SECRET,
    scope: 'cob.read cob.write pix.read pix.write',
    grant_type: 'client_credentials'
  });

  return new Promise((resolve, reject) => {
    const req = https.request({
      hostname: 'cdpj.partners.bancointer.com.br',
      port: 443,
      path: '/oauth/v2/token',
      method: 'POST',
      agent: getHttpsAgent(),
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Content-Length': Buffer.byteLength(postData)
      }
    }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          if (res.statusCode === 200 && parsed.access_token) {
            cachedToken = parsed.access_token;
            tokenExpiresAt = Date.now() + ((parsed.expires_in || 3600) * 1000);
            resolve(cachedToken);
          } else {
            reject(new Error(`Inter Auth Failed (${res.statusCode}): ${data}`));
          }
        } catch (e) {
          reject(e);
        }
      });
    });

    req.on('error', reject);
    req.write(postData);
    req.end();
  });
}

/**
 * Cria uma cobrança imediata PIX via Banco Inter
 */
async function createPixCob({ amount = 4.99, description = '10 Chaves - Desafio do Cofre' }) {
  const token = await getInterToken();

  const payload = JSON.stringify({
    calendario: { expiracao: 3600 },
    valor: { original: Number(amount).toFixed(2) },
    chave: PIX_KEY,
    solicitacaoPagador: description
  });

  return new Promise((resolve, reject) => {
    const req = https.request({
      hostname: 'cdpj.partners.bancointer.com.br',
      port: 443,
      path: '/pix/v2/cob',
      method: 'POST',
      agent: getHttpsAgent(),
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload)
      }
    }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          if (res.statusCode === 201 && parsed.pixCopiaECola) {
            resolve({
              txid: parsed.txid,
              pixCopiaECola: parsed.pixCopiaECola,
              location: parsed.location,
              status: parsed.status,
              valor: parsed.valor?.original || amount
            });
          } else {
            reject(new Error(`Inter Pix Error (${res.statusCode}): ${data}`));
          }
        } catch (e) {
          reject(e);
        }
      });
    });

    req.on('error', reject);
    req.write(payload);
    req.end();
  });
}

/**
 * Consulta o status de um Pix no Banco Inter pelo txid
 */
async function checkPixCob(txid) {
  if (!txid) return { paid: false, status: 'NOT_FOUND' };
  const token = await getInterToken();

  return new Promise((resolve, reject) => {
    const req = https.request({
      hostname: 'cdpj.partners.bancointer.com.br',
      port: 443,
      path: `/pix/v2/cob/${encodeURIComponent(txid)}`,
      method: 'GET',
      agent: getHttpsAgent(),
      headers: {
        'Authorization': `Bearer ${token}`,
        'Accept': 'application/json'
      }
    }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          if (res.statusCode === 200) {
            const isPaid = parsed.status === 'CONCLUIDA';
            resolve({
              txid: parsed.txid,
              status: parsed.status,
              paid: isPaid,
              valor: parsed.valor?.original,
              horario: parsed.pix?.[0]?.horario || null
            });
          } else {
            resolve({ paid: false, status: parsed.status || 'ERROR', error: data });
          }
        } catch (e) {
          resolve({ paid: false, status: 'PARSE_ERROR', error: e.message });
        }
      });
    });

    req.on('error', (e) => resolve({ paid: false, status: 'NETWORK_ERROR', error: e.message }));
    req.end();
  });
}

async function setupWebhook(webhookUrl = 'https://web-production-09e83.up.railway.app/api/pix/webhook') {
  const token = await getInterToken();
  const payload = JSON.stringify({ webhookUrl });

  return new Promise((resolve) => {
    const req = https.request({
      hostname: 'cdpj.partners.bancointer.com.br',
      port: 443,
      path: `/pix/v2/webhook/${encodeURIComponent(PIX_KEY)}`,
      method: 'PUT',
      agent: getHttpsAgent(),
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload)
      }
    }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        resolve({ status: res.statusCode, data });
      });
    });
    req.on('error', (e) => resolve({ status: 500, error: e.message }));
    req.write(payload);
    req.end();
  });
}

module.exports = {
  createPixCob,
  checkPixCob,
  getInterToken,
  setupWebhook,
  PIX_KEY
};
