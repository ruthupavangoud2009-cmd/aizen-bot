/**
 * Cloudflare Pages Function: /api/staff/list
 * Returns registered website staff members with persistent cookie + backend sync.
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

  // If backend is configured, attempt backend query first
  const backendBase = (
    env.BACKEND_URL ||
    env.KYOKA_BACKEND_URL ||
    'https://kyokasugisetsu.onrender.com'
  ).replace(/\/+$/, '');

  let backendStaff = null;
  if (backendBase) {
    try {
      const res = await fetch(`${backendBase}/api/staff/list`, {
        headers: request.headers,
      });
      if (res.ok) {
        const data = await res.json();
        if (data.staff && Array.isArray(data.staff)) {
          backendStaff = data.staff;
        }
      }
    } catch {}
  }

  // Merge cookie staff with defaults and backend
  const cookieHeader = request.headers.get('Cookie') || '';
  const cookieStaff = getStaffFromCookie(cookieHeader);

  const finalMap = new Map();
  for (const s of cookieStaff) finalMap.set(String(s.user_id), s);
  if (backendStaff) {
    for (const s of backendStaff) finalMap.set(String(s.user_id), s);
  }

  const staff = Array.from(finalMap.values());

  return new Response(JSON.stringify({ success: true, staff, total: staff.length }), {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': url.origin,
      'Access-Control-Allow-Credentials': 'true',
    },
  });
}
