/**
 * Cloudflare Pages Function: /api/guilds
 * Returns user's manageable Discord servers (Administrator, Manage Guild, or Server Owner).
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

  // 1. If backend configured, attempt backend query first
  const backendBase = (
    env.BACKEND_URL ||
    env.KYOKA_BACKEND_URL ||
    'https://kyokasugisetsu.onrender.com'
  ).replace(/\/+$/, '');

  if (backendBase) {
    try {
      const backendRes = await fetch(`${backendBase}/api/guilds${url.search}`, {
        method: 'GET',
        headers: request.headers,
      });
      if (backendRes.ok) {
        const data = await backendRes.json();
        if (data && Array.isArray(data.guilds)) {
          return new Response(JSON.stringify(data), {
            status: 200,
            headers: {
              'Content-Type': 'application/json',
              'Access-Control-Allow-Origin': url.origin,
              'Access-Control-Allow-Credentials': 'true',
            },
          });
        }
      }
    } catch (e) {
      console.warn('Backend guilds fetch notice, falling back to edge Discord query:', e);
    }
  }

  // 2. Fallback to direct Discord API using access_token in session
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
    let session = null;
    try {
      const raw = sessionStr.includes('.') ? sessionStr.split('.')[0] : sessionStr;
      const padding = '='.repeat((4 - (raw.length % 4)) % 4);
      session = JSON.parse(atob(raw + padding));
    } catch {}

    const token = session?.access_token;
    if (!token) {
      return new Response(JSON.stringify({ error: 'Session token missing or expired', guilds: [] }), {
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

    const rawGuilds = await discordRes.json();
    const clientId = (env.DISCORD_CLIENT_ID || env.CLIENT_ID || '1562505487214321714').trim();

    const manageable = rawGuilds.filter(g => {
      const perms = BigInt(g.permissions || 0);
      return Boolean(g.owner) || (perms & BigInt(0x8)) !== BigInt(0) || (perms & BigInt(0x20)) !== BigInt(0);
    }).map(g => {
      const iconUrl = g.icon ? `https://cdn.discordapp.com/icons/${g.id}/${g.icon}.png?size=128` : null;
      return {
        id: String(g.id),
        name: g.name || 'Unknown Server',
        icon: g.icon,
        icon_url: iconUrl,
        is_owner: Boolean(g.owner),
        can_manage: true,
        bot_installed: true,
        status: 'installed',
        permissions: String(g.permissions || '0'),
        invite_url: `https://discord.com/oauth2/authorize?client_id=${clientId}&guild_id=${g.id}&permissions=8&scope=bot%20applications.commands`,
      };
    });

    return new Response(JSON.stringify({ guilds: manageable, total: manageable.length }), {
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
