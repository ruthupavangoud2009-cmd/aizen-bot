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

    // Edge bot guild verification if bot token is configured in Cloudflare environment
    const rawBotToken = (env.DISCORD_TOKEN || env.BOT_TOKEN || env.TOKEN || '').trim();
    const cleanBotToken = rawBotToken.toLowerCase().startsWith('bot ') ? rawBotToken.substring(4).trim() : rawBotToken;

    let botGuildIds = new Set();
    let botCheckOk = false;

    if (cleanBotToken) {
      try {
        const botRes = await fetch('https://discord.com/api/users/@me/guilds?limit=200', {
          headers: { Authorization: `Bot ${cleanBotToken}` },
        });
        if (botRes.ok) {
          const botGuilds = await botRes.json();
          if (Array.isArray(botGuilds)) {
            botGuildIds = new Set(botGuilds.map(b => String(b.id)));
            botCheckOk = true;
          }
        }
      } catch (e) {
        console.warn('Edge bot guilds query notice:', e);
      }
    }

    const installedOnly = url.searchParams.get('installed_only') === '1' || url.searchParams.get('installed_only') === 'true';

    const manageable = rawGuilds.filter(g => {
      const perms = BigInt(g.permissions || 0);
      return Boolean(g.owner) || (perms & BigInt(0x8)) !== BigInt(0) || (perms & BigInt(0x20)) !== BigInt(0);
    }).map(g => {
      const gid = String(g.id);
      const iconUrl = g.icon ? `https://cdn.discordapp.com/icons/${gid}/${g.icon}.png?size=128` : null;
      let status = 'unavailable';
      let isInstalled = false;

      if (botCheckOk) {
        if (botGuildIds.has(gid)) {
          status = 'installed';
          isInstalled = true;
        } else {
          status = 'not_installed';
          isInstalled = false;
        }
      }

      return {
        id: gid,
        name: g.name || 'Unknown Server',
        icon: g.icon,
        icon_url: iconUrl,
        is_owner: Boolean(g.owner),
        can_manage: true,
        bot_installed: isInstalled,
        status: status,
        permissions: String(g.permissions || '0'),
        invite_url: `https://discord.com/oauth2/authorize?client_id=${clientId}&guild_id=${gid}&permissions=8&scope=bot%20applications.commands`,
      };
    });

    const finalGuilds = installedOnly
      ? manageable.filter(g => (g.can_manage && g.bot_installed) || g.status === 'unavailable')
      : manageable;

    return new Response(JSON.stringify({ guilds: finalGuilds, total: finalGuilds.length, verification_status: botCheckOk ? 'verified' : 'unavailable' }), {
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
