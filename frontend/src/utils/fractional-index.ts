const ALPH = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";

export function midKey(a: string | null, b: string | null): string {
  const pad = "U";
  if (!a && !b) return pad;
  if (!a) a = "";
  if (!b) return a + pad;

  let i = 0;
  while (true) {
    const ca = i < a.length ? ALPH.indexOf(a[i]) : ALPH.indexOf(pad);
    const cb = i < b.length ? ALPH.indexOf(b[i]) : ALPH.length - 1;
    
    if (ca + 1 < cb) {
      return a.slice(0, i) + ALPH[Math.floor((ca + cb) / 2)];
    }
    i++;
    if (i > Math.max(a.length, b.length) + 4) {
      return a + ALPH[1];
    }
  }
}

export function afterKey(a: string | null): string {
  if (!a) return "U";
  const last = ALPH.indexOf(a[a.length - 1]);
  if (last === -1 || last === ALPH.length - 1) {
    return a + "U";
  }
  return a.slice(0, -1) + ALPH[last + 1];
}
