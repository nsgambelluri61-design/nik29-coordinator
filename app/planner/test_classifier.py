"""
Test del classificatore euristico — verifica che SIMPLE/COMPLEX funzioni correttamente.
"""
import sys
sys.path.insert(0, "/home/ubuntu")

# Direct import bypassing __init__ (which uses app.planner path)
import importlib.util
spec = importlib.util.spec_from_file_location("planner", "/home/ubuntu/planner/planner.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
classify_message = mod.classify_message

# === TEST CASES ===
test_cases = [
    # (messaggio, risultato atteso)
    # SIMPLE
    ("ciao", "SIMPLE"),
    ("che versione sei?", "SIMPLE"),
    ("come stai?", "SIMPLE"),
    ("ok", "SIMPLE"),
    ("grazie", "SIMPLE"),
    ("cerca quanto costa un materasso Tempur", "SIMPLE"),
    ("controlla se ildormire.com è online", "SIMPLE"),
    ("fai uno screenshot del sito", "SIMPLE"),
    ("che ore sono?", "SIMPLE"),
    ("si", "SIMPLE"),

    # COMPLEX
    ("cerca i competitor di ildormire.com e preparami un report con prezzi e punti di forza", "COMPLEX"),
    ("crea un agente che monitora i prezzi dei competitor e mi avvisa quando cambiano", "COMPLEX"),
    ("fai una ricerca approfondita sui materassi in memory foam, poi crea una pagina prodotto e pubblica sul sito", "COMPLEX"),
    ("analizza il sito ildormire.com, trova i problemi SEO, correggili e poi fai un deploy", "COMPLEX"),
    ("per prima cosa controlla lo stato del server, poi aggiorna il codice, fai il build e infine deploya", "COMPLEX"),
    ("cerca le keyword migliori per materassi Reggio Calabria, crea i meta tag, aggiorna il sito e verifica con un test SEO", "COMPLEX"),
    ("implementa un sistema di notifiche push che avvisa i clienti quando un prodotto torna disponibile, con backend e frontend", "COMPLEX"),
]

print("=" * 60)
print("TEST CLASSIFICATORE PLANNER")
print("=" * 60)

passed = 0
failed = 0

for message, expected in test_cases:
    result = classify_message(message)
    status = "✅" if result == expected else "❌"
    if result != expected:
        failed += 1
        print(f"{status} EXPECTED={expected} GOT={result}")
        print(f"   MSG: {message[:80]}")
    else:
        passed += 1
        print(f"{status} {result:7s} | {message[:60]}")

print("=" * 60)
print(f"Risultati: {passed} passati, {failed} falliti su {len(test_cases)} test")
if failed == 0:
    print("🎉 Tutti i test passati!")
else:
    print(f"⚠️  {failed} test falliti — rivedere le euristiche")
