/** Tracking ID check (TS twin of services/core/app/core/ids.py): SM-<STATE>-<YY>-<6 chars><check>. */
const ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';
const N = ALPHABET.length;

export function normalizeTrackingId(raw: string): string {
  const cleaned = raw.trim().toUpperCase().replace(/\s+/g, '');
  const cut = cleaned.lastIndexOf('-');
  if (cut < 0) return cleaned;
  const tail = cleaned.slice(cut + 1).replace(/O/g, '0').replace(/[IL]/g, '1').replace(/U/g, 'V');
  return `${cleaned.slice(0, cut)}-${tail}`;
}

function luhnModNValid(full: string): boolean {
  let factor = 1;
  let total = 0;
  const points = [...full].filter((c) => ALPHABET.includes(c)).map((c) => ALPHABET.indexOf(c));
  for (let i = points.length - 1; i >= 0; i--) {
    const addend = factor * points[i]!;
    factor = factor === 2 ? 1 : 2;
    total += Math.floor(addend / N) + (addend % N);
  }
  return total % N === 0;
}

export function isValidTrackingId(raw: string): boolean {
  const tid = normalizeTrackingId(raw);
  const parts = tid.split('-');
  if (parts.length !== 4 || parts[0] !== 'SM' || parts[1]!.length !== 2 || parts[3]!.length !== 7) return false;
  if (!/^\d+$/.test(parts[2]!) || [...parts[3]!].some((c) => !ALPHABET.includes(c))) return false;
  return luhnModNValid(tid);
}
