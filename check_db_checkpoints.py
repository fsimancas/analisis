import sqlite3

conn = sqlite3.connect('betplay_flashscore.db')
c = conn.cursor()
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
print('Tablas en DB:', tables)
for t in ['checkpoints_fotmob_detalles', 'checkpoints_detalles_partidos', 'checkpoints_competiciones', 'fotmob_partidos', 'partidos']:
    if t in tables:
        cnt = c.execute(f"SELECT count(*) FROM {t};").fetchone()[0]
        print(f"\nTabla '{t}': {cnt} filas")
        if 'checkpoint' in t:
            estados = c.execute(f"SELECT estado, count(*) FROM {t} GROUP BY estado;").fetchall()
            print(f"   Estados: {estados}")

# Check Flashscore partidos: how many belong to the 44 flashscore competitions vs the 163 fotmob
c.execute("""
SELECT cf.ruta_optima, count(p.id)
FROM partidos p
JOIN competiciones_fotmob cf ON p.competicion_id = cf.competicion_id
GROUP BY cf.ruta_optima;
""")
print("\nPartidos en Flashscore distribuidos por ruta_optima:", c.fetchall())

# Check completed in checkpoints_detalles_partidos
c.execute("""
SELECT cf.ruta_optima, chk.estado, count(*)
FROM checkpoints_detalles_partidos chk
JOIN competiciones_fotmob cf ON chk.competicion_id = cf.competicion_id
GROUP BY cf.ruta_optima, chk.estado;
""")
print("\nCheckpoints Flashscore por ruta y estado:", c.fetchall())

conn.close()
