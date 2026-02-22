// MSS Push Notification Worker
// Handles push token registration and sending notifications via Expo Push API.

const EXPO_PUSH_URL = 'https://exp.host/--/api/v2/push/send';

// Expo recommends batches of up to 100 notifications per request.
const EXPO_BATCH_SIZE = 100;

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', ...CORS_HEADERS },
  });
}

// --------------- POST /api/push/register ---------------

async function handleRegister(request, env) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ ok: false, error: 'Invalid JSON' }, 400);
  }

  const { token, platform } = body;

  if (!token || typeof token !== 'string') {
    return json({ ok: false, error: 'Missing or invalid token' }, 400);
  }
  if (!platform || typeof platform !== 'string') {
    return json({ ok: false, error: 'Missing or invalid platform' }, 400);
  }

  await env.DB.prepare(
    `INSERT INTO push_tokens (token, platform)
     VALUES (?, ?)
     ON CONFLICT(token) DO UPDATE SET
       platform = excluded.platform,
       last_seen_at = datetime('now')`
  )
    .bind(token, platform)
    .run();

  return json({ ok: true });
}

// --------------- POST /api/push/send-new-track ---------------

async function handleSendNewTrack(request, env) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ ok: false, error: 'Invalid JSON' }, 400);
  }

  const { trackId, trackName } = body;

  if (trackId === undefined || trackId === null) {
    return json({ ok: false, error: 'Missing trackId' }, 400);
  }
  if (!trackName || typeof trackName !== 'string') {
    return json({ ok: false, error: 'Missing or invalid trackName' }, 400);
  }

  // Fetch all tokens
  const { results } = await env.DB.prepare(
    'SELECT token FROM push_tokens'
  ).all();

  if (!results || results.length === 0) {
    return json({ ok: true, sent: 0 });
  }

  // Build Expo push messages
  const messages = results.map((row) => ({
    to: row.token,
    title: 'New Track Available',
    body: `"${trackName}" is now available! Tap to download.`,
    data: {
      type: 'new_track',
      trackId: String(trackId),
      trackName,
    },
    sound: 'default',
  }));

  // Send in batches of EXPO_BATCH_SIZE
  let totalSent = 0;
  const errors = [];

  for (let i = 0; i < messages.length; i += EXPO_BATCH_SIZE) {
    const batch = messages.slice(i, i + EXPO_BATCH_SIZE);

    try {
      const resp = await fetch(EXPO_PUSH_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
        },
        body: JSON.stringify(batch),
      });

      if (resp.ok) {
        const data = await resp.json();
        // data.data is an array of tickets, one per message
        const tickets = data.data || [];
        tickets.forEach((ticket, idx) => {
          if (ticket.status === 'ok') {
            totalSent++;
          } else {
            errors.push({
              token: batch[idx].to,
              status: ticket.status,
              message: ticket.message,
              details: ticket.details,
            });
          }
        });
      } else {
        const text = await resp.text();
        errors.push(`Expo API ${resp.status}: ${text}`);
      }
    } catch (err) {
      errors.push(`Fetch error: ${err.message}`);
    }
  }

  const result = { ok: true, sent: totalSent };
  if (errors.length > 0) {
    result.errors = errors;
  }
  return json(result);
}

// --------------- Router ---------------

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const { pathname } = url;

    // CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    if (request.method === 'POST' && pathname === '/api/push/register') {
      return handleRegister(request, env);
    }

    if (request.method === 'POST' && pathname === '/api/push/send-new-track') {
      return handleSendNewTrack(request, env);
    }

    return json({ ok: false, error: 'Not found' }, 404);
  },
};
