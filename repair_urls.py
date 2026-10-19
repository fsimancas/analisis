import sqlite3
import re

conn = sqlite3.connect('betplay_flashscore.db')
c = conn.cursor()

# 1. Corregir enlaces duplicados en partidos
c.execute("""
UPDATE partidos 
SET link = replace(link, 'https://www.flashscore.cohttps://www.flashscore.co', 'https://www.flashscore.co')
WHERE link LIKE '%flashscore.cohttps%';
""")
print(f"Partidos con enlace corregido: {c.rowcount}")

# 2. Corregir cualquier otra posible variante de duplicación
c.execute("""
UPDATE partidos 
SET link = replace(link, 'https://www.flashscore.cohttps//', 'https://')
WHERE link LIKE '%flashscore.cohttps//%';
""")
print(f"Partidos con enlace sin dos puntos corregido: {c.rowcount}")

# 3. Limpiar checkpoints que quedaron en error debido al enlace roto previo
c.execute("""
DELETE FROM checkpoints_detalles_partidos 
WHERE estado = 'error' AND error LIKE '%ERR_NAME_NOT_RESOLVED%';
""")
print(f"Checkpoints de error reseteados para reintento limpio: {c.rowcount}")

conn.commit()

# Verificación
c.execute("SELECT count(*) FROM partidos WHERE link LIKE '%flashscore.cohttps%';")
bad_remain = c.fetchone()[0]
print(f"Enlaces corruptos restantes en DB: {bad_remain}")

conn.close()
print("✓ Base de datos saneada con éxito.")
