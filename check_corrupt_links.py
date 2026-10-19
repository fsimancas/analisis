import sqlite3

conn = sqlite3.connect('betplay_flashscore.db')
c = conn.cursor()
c.execute("SELECT id, link FROM partidos WHERE link LIKE '%flashscore.cohttps%' LIMIT 10;")
rows = c.fetchall()
print(f"Total encontrados con 'flashscore.cohttps': {len(rows)}")
for r in rows:
    print(r)

c.execute("SELECT count(*) FROM partidos WHERE link LIKE '%https://www.flashscore.cohttps%';")
count_bad = c.fetchone()[0]
print(f"Total registros corruptos en toda la tabla partidos: {count_bad}")

c.execute("SELECT id, link FROM partidos WHERE id = 'fulq13RF';")
print("Partido fulq13RF:", c.fetchall())

conn.close()
