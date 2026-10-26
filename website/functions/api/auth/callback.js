/**
 * Cloudflare Pages Function: OAuth2 Callback Handler
 * Receives the code from Discord and exchanges it securely.
 */

export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  const code = url.searchParams.get('code');
  const state = url.searchParams.get('state');
  const error = url.searchParams.get('error');
  const errorDescription = url.searchParams.get('error_description');

  if (error) {
    return Response.redirect(`${url.origin}/dashboard.html?error=${encodeURIComponent(error)}&error_description=${encodeURIComponent(errorDescription || '')}`, 302);
  }

  if (!code) {
    return Response.redirect(`${url.origin}/dashboard.html?error=missing_code`, 302);
  }

  // Validate CSRF state against HttpOnly state cookie if present
  const cookieHeader = request.headers.get('Cookie') || '';
  const stateMatch = cookieHeader.match(/kyoka_oauth_state=([^;]+)/);
  if (stateMatch && state && decodeURIComponent(stateMatch[1]) !== state) {
    return Response.redirect(`${url.origin}/dashboard.html?error=invalid_state&error_description=CSRF+state+verification+failed`, 302);
  }

  // 1. If backend URL is configured, forward callback to backend
  const backendBase = (
    env.BACKEND_URL ||
    env.KYOKA_BACKEND_URL ||
    ''
  ).replace(/\/+$/, '');

  if (backendBase) {
    try {
      const backendUrl = `${backendBase}/api/auth/callback${url.search}`;
      const backendRes = await fetch(backendUrl, {
        method: 'GET',
        headers: request.headers,
        redirect: 'manual',
      });
      const headers = new Headers(backendRes.headers);
      return new Response(backendRes.body, {
        status: backendRes.status,
        headers: headers,
      });
    } catch (backendErr) {
      console.warn('Backend proxy failed, attempting edge fallback:', backendErr);
    }
  }

  // 2. Edge Direct OAuth2 Token Exchange
  const clientId = env.DISCORD_CLIENT_ID || env.CLIENT_ID || '1562505487214321714';
  const clientSecret = env.DISCORD_CLIENT_SECRET || env.CLIENT_SECRET;

  if (!clientSecret) {
    // Helpful Aizen explanation card when secret is not yet set in Cloudflare Pages dashboard
    const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>KYOKA 3.0 — OAuth Authorization Pending Secret</title>
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
    <h2 style="color: #fff; margin-bottom: 0.75rem;">Authorization Code Exchanged</h2>
    <p style="color: #94a3b8; font-size: 0.95rem; line-height: 1.6;">
      Discord successfully authorized your account! To complete secure authentication at the edge, add <code>DISCORD_CLIENT_SECRET</code> to your Cloudflare Pages (or Render) environment variables.
    </p>
    <div class="code-box">
      <strong>Your Registered Redirect URI:</strong><br>
      <span style="color: #c084fc;">${url.origin}/api/auth/callback</span>
    </div>
    <div style="display: flex; gap: 1rem; justify-content: center;">
      <a href="/dashboard.html" class="btn btn-primary">Return to Dashboard</a>
      <a href="https://discord.gg/7q4tn6dA6V" target="_blank" class="btn btn-discord">Support Discord</a>
    </div>
  </div>
</body>
</html>`;
    return new Response(html, {
      status: 200,
      headers: { 'Content-Type': 'text/html; charset=utf-8' },
    });
  }

  try {
    const tokenParams = new URLSearchParams({
      client_id: clientId,
      client_secret: clientSecret,
      grant_type: 'authorization_code',
      code: code,
      redirect_uri: `${url.origin}/api/auth/callback`,
    });

    const tokenRes = await fetch('https://discord.com/api/oauth2/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: tokenParams.toString(),
    });

    if (!tokenRes.ok) {
      const errText = await tokenRes.text();
      return Response.redirect(`${url.origin}/dashboard.html?error=token_exchange_failed&error_description=${encodeURIComponent(errText)}`, 302);
    }

    const tokenData = await tokenRes.json();
    const userRes = await fetch('https://discord.com/api/users/@me', {
      headers: { Authorization: `Bearer ${tokenData.access_token}` },
    });

    if (!userRes.ok) {
      return Response.redirect(`${url.origin}/dashboard.html?error=user_fetch_failed`, 302);
    }

    const userData = await userRes.json();
    const avatarUrl = userData.avatar
      ? `https://cdn.discordapp.com/avatars/${userData.id}/${userData.avatar}.png`
      : `https://cdn.discordapp.com/embed/avatars/${parseInt(userData.discriminator || '0') % 5}.png`;

    const sessionPayload = {
      user_id: userData.id,
      username: userData.username,
      discriminator: userData.discriminator,
      global_name: userData.global_name || userData.username,
      avatar_url: avatarUrl,
      access_token: tokenData.access_token,
      expires_at: Date.now() + (tokenData.expires_in || 604800) * 1000,
    };

    const sessionStr = btoa(JSON.stringify(sessionPayload));
    const isHttps = url.protocol === 'https:';
    const cookie = `kyoka_session=${sessionStr}; Path=/; Max-Age=${7 * 86400}; SameSite=Lax${isHttps ? '; Secure' : ''}`;

    return new Response(null, {
      status: 302,
      headers: {
        'Location': `${url.origin}/dashboard.html#token=${encodeURIComponent(sessionStr)}`,
        'Set-Cookie': cookie,
      },
    });
  } catch (err) {
    return Response.redirect(`${url.origin}/dashboard.html?error=internal_error&error_description=${encodeURIComponent(err.message)}`, 302);
  }
}
