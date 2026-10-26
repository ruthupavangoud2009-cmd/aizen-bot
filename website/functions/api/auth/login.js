/**
 * Cloudflare Pages Function: /api/auth/login
 * Initiates official Discord OAuth2 authorization-code flow with CSRF protection.
 *
 * Scopes: identify, guilds
 * Client ID: 1562505487214321714 (KYOKA 3.0 / Aizen Edition)
 * Redirect URI: https://aizen-bot.pages.dev/api/auth/callback
 */

export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);

  // 1. Resolve Client ID & Redirect URI
  const clientId = (
    env.DISCORD_CLIENT_ID ||
    env.CLIENT_ID ||
    '1562505487214321714'
  ).trim();

  // Target frontend origin: always Cloudflare Pages in production
  const destinationOrigin = url.origin.includes('localhost') ? url.origin : 'https://aizen-bot.pages.dev';

  let redirectUri = (
    env.DISCORD_REDIRECT_URI ||
    `${destinationOrigin}/api/auth/callback`
  ).trim();

  // Safety guard: If DISCORD_REDIRECT_URI was mistakenly set to an onrender.com URL in dashboard, force Cloudflare
  if (redirectUri.includes('onrender.com') || !redirectUri.startsWith('http')) {
    redirectUri = `${destinationOrigin}/api/auth/callback`;
  }

  // 2. Generate cryptographically secure CSRF state (32 random bytes)
  const array = new Uint8Array(32);
  crypto.getRandomValues(array);
  const state = Array.from(array, (b) => b.toString(16).padStart(2, '0')).join('');

  // 3. Build official Discord authorization URL
  const params = new URLSearchParams({
    client_id: clientId,
    response_type: 'code',
    redirect_uri: redirectUri,
    scope: 'identify guilds',
    state: state,
    prompt: 'consent',
  });

  const discordAuthUrl = `https://discord.com/api/oauth2/authorize?${params.toString()}`;

  // 4. Set HttpOnly CSRF state cookie valid for 10 minutes (600s)
  const isHttps = url.protocol === 'https:' || !url.hostname.includes('localhost');
  const stateCookie = `kyoka_oauth_state=${state}; Path=/; Max-Age=600; SameSite=Lax${isHttps ? '; Secure' : ''}; HttpOnly`;

  // 5. If called via AJAX/fetch requesting JSON format
  const acceptHeader = request.headers.get('Accept') || '';
  if (url.searchParams.get('format') === 'json' || acceptHeader.includes('application/json')) {
    return new Response(
      JSON.stringify({
        auth_url: discordAuthUrl,
        state: state,
        client_id: clientId,
        redirect_uri: redirectUri,
      }),
      {
        status: 200,
        headers: {
          'Content-Type': 'application/json',
          'Set-Cookie': stateCookie,
          'Access-Control-Allow-Origin': url.origin,
          'Access-Control-Allow-Credentials': 'true',
        },
      }
    );
  }

  // 6. Direct browser navigation: 302 Redirect to Discord
  return new Response(null, {
    status: 302,
    headers: {
      'Location': discordAuthUrl,
      'Set-Cookie': stateCookie,
      'Cache-Control': 'no-cache, no-store, must-revalidate',
    },
  });
}
