"""Forgiving search: 'calc', 'clc', 'ms word', 'vsc' (initials) all find things."""

SEPARATORS = " -_.()[]"


def _token_score(t, name):
    if not t:
        return 0
    if name.startswith(t):
        return 1000 - len(name)
    idx = name.find(t)
    if idx >= 0:
        bonus = 120 if name[idx - 1] in SEPARATORS else 0
        return 800 + bonus - idx * 4 - len(name) * 0.2
    words = [w for w in "".join(c if c not in SEPARATORS else " " for c in name).split() if w]
    initials = "".join(w[0] for w in words)
    if initials.startswith(t):
        return 700 - len(name) * 0.2
    # letters in order, with gaps allowed
    pos, gaps, first = -1, 0, None
    for ch in t:
        nxt = name.find(ch, pos + 1)
        if nxt < 0:
            return None
        if first is None:
            first = nxt
        gaps += nxt - pos - 1 if pos >= 0 else 0
        pos = nxt
    return 400 - gaps * 6 - first * 2 - len(name) * 0.2


def score(query, name):
    """Higher is better; None means 'no match'."""
    q = query.lower().strip()
    n = name.lower()
    if not q:
        return 0
    total = 0
    for t in q.split():
        s = _token_score(t, n)
        if s is None:
            return None
        total += s
    return total


def rank(query, entries, key=lambda e: e[0], limit=50):
    scored = []
    for e in entries:
        s = score(query, key(e))
        if s is not None:
            scored.append((s, key(e).lower(), e))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [e for _s, _n, e in scored[:limit]]
