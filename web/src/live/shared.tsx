// Small helpers shared by the two live apps.
import { useEffect, useState } from 'react';

/** A remembered value (who is signed in, per browser). Works without storage too. */
export function useRemembered(key: string): [string | null, (value: string | null) => void] {
  const [value, setValue] = useState<string | null>(() => {
    try {
      return window.localStorage.getItem(key);
    } catch {
      return null;
    }
  });
  const set = (next: string | null) => {
    setValue(next);
    try {
      if (next === null) window.localStorage.removeItem(key);
      else window.localStorage.setItem(key, next);
    } catch {
      // storage blocked: the sign-in just isn't remembered
    }
  };
  return [value, set];
}

/** Hash routing inside one app (#/messages ...). */
export function useHashRoute(routes: readonly string[], fallback: string): [string, (route: string) => void] {
  const read = () => {
    const path = window.location.hash.replace(/^#/, '') || fallback;
    return routes.includes(path) ? path : fallback;
  };
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const onChange = () => {
      setRoute(read());
      window.scrollTo(0, 0);
    };
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const go = (next: string) => {
    window.location.hash = next;
  };
  return [route, go];
}

const AUD = new Intl.NumberFormat('en-AU', { style: 'currency', currency: 'AUD' });
export const money = (n: number) => AUD.format(n);

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
/** "2026-11-18T14:00:00" -> "18 Nov, 2:00 pm"; "2026-11-15" -> "15 Nov". */
export function friendly(iso: string | null | undefined): string {
  if (!iso) return '';
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/.exec(iso);
  if (!m) return iso;
  const day = `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]}`;
  if (m[4] === undefined) return day;
  const h = Number(m[4]);
  return `${day}, ${h % 12 || 12}:${m[5]} ${h < 12 ? 'am' : 'pm'}`;
}

/** The time of day, for "Good morning". The demo clock is 16 Nov 2026 10:00. */
export function greeting(nowIso: string | undefined): string {
  const h = nowIso ? Number(nowIso.slice(11, 13)) : 10;
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
}
