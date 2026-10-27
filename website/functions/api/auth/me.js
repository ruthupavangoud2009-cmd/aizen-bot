/**
 * Cloudflare Pages Function: /api/auth/me
 * Returns current authenticated user profile from session cookie or bearer token.
 */

export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);

  // Read session from Cookie or Authorization header
  let sessionStr = null;
  const cookieHeader = request.headers.get('Cookie') || '';
  const match = cookieHeader.match(/kyoka_session=([^;]+)/);
  if (match) {
    sessionStr = decodeURIComponent(match[1]);
  }
  const authHeader = request.headers.get('Authorization') || '';
  if (!sessionStr && authHeader.startsWith('Bearer ')) {
    sessionStr = authHeader.substring(7).trim();
  }

  // If no edge session, forward to backend if configured
  if (!sessionStr) {
    const backendBase = (
      env.BACKEND_URL ||
      env.KYOKA_BACKEND_URL ||
      'https://kyokasugisetsu.onrender.com'
    ).replace(/\/+$/, '');

    if (backendBase) {
      try {
        const backendRes = await fetch(`${backendBase}/api/auth/me`, {
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

    return new Response(JSON.stringify({ authenticated: false, user: null }), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': url.origin,
        'Access-Control-Allow-Credentials': 'true',
      },
    });
  }

  try {
    const raw = sessionStr.includes('.') ? sessionStr.split('.')[0] : sessionStr;
    const padding = '='.repeat((4 - (raw.length % 4)) % 4);
    const session = JSON.parse(atob(raw + padding));
    if (session.expires_at && Date.now() > session.expires_at) {
      return new Response(JSON.stringify({ authenticated: false, user: null, expired: true }), {
        status: 200,
        headers: {
          'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': url.origin,
          'Access-Control-Allow-Credentials': 'true',
        },
      });
    }

    const OWNER_ID = '1505515188991033409';
    const isOwner = String(session.user_id) === OWNER_ID;

    // Authorized staff whitelist (PostgreSQL synced and fallback)
    const KNOWN_STAFF_IDS = new Set([
      '1505515188991033409', // Authoritative Bot Owner
      '1532660258403647687', // mrhowler01 (Administrator)
    ]);
    const KNOWN_STAFF_NAMES = new Set(['mrhowler01', 'aizen', 'ruthupavan']);

    const isStaff = isOwner ||
      Boolean(session.is_staff) ||
      KNOWN_STAFF_IDS.has(String(session.user_id)) ||
      KNOWN_STAFF_NAMES.has(String(session.username || '').toLowerCase());

    const staffRole = isOwner ? 'admin' : (session.staff_role || (isStaff ? 'admin' : null));

    return new Response(JSON.stringify({
      authenticated: true,
      user: {
        id: session.user_id,
        username: session.username,
        discriminator: session.discriminator || '0',
        global_name: session.global_name || session.username,
        avatar_url: session.avatar_url,
        is_owner: isOwner,
        is_staff: isStaff,
        staff_role: staffRole,
      },
    }), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': url.origin,
        'Access-Control-Allow-Credentials': 'true',
      },
    });
  } catch (err) {
    return new Response(JSON.stringify({ authenticated: false, user: null }), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': url.origin,
        'Access-Control-Allow-Credentials': 'true',
      },
    });
  }
}
