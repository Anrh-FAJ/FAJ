import psycopg2

# Informations de connexion (depuis Render)
DB_HOST = "dpg-d0cq590dl3ps73eenk2g-a.frankfurt-postgres.render.com"
DB_PORT = 5432
DB_NAME = "faj"
DB_USER = "faj_user"
DB_PASSWORD = "SLe1V7mP1IQ0T5ZMBfknmMWT3TC8GpuP"  # ⚠️ Sécurisez ce mot de passe

# Connexion à la base PostgreSQL
conn = psycopg2.connect(
    host=DB_HOST,
    port=DB_PORT,
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD
)
cursor = conn.cursor()

# Script SQL pour créer les tables
create_tables_sql = """
CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  username TEXT NOT NULL,
  password TEXT NOT NULL,
  role TEXT NOT NULL
);

CREATE TABLE activities (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL
);

CREATE TABLE commentaire_journalier (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  date DATE NOT NULL,
  texte TEXT
);

CREATE TABLE durees (
  id SERIAL PRIMARY KEY,
  user_id INTEGER REFERENCES users(id),
  activity_id INTEGER REFERENCES activities(id),
  date DATE,
  heure_debut TIME,
  heure_fin TIME
);
"""

try:
    cursor.execute(create_tables_sql)
    conn.commit()
    print("✅ Tables créées avec succès.")
except Exception as e:
    print("❌ Erreur lors de la création des tables :", e)
finally:
    cursor.close()
    conn.close()
