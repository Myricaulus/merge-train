# ---------------------------------------------------------------- Syntax

SONDER = {".razor": "html", ".cshtml": "html", ".vue": "html", ".svelte": "html",
          ".conf": "ini", ".service": "ini", ".desktop": "ini", ".webmanifest": "json"}

SHEBANG = {"python": "python", "bash": "bash", "sh": "bash", "zsh": "bash", "dash": "bash",
           "fish": "fish", "node": "javascript", "perl": "perl", "ruby": "ruby", "lua": "lua",
           "php": "php", "awk": "awk", "gawk": "awk", "pwsh": "powershell"}

_LEXER = {}

def lexer_fuer(pfad, text=None):
    """Lexer nach Dateiname, ohne passende Endung nach der Shebang-Zeile.
    Je Endung gemerkt: die Suche über alle Pygments-Plugins kostet sonst ~6 ms pro Datei."""
    if not PYGMENTS:
        return None
    ext = os.path.splitext(pfad)[1].lower()
    kw = dict(stripnl=False, ensurenl=False)
    schl = ext if ext else os.path.basename(pfad).lower()  # Makefile, Dockerfile …
    if schl in _LEXER and _LEXER[schl] is not None:
        return _LEXER[schl]
    if schl not in _LEXER:
        try:
            _LEXER[schl] = get_lexer_by_name(SONDER[ext], **kw) if ext in SONDER else get_lexer_for_filename(pfad, **kw)
            return _LEXER[schl]
        except ClassNotFound:
            _LEXER[schl] = None
    erste = (text or "").split("\n", 1)[0]
    if erste.startswith("#!"):
        teile = erste[2:].split()
        if teile and os.path.basename(teile[0]) == "env":  # env [-S …] programm
            teile = [t for t in teile[1:] if not t.startswith("-")]
        prog = os.path.basename(teile[0]) if teile else ""
        prog = re.sub(r"[\d.]+$", "", prog)  # python3.14 → python
        if prog in SHEBANG:
            try:
                return get_lexer_by_name(SHEBANG[prog], **kw)
            except ClassNotFound:
                pass
    return None

_KLASSE = {}

def klasse(tt):
    k = _KLASSE.get(tt)
    if k is None:
        k = _KLASSE[tt] = _klasse(tt)
    return k

def _klasse(tt):
    if not PYGMENTS: return ""
    if tt in T.Comment: return "tc"
    if tt in T.String or tt in T.Literal.String: return "ts"
    if tt in T.Number: return "tn"
    if tt in T.Keyword: return "tk"
    if tt in T.Name.Tag: return "tt"
    if tt in T.Name.Attribute: return "ta"
    if tt in T.Name.Function or tt in T.Name.Class: return "tf"
    if tt in T.Name.Builtin or tt in T.Name.Decorator: return "tb"
    if tt in T.Name.Variable: return "tv"
    if tt in T.Operator: return "to"
    if tt in T.Generic.Heading or tt in T.Generic.Subheading: return "tk"
    return ""

_VORAB = {}

def zeilen_tokens(text, pfad):
    """Ganze Datei lexen (damit mehrzeilige Kommentare/Strings stimmen),
    Ergebnis: Liste je Zeile von (klasse, text)."""
    if text is not None and (pfad, text) in _VORAB:
        return _VORAB.pop((pfad, text))
    lx = lexer_fuer(pfad, text)
    if lx is None or text is None or len(text) > 2_000_000:
        return None
    zeilen, akt = [], []
    for tt, wert in lx.get_tokens(text):
        k = klasse(tt)
        teile = wert.split("\n")
        for i, t in enumerate(teile):
            if i:
                zeilen.append(akt); akt = []
            if t:
                akt.append((k, t))
    zeilen.append(akt)
    return zeilen

def darstellen(toks, roh, bereiche, tag):
    """Zeile als HTML: Syntaxklassen + markierte Änderungsbereiche (tag = del/ins)."""
    if toks is None or "".join(t for _, t in toks) != roh:
        toks = [("", roh)]
    grenzen = sorted({0, len(roh), *[x for b in bereiche for x in b]})
    def geaendert(p):
        return any(a <= p < b for a, b in bereiche)
    out, pos = [], 0
    for k, t in toks:
        ende = pos + len(t)
        schnitte = [g for g in grenzen if pos < g < ende]
        start = pos
        for g in schnitte + [ende]:
            stueck = html.escape(roh[start:g])
            if k: stueck = f'<span class="{k}">{stueck}</span>'
            if bereiche and geaendert(start): stueck = f"<{tag}>{stueck}</{tag}>"
            out.append(stueck); start = g
        pos = ende
    return "".join(out)

def intraline(a, b):
    """Geänderte Bereiche in a und b, nur wenn sich die Zeilen ähneln."""
    if len(a) + len(b) > 4000:
        return [], []
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    if sm.ratio() < 0.5:
        return [], []
    ra, rb = [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op != "equal":
            if i2 > i1: ra.append((i1, i2))
            if j2 > j1: rb.append((j1, j2))
    return ra, rb


_AUFTRAEGE, _LEX_SPERRE = [], threading.Lock()
SERVER_SOCKET = None  # setzt server(): Lexer-Kinder schließen ihre geerbte Kopie

def _kind_start():
    """Im geforkten Lexer-Prozess: Port nicht festhalten und mit dem Elternprozess sterben (sonst bleibt der Port
    nach einem Server-Ende mitten im Lexen belegt und der neue Server startet nicht)."""
    if SERVER_SOCKET is not None:
        try:
            SERVER_SOCKET.close()
        except OSError:
            pass
    try:
        import ctypes, signal
        ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL)  # PR_SET_PDEATHSIG
    except Exception:
        pass

def _lexen(nummern):
    return [zeilen_tokens(*_AUFTRAEGE[i]) for i in nummern]  # Texte erbt das Kind beim fork, nur Nummern reisen

def vorab_lexen(auftraege):
    """Viele Dateien parallel lexen (Pygments ist reines Python, ein Kern schafft ~1 MB/s). Danach liefert
    zeilen_tokens das Ergebnis aus _VORAB. Nur bei viel Text: Prozesse anlegen kostet ~50 ms."""
    auftraege = [(t, p) for t, p in dict.fromkeys(auftraege) if t and len(t) <= 2_000_000 and lexer_fuer(p, t)]
    gesamt = sum(len(t) for t, _ in auftraege)
    kerne = min(os.cpu_count() or 1, 16)
    if gesamt < 300_000 or kerne < 2 or len(auftraege) < 2:
        return
    # gleich große Pakete (nach Textmenge), größte Dateien zuerst verteilen
    pakete = [[] for _ in range(min(kerne * 2, len(auftraege)))]
    groesse = [0] * len(pakete)
    for n in sorted(range(len(auftraege)), key=lambda n: -len(auftraege[n][0])):
        i = groesse.index(min(groesse)); pakete[i].append(n); groesse[i] += len(auftraege[n][0])
    global _AUFTRAEGE
    with _LEX_SPERRE:  # Seiten werden auch in Threads gebaut; _AUFTRAEGE gehört dem, der gerade forkt
        _AUFTRAEGE = auftraege
        try:
            _vorab_lexen(pakete, auftraege)
        except Exception:
            _VORAB.clear()  # dann eben nacheinander
        finally:
            _AUFTRAEGE = []

def _vorab_lexen(pakete, auftraege):
    import multiprocessing, warnings
    from concurrent.futures import ProcessPoolExecutor
    kerne = min(os.cpu_count() or 1, 16)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)  # fork im Server mit Threads: Kinder lexen nur
        with ProcessPoolExecutor(min(kerne, len(pakete)), mp_context=multiprocessing.get_context("fork"),
                                 initializer=_kind_start) as ex:
            for paket, erg in zip(pakete, ex.map(_lexen, pakete)):
                for n, tok in zip(paket, erg):
                    _VORAB[(auftraege[n][1], auftraege[n][0])] = tok
