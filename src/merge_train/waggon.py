"""Der Waggon: ein Vergleich Quelle → Ziel in einem lokalen Klon – ein lokales Projekt (Branch bis gegen von), ein
GitLab-Merge-Request oder ein Lauf des Myrlings, der auf eine Prüfung wartet (Skript gegen die zuletzt angesehene Fassung). Waggon ist sein Schlüssel; daraus ergeben sich Kennung, Name, Dateiname und was er kann.
von/bis eines lokalen Projekts: von_bis."""
import re
from .einstellungen import ARBEITSSTAND, BIS, KONF, VON, dateiname
from .akte import akte_lesen
from typing import NamedTuple, Optional


class Fehler(Exception):
    """Fehler mit einer Meldung für den Nutzer bzw. den Agenten (kein Programmfehler)."""


class Ungueltig(Fehler):
    """Ungültige Eingabe (Kennung, Parameter einer Anfrage): beim Server 400."""


def zweige_standard(projekt):
    """von/bis eines lokalen Projekts laut Einstellung: [zweige."<projekt>"] vor von/bis."""
    eigen = (KONF.get("zweige") or {}).get(projekt) or {}
    return eigen.get("von") or VON, eigen.get("bis") or BIS


def zweige_gewaehlt(projekt):
    """Auf der Seite (aufgeklappter Waggon) gewähltes {von, bis}, leer = Standard."""
    return akte_lesen(Waggon(lokal=projekt)).get("zweige") or {}


def von_bis(projekt):
    """(von, bis) eines lokalen Projekts: auf der Seite gewählt vor der Einstellung (zweige_standard)."""
    von, bis = zweige_standard(projekt)
    g = zweige_gewaehlt(projekt)
    return g.get("von") or von, g.get("bis") or bis


def fertig_moeglich(projekt):
    """„fertig“ setzt den Branch von – nur bei lokalen Branches, nicht gegen origin/… oder den Arbeitsstand."""
    von, bis = von_bis(projekt)
    return bis != ARBEITSSTAND and not von.startswith(("origin/", "refs/remotes/"))


class Waggon(NamedTuple):
    lokal: Optional[str] = None    # Name des lokalen Projekts – oder der MR:
    host: Optional[str] = None     # None = Standardhost von glab
    projekt: Optional[str] = None  # gruppe/projekt
    iid: Optional[int] = None
    myrling: Optional[str] = None  # oder ein Lauf des Myrlings: Name des Skripts (nas-lauf --anstehend)

    @classmethod
    def aus_id(cls, kennung):
        """Kennung (wie sie die Seite und der Agent nennen) → Waggon. „projekt:name“ = lokales Projekt, sonst
        „myrling:skript“ = Lauf des Myrlings, sonst „host/gruppe/projekt/42“."""
        kennung = str(kennung)
        if kennung.startswith("myrling:"):
            name = kennung[len("myrling:"):]
            if not re.fullmatch(r"[\w][\w.+-]*", name) or ".." in name:
                raise Ungueltig(f"ungültige Myrling-Kennung: {kennung}")
            return cls(myrling=name)
        if kennung.startswith("projekt:"):
            name = kennung[len("projekt:"):]
            if not name or any(t in ("", ".", "..") for t in name.split("/")):
                raise Ungueltig(f"ungültige Projekt-Kennung: {kennung}")
            return cls(lokal=name)
        teile = kennung.split("/")
        if len(teile) < 3 or not teile[-1].isdigit() or not re.fullmatch(r"[\w.:-]*", teile[0]) \
           or any(t in ("", ".", "..") for t in teile[1:-1]):
            raise Ungueltig(f"ungültige MR-Kennung: {kennung}")
        return cls(host=teile[0], projekt="/".join(teile[1:-1]), iid=int(teile[-1]))

    @classmethod
    def aus_dict(cls, d):
        """Aus dem Feld „mr“ einer Akte."""
        if d.get("lokal"):
            return cls(lokal=d["lokal"])
        if d.get("myrling"):
            return cls(myrling=d["myrling"])
        return cls(host=d["host"], projekt=d["projekt"], iid=d["iid"])

    def als_dict(self):
        if self.lokal:
            return {"lokal": self.lokal}
        if self.myrling:
            return {"myrling": self.myrling}
        return {"host": self.host, "projekt": self.projekt, "iid": self.iid}

    @property
    def ist_mr(self):
        return not (self.lokal or self.myrling)

    @property
    def id(self):
        if self.lokal:
            return "projekt:" + self.lokal
        if self.myrling:
            return "myrling:" + self.myrling
        return f"{self.host}/{self.projekt}/{self.iid}"

    @property
    def name(self):
        return self.lokal or self.myrling or f"{self.projekt}!{self.iid}"

    @property
    def url(self):
        """Pfad der Seite auf dem Server."""
        if self.lokal:
            return "/" + dateiname(self.lokal)
        if self.myrling:
            return "/myrling/" + self.myrling
        return "/mr/" + self.id

    @property
    def dateiname(self):
        """Name (ohne Endung) für Dateien zu diesem Waggon."""
        if self.lokal:
            return dateiname(self.lokal)[:-5]
        if self.myrling:
            return self.myrling
        return re.sub(r"[^\w.-]", "_", f"{self.host or 'gitlab'}_{self.projekt}_{self.iid}")

    @property
    def kann(self):
        """review    – Review-Kommentare und Agent-Hinweise, „Review abschließen“ überträgt sie nach GitLab
        fertig    – „fertig ✓“ setzt den Ziel-Branch auf den gesehenen Stand
        committen – der Agent darf Wünsche umsetzen und committen (sonst nur antworten)
        Myrling: der Agent im Repo des Skripts darf es ändern; die Entscheidung über den Lauf trifft der Nutzer."""
        if self.lokal:
            return {"review": False, "fertig": fertig_moeglich(self.lokal), "committen": True}
        if self.myrling:
            return {"review": False, "fertig": False, "committen": True}
        return {"review": True, "fertig": False, "committen": False}
