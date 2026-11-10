"""Prüft: jeder globale Name, den eine Funktion lädt, ist in ihrem Modul bekannt (findet vergessene Imports, die die
Tests nicht treffen). Aufruf aus der Repo-Wurzel nach ./bauen:

  MERGE_TRAIN_CONFIG=/nonexistent python3 werkzeug/namen_pruefen.py merge-train
"""
import builtins, dis, importlib, pkgutil, sys, types

sys.path.insert(0, sys.argv[1])
import merge_train


def codes(c):
    yield c
    for k in c.co_consts:
        if isinstance(k, types.CodeType):
            yield from codes(k)


fehler = 0
for info in pkgutil.iter_modules(merge_train.__path__):
    m = importlib.import_module("merge_train." + info.name)
    quelltext = m.__loader__.get_source(m.__name__)
    for c in codes(compile(quelltext, info.name, "exec")):
        for i in dis.get_instructions(c):
            if i.opname in ("LOAD_GLOBAL", "LOAD_NAME") and i.argval not in vars(m) and not hasattr(builtins, i.argval):
                print(f"{info.name}: {c.co_name}: {i.argval}")
                fehler += 1
print("fehlende Namen:", fehler)
sys.exit(1 if fehler else 0)
