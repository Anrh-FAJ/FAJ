import pandas as pd
import psycopg2.extras
from datetime import datetime

def get_monthly_summary_dataframe(conn, month, year):
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    query = """
        SELECT a.name AS activité, 
               SUM(EXTRACT(EPOCH FROM (d.heure_fin - d.heure_debut)) / 60) AS total_minutes
        FROM durees d
        JOIN activities a ON d.activity_id = a.id
        WHERE EXTRACT(MONTH FROM d.date) = %s AND EXTRACT(YEAR FROM d.date) = %s
        GROUP BY a.name
        ORDER BY a.name;
    """

    cursor.execute(query, (month, year))
    rows = cursor.fetchall()
    conn.close()

    df = pd.DataFrame(rows, columns=["Activité", "Total (minutes)"])

    def minutes_to_hhmm(mins):
        heures = int(mins) // 60
        minutes = int(mins) % 60
        return f"{heures:02d}:{minutes:02d}"

    if not df.empty:
        df["Durée (HH:MM)"] = df["Total (minutes)"].apply(minutes_to_hhmm)

    return df


def export_to_excel(df, path, sheet_name="Feuille1"):
    # Supprime la colonne des minutes si elle existe
    if "Total (minutes)" in df.columns:
        df = df.drop(columns=["Total (minutes)"])

    # Exporte vers Excel avec nom de feuille personnalisé
    with pd.ExcelWriter(path, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)

def get_user_activity_summary_dataframe(conn, year: int, month: int):
    import pandas as pd
    from calendar import monthrange
    
    date_debut = f"{year}-{month:02d}-01"
    date_fin = f"{year}-{month:02d}-{monthrange(year, month)[1]}"
    
    query = """
        SELECT u.username AS "Utilisateur",
               a.name AS "Activité",
               CAST(EXTRACT(EPOCH FROM (d.heure_fin - d.heure_debut)) / 60 AS INTEGER) AS "Minutes"
        FROM durees d
        JOIN users u ON d.user_id = u.id
        JOIN activities a ON d.activity_id = a.id
        WHERE d.date BETWEEN %s AND %s
          AND d.heure_debut IS NOT NULL
          AND d.heure_fin IS NOT NULL
    """
    
    df = pd.read_sql_query(query, conn, params=(date_debut, date_fin))
    
    if df.empty:
        return pd.DataFrame()
    
    # Conversion des minutes en heures:minutes pour l'affichage
    df['Heures'] = df['Minutes'].apply(lambda m: f"{int(m) // 60:02d}:{int(m) % 60:02d}")
    df.drop(columns=['Minutes'], inplace=True)
    
    pivot_df = df.pivot_table(index="Utilisateur", columns="Activité", values="Heures", 
                             aggfunc="first", fill_value="00:00")
    pivot_df = pivot_df.reset_index()
    
    return pivot_df
