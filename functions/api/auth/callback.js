/**
 * Cloudflare Pages Function: OAuth2 Callback Handler
 * Receives the authorization code from Discord and exchanges it securely.
 * Destination dashboard is ALWAYS https://aizen-bot.pages.dev/dashboard.html
 */

export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);

  // Target frontend origin: always Cloudflare Pages in production
  const destinationOrigin = url.origin.includes('localhost') ? url.origin : 'https://aizen-bot.pages.dev';

  const code = url.searchParams.get('code');
  const state = url.searchParams.get('state');
  const error = url.searchParams.get('error');
  const errorDescription = url.searchParams.get('error_description');

  if (error) {
    return Response.redirect(`${destinationOrigin}/dashboard?error=${encodeURIComponent(error)}&error_description=${encodeURIComponent(errorDescription || '')}`, 302);
  }

  if (!code) {
    return Response.redirect(`${destinationOrigin}/dashboard?error=missing_code`, 302);
  }

  // 1. Validate CSRF state against short-lived HttpOnly state cookie
  const cookieHeader = request.headers.get('Cookie') || '';
  const stateMatch = cookieHeader.match(/(?:^|;\s*)kyoka_oauth_state=([^;]+)/);
  const storedState = stateMatch ? decodeURIComponent(stateMatch[1].trim()) : null;

  if (storedState && state && state !== storedState) {
    return Response.redirect(`${destinationOrigin}/dashboard?error=invalid_state&error_description=CSRF+state+mismatch.+Please+try+logging+in+again.`, 302);
  }

  const isHttps = url.protocol === 'https:' || !url.hostname.includes('localhost');
  const clearStateCookie = `kyoka_oauth_state=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax${isHttps ? '; Secure' : ''}`;

  // 2. Token Exchange Parameters
  const clientId = (env.DISCORD_CLIENT_ID || env.CLIENT_ID || '1562407391440535633').trim();
  const clientSecret = (env.DISCORD_CLIENT_SECRET || env.CLIENT_SECRET || '').trim();
  const redirectUri = `${destinationOrigin}/api/auth/callback`;

  const backendBase = (
    env.BACKEND_URL ||
    env.KYOKA_BACKEND_URL ||
    'https://aizen-bot-uty6.onrender.com'
  ).replace(/\/+$/, '');

  let sessionPayload = null;
  let sessionStr = null;

  // Option A: Direct Token Exchange at Edge if client_secret is configured in Cloudflare Pages
  if (clientSecret) {
    try {
      const tokenParams = new URLSearchParams({
        client_id: clientId,
        client_secret: clientSecret,
        grant_type: 'authorization_code',
        code: code,
        redirect_uri: redirectUri,
      });

      const tokenRes = await fetch('https://discord.com/api/oauth2/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: tokenParams.toString(),
      });

      if (!tokenRes.ok) {
        const errText = await tokenRes.text();
        return Response.redirect(`${destinationOrigin}/dashboard?error=token_exchange_failed&error_description=${encodeURIComponent(errText)}`, 302);
      }

      const tokenData = await tokenRes.json();
      const userRes = await fetch('https://discord.com/api/users/@me', {
        headers: { Authorization: `Bearer ${tokenData.access_token}` },
      });

      if (!userRes.ok) {
        return Response.redirect(`${destinationOrigin}/dashboard?error=user_fetch_failed`, 302);
      }

      const userData = await userRes.json();
      const avatarUrl = userData.avatar
        ? `https://cdn.discordapp.com/avatars/${userData.id}/${userData.avatar}.png`
        : `https://cdn.discordapp.com/embed/avatars/${parseInt(userData.discriminator || '0') % 5}.png`;

      const isOwner = String(userData.id) === '1505515188991033409';
      const isStaff = isOwner || String(userData.id) === '1532660258403647687' || String(userData.username || '').toLowerCase() === 'mrhowler01';
      const staffRole = isOwner ? 'admin' : (isStaff ? 'admin' : null);

      sessionPayload = {
        user_id: userData.id,
        username: userData.username,
        discriminator: userData.discriminator || '0',
        global_name: userData.global_name || userData.username,
        avatar_url: avatarUrl,
        access_token: tokenData.access_token,
        is_owner: isOwner,
        is_staff: isStaff,
        staff_role: staffRole,
        expires_at: Date.now() + (tokenData.expires_in || 604800) * 1000,
      };

      sessionStr = btoa(JSON.stringify(sessionPayload));
    } catch (err) {
      return Response.redirect(`${destinationOrigin}/dashboard?error=internal_error&error_description=${encodeURIComponent(err.message)}`, 302);
    }
  } else if (backendBase) {
    // Option B: Delegate Code Exchange to Backend securely (if client_secret is stored on Render)
    try {
      const exchangeRes = await fetch(`${backendBase}/api/auth/exchange`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: JSON.stringify({
          code: code,
          redirect_uri: redirectUri,
        }),
      });

      if (exchangeRes.ok) {
        const exchangeData = await exchangeRes.json();
        if (exchangeData.success && exchangeData.user) {
          sessionPayload = {
            user_id: exchangeData.user.id,
            username: exchangeData.user.username,
            discriminator: exchangeData.user.discriminator || '0',
            global_name: exchangeData.user.global_name || exchangeData.user.username,
            avatar_url: exchangeData.user.avatar_url,
            access_token: exchangeData.token_data?.access_token || '',
            expires_at: Date.now() + 604800 * 1000,
          };
          sessionStr = exchangeData.session_token || btoa(JSON.stringify(sessionPayload));
        }
      }
    } catch (backendErr) {
      console.warn('Backend exchange request failed:', backendErr);
    }
  }

  // If session was successfully constructed
  if (sessionStr) {
    const sessionCookie = `kyoka_session=${sessionStr}; Path=/; Max-Age=${7 * 86400}; SameSite=Lax${isHttps ? '; Secure' : ''}`;
    const headers = new Headers();
    headers.set('Location', `${destinationOrigin}/dashboard#token=${encodeURIComponent(sessionStr)}`);
    headers.append('Set-Cookie', sessionCookie);
    headers.append('Set-Cookie', clearStateCookie);

    return new Response(null, {
      status: 302,
      headers: headers,
    });
  }

  // Option C: Neither client_secret nor backend exchange succeeded: Show Aizen Setup Card
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>KYOKA 3.0 — Discord OAuth2 Setup</title>
  <link rel="stylesheet" href="/css/style.css">
  <style>
    body { background: #07030D; color: #fff; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; display: flex; align-items: center; justify-content: center; min-height: 100vh; padding: 2rem; margin: 0; }
    .auth-box { max-width: 600px; background: rgba(18, 9, 34, 0.95); border: 1px solid #7c3aed; border-radius: 16px; padding: 2.5rem; text-align: center; box-shadow: 0 10px 40px rgba(0,0,0,0.8); }
    .badge { display: inline-block; padding: 0.25rem 0.75rem; border-radius: 9999px; background: rgba(168, 85, 247, 0.2); color: #c084fc; font-size: 0.8rem; font-weight: 700; margin-bottom: 1rem; border: 1px solid rgba(168, 85, 247, 0.4); }
    .code-box { background: rgba(0,0,0,0.6); padding: 1rem; border-radius: 8px; text-align: left; font-family: monospace; font-size: 0.85rem; color: #e2e8f0; margin: 1.5rem 0; border-left: 3px solid #a855f7; word-break: break-all; }
  </style>
</head>
<body>
  <div class="auth-box">
    <div class="badge">DISCORD OAUTH2 AUTHORIZATION CODE RECEIVED</div>
    <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">⚡</div>
    <h2 style="color: #fff; margin-bottom: 0.75rem;">Authorization Received</h2>
    <p style="color: #94a3b8; font-size: 0.95rem; line-height: 1.6;">
      Discord authorized successfully! To complete automatic token exchange, ensure <code>DISCORD_CLIENT_SECRET</code> is configured in Cloudflare Pages environment variables.
    </p>
    <div class="code-box">
      <strong>Registered Callback URI:</strong><br>
      <span style="color: #c084fc;">https://aizen-bot.pages.dev/api/auth/callback</span>
    </div>
    <div style="display: flex; gap: 1rem; justify-content: center;">
      <a href="${destinationOrigin}/dashboard" class="btn btn-primary">Return to Dashboard</a>
      <a href="https://discord.gg/7q4tn6dA6V" target="_blank" class="btn btn-discord">Support Discord</a>
    </div>
  </div>
</body>
</html>`;

  return new Response(html, {
    status: 200,
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'Set-Cookie': clearStateCookie,
    },
  });
}
