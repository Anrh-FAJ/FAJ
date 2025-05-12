import sqlite3
import psycopg2
import pandas as pd

# Connexion à la base SQLite
sqlite_conn = sqlite3.connect("FAJ2.db")

tables = ["users", "activities", "commentaire_journalier", "durees"]
data = {table: pd.read_sql_query(f"SELECT * FROM {table}", sqlite_conn) for table in tables}
sqlite_conn.close()

# Connexion à PostgreSQL Render
pg_conn = psycopg2.connect(
    host="dpg-d0cq590dl3ps73eenk2g-a.frankfurt-postgres.render.com",
    port=5432,
    dbname="faj",
    user="faj_user",
    password="SLe1V7mP1IQ0T5ZMBfknmMWT3TC8GpuP"
)
pg_cursor = pg_conn.cursor()

# 1. Vider les tables
for table in reversed(tables):  # ordre inverse pour respecter les dépendances FK
    pg_cursor.execute(f"DELETE FROM {table};")

# 2. Insérer les données
for _, row in data["users"].iterrows():
    pg_cursor.execute(
        "INSERT INTO users (id, username, password, role) VALUES (%s, %s, %s, %s)",
        (row["id"], row["username"], row["password"], row["role"])
    )

for _, row in data["activities"].iterrows():
    pg_cursor.execute(
        "INSERT INTO activities (id, name) VALUES (%s, %s)",
        (row["id"], row["name"])
    )

for _, row in data["commentaire_journalier"].iterrows():
    pg_cursor.execute(
        "INSERT INTO commentaire_journalier (id, user_id, date, texte) VALUES (%s, %s, %s, %s)",
        (row["id"], row["user_id"], row["date"], row["texte"])
    )

for _, row in data["durees"].iterrows():
    pg_cursor.execute(
        "INSERT INTO durees (id, user_id, activity_id, date, heure_debut, heure_fin) VALUES (%s, %s, %s, %s, %s, %s)",
        (row["id"], row["user_id"], row["activity_id"], row["date"], row["heure_debut"], row["heure_fin"])
    )

pg_conn.commit()
pg_cursor.close()
pg_conn.close()

print("✅ Données migrées avec succès vers PostgreSQL Render.")
