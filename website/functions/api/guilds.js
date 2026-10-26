/**
 * Cloudflare Pages Function: /api/guilds
 * Returns user's manageable Discord servers (Admin or Manage Guild).
 */

export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);

  let sessionStr = null;
  const cookieHeader = request.headers.get('Cookie') || '';
  const match = cookieHeader.match(/kyoka_session=([^;]+)/);
  if (match) sessionStr = decodeURIComponent(match[1]);
  const authHeader = request.headers.get('Authorization') || '';
  if (!sessionStr && authHeader.startsWith('Bearer ')) sessionStr = authHeader.substring(7).trim();

  // If backend configured, forward to backend
  const backendBase = (
    env.BACKEND_URL ||
    env.KYOKA_BACKEND_URL ||
    ''
  ).replace(/\/+$/, '');

  if (backendBase) {
    try {
      const backendRes = await fetch(`${backendBase}/api/guilds${url.search}`, {
        method: 'GET',
        headers: request.headers,
      });
      const headers = new Headers(backendRes.headers);
      headers.set('Access-Control-Allow-Origin', url.origin);
      headers.set('Access-Control-Allow-Credentials', 'true');
      return new Response(backendRes.body, {
        status: backendRes.status,
        headers: headers,
      });
    } catch {}
  }

  if (!sessionStr) {
    return new Response(JSON.stringify({ error: 'Unauthorized', guilds: [] }), {
      status: 401,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': url.origin,
        'Access-Control-Allow-Credentials': 'true',
      },
    });
  }

  try {
    const session = JSON.parse(atob(sessionStr));
    const token = session.access_token;
    if (!token) {
      return new Response(JSON.stringify({ error: 'Session token missing', guilds: [] }), {
        status: 401,
        headers: {
          'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': url.origin,
          'Access-Control-Allow-Credentials': 'true',
        },
      });
    }

    const discordRes = await fetch('https://discord.com/api/users/@me/guilds', {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (!discordRes.ok) {
      const err = await discordRes.text();
      return new Response(JSON.stringify({ error: 'Failed to retrieve guilds from Discord API', details: err, guilds: [] }), {
        status: 502,
        headers: {
          'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': url.origin,
          'Access-Control-Allow-Credentials': 'true',
        },
      });
    }

    const guilds = await discordRes.json();
    const manageable = guilds.filter(g => {
      const perms = BigInt(g.permissions || 0);
      return (perms & BigInt(0x8)) !== BigInt(0) || (perms & BigInt(0x20)) !== BigInt(0);
    }).map(g => ({
      id: g.id,
      name: g.name,
      icon: g.icon ? `https://cdn.discordapp.com/icons/${g.id}/${g.icon}.png` : null,
      owner: Boolean(g.owner),
      permissions: g.permissions,
      bot_in_guild: true,
    }));

    return new Response(JSON.stringify({ guilds: manageable }), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': url.origin,
        'Access-Control-Allow-Credentials': 'true',
      },
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: err.message, guilds: [] }), {
      status: 500,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': url.origin,
        'Access-Control-Allow-Credentials': 'true',
      },
    });
  }
}
