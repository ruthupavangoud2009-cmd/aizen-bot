/**
 * Cloudflare Pages Function: /api/staff/manage
 * Adds or removes website staff members with persistent cookie + backend sync.
 */

const DEFAULT_STAFF = [
  {
    user_id: '1505515188991033409',
    username: 'Aizen (ruthupavan)',
    role_level: 'admin',
    added_by: '1505515188991033409',
    added_at: '2026-01-01T00:00:00Z',
  },
  {
    user_id: '1532660258403647687',
    username: 'mrhowler01',
    role_level: 'admin',
    added_by: '1505515188991033409',
    added_at: '2026-10-27T11:46:50Z',
  },
];

function getStaffFromCookie(cookieHeader) {
  if (!cookieHeader) return [...DEFAULT_STAFF];
  const match = cookieHeader.match(/kyoka_staff_registry=([^;]+)/);
  if (!match) return [...DEFAULT_STAFF];
  try {
    const raw = decodeURIComponent(match[1]);
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      // Merge defaults with parsed
      const map = new Map();
      for (const s of DEFAULT_STAFF) map.set(String(s.user_id), s);
      for (const s of parsed) {
        if (s && s.user_id) map.set(String(s.user_id), s);
      }
      return Array.from(map.values());
    }
  } catch {}
  return [...DEFAULT_STAFF];
}

export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);

  if (request.method !== 'POST') {
    return new Response(JSON.stringify({ error: 'Method Not Allowed' }), {
      status: 405,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': url.origin,
      },
    });
  }

  let body = {};
  try {
    body = await request.json();
  } catch {}

  const action = String(body.action || 'add').toLowerCase().trim();
  const targetId = String(body.user_id || '').trim();
  const username = String(body.username || `Staff_${targetId}`).trim();
  const roleLevel = String(body.role_level || 'support').toLowerCase().trim();

  if (!targetId || targetId === 'Unknown') {
    return new Response(JSON.stringify({ success: false, error: 'Valid user_id is required.' }), {
      status: 400,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': url.origin,
      },
    });
  }

  // Attempt proxying to Render backend if active
  const backendBase = (
    env.BACKEND_URL ||
    env.KYOKA_BACKEND_URL ||
    'https://kyokasugisetsu.onrender.com'
  ).replace(/\/+$/, '');

  if (backendBase) {
    try {
      const res = await fetch(`${backendBase}/api/staff/manage`, {
        method: 'POST',
        headers: {
          ...request.headers,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        const data = await res.json();
        // Fall through to also update edge cookie
      }
    } catch {}
  }

  // Update edge roster registry
  const cookieHeader = request.headers.get('Cookie') || '';
  let staffList = getStaffFromCookie(cookieHeader);

  if (action === 'remove') {
    if (targetId === '1505515188991033409') {
      return new Response(JSON.stringify({ success: false, error: 'Cannot remove authoritative Bot Owner.' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': url.origin },
      });
    }
    staffList = staffList.filter(s => String(s.user_id) !== targetId);
  } else {
    // Add or update
    const existingIndex = staffList.findIndex(s => String(s.user_id) === targetId);
    const newEntry = {
      user_id: targetId,
      username: username || `Staff_${targetId}`,
      role_level: roleLevel,
      added_by: '1505515188991033409',
      added_at: new Date().toISOString(),
    };
    if (existingIndex >= 0) {
      staffList[existingIndex] = { ...staffList[existingIndex], ...newEntry };
    } else {
      staffList.push(newEntry);
    }
  }

  const encodedCookie = encodeURIComponent(JSON.stringify(staffList));
  const setCookie = `kyoka_staff_registry=${encodedCookie}; Path=/; Max-Age=315360000; SameSite=Lax; Secure`;

  return new Response(
    JSON.stringify({
      success: true,
      message: action === 'remove'
        ? `Removed staff member ${targetId}.`
        : `Granted '${roleLevel}' role to ${username}.`,
      staff: staffList,
      total: staffList.length,
    }),
    {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': url.origin,
        'Access-Control-Allow-Credentials': 'true',
        'Set-Cookie': setCookie,
      },
    }
  );
}
