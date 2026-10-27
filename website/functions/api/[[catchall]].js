/**
 * Cloudflare Pages Function: Universal Edge Catchall for /api/*
 * Proxies API traffic to the active Render backend when configured,
 * or handles CORS preflight and safe default responses at the Cloudflare edge.
 */

export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);

  // Handle CORS preflight directly at the Cloudflare edge
  if (request.method === 'OPTIONS') {
    return new Response(null, {
      status: 204,
      headers: {
        'Access-Control-Allow-Origin': url.origin,
        'Access-Control-Allow-Credentials': 'true',
        'Access-Control-Allow-Methods': 'GET, POST, PATCH, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With, Accept',
        'Access-Control-Max-Age': '86400',
      },
    });
  }

  // Read backend base URL from Cloudflare environment variable with production fallback
  const backendBase = (
    env.BACKEND_URL ||
    env.KYOKA_BACKEND_URL ||
    'https://kyokasugisetsu.onrender.com'
  ).replace(/\/+$/, '');

  if (backendBase) {
    const targetUrl = new URL(`${backendBase}${url.pathname}${url.search}`);
    const headers = new Headers(request.headers);
    headers.set('X-Forwarded-Host', url.host);
    headers.set('X-Forwarded-Proto', url.protocol.replace(':', ''));
    if (!headers.get('Origin')) {
      headers.set('Origin', url.origin);
    }

    const init = {
      method: request.method,
      headers: headers,
      redirect: 'manual',
    };

    if (request.method !== 'GET' && request.method !== 'HEAD') {
      init.body = request.body;
    }

    try {
      const response = await fetch(targetUrl.toString(), init);
      const responseHeaders = new Headers(response.headers);
      responseHeaders.set('Access-Control-Allow-Origin', url.origin);
      responseHeaders.set('Access-Control-Allow-Credentials', 'true');
      responseHeaders.set('Access-Control-Allow-Methods', 'GET, POST, PATCH, PUT, DELETE, OPTIONS');
      responseHeaders.set('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, Accept');

      if (response.status >= 300 && response.status < 400) {
        let loc = response.headers.get('location');
        if (loc) {
          loc = loc.replace(/^https?:\/\/[^\/]+\/dashboard(\.html)?/, 'https://aizen-bot.pages.dev/dashboard');
          if (loc.startsWith('/dashboard.html') || loc.startsWith('/dashboard')) {
            loc = `https://aizen-bot.pages.dev/dashboard`;
          }
          responseHeaders.set('Location', loc);
        }
      }

      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: responseHeaders,
      });
    } catch (err) {
      console.warn('Backend proxy fetch failed:', err);
    }
  }

  // Dedicated check: if login route reached catchall, redirect directly to Discord OAuth2
  if (url.pathname === '/api/auth/login') {
    const clientId = (env.DISCORD_CLIENT_ID || env.CLIENT_ID || '1562505487214321714').trim();
    const destinationOrigin = url.origin.includes('localhost') ? url.origin : 'https://aizen-bot.pages.dev';
    const redirectUri = `${destinationOrigin}/api/auth/callback`;
    const array = new Uint8Array(32);
    crypto.getRandomValues(array);
    const state = Array.from(array, b => b.toString(16).padStart(2, '0')).join('');
    const discordAuthUrl = `https://discord.com/api/oauth2/authorize?client_id=${clientId}&redirect_uri=${encodeURIComponent(redirectUri)}&response_type=code&scope=identify%20guilds&state=${state}&prompt=consent`;
    return Response.redirect(discordAuthUrl, 302);
  }

  if (url.pathname === '/api/auth/callback') {
    const destinationOrigin = url.origin.includes('localhost') ? url.origin : 'https://aizen-bot.pages.dev';
    return Response.redirect(`${destinationOrigin}/dashboard?error=invalid_state`, 302);
  }

  // Graceful standalone fallback when backend is not configured or in transition
  return new Response(
    JSON.stringify({
      message: 'KYOKA 3.0 Cloudflare Edge API Active',
      path: url.pathname,
      status: 'operational',
      hint: 'Configure BACKEND_URL in Cloudflare Pages environment variables if routing to external Render service.',
    }),
    {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': url.origin,
        'Access-Control-Allow-Credentials': 'true',
      },
    }
  );
}
