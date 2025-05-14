import pandas as pd
import psycopg2.extras
from datetime import datetime

def get_monthly_summary_dataframe(conn, month, year):
    import pandas as pd

    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    query = """
        SELECT u.id AS user_id, a.name AS activité,
               EXTRACT(EPOCH FROM (d.heure_fin - d.heure_debut)) / 60 AS minutes
        FROM durees d
        JOIN activities a ON d.activity_id = a.id
        JOIN users u ON d.user_id = u.id
        WHERE 
            EXTRACT(MONTH FROM d.date) = %s 
            AND EXTRACT(YEAR FROM d.date) = %s
            AND d.heure_debut IS NOT NULL 
            AND d.heure_fin IS NOT NULL
    """

    cursor.execute(query, (month, year))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return pd.DataFrame(columns=["Activité", "Total (minutes)", "Durée (HH:MM)"])

    df = pd.DataFrame(rows, columns=["user_id", "activité", "minutes"])

    df_grouped = df.groupby("activité")["minutes"].sum().reset_index()

    def minutes_to_hhmm(mins):
        heures = int(mins) // 60
        minutes = int(mins) % 60
        return f"{heures:02d}:{minutes:02d}"

    df_grouped["Durée (HH:MM)"] = df_grouped["minutes"].apply(minutes_to_hhmm)
    df_grouped.rename(columns={"minutes": "Total (minutes)"}, inplace=True)

    return df_grouped[["activité", "Total (minutes)", "Durée (HH:MM)"]]





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
        SELECT u.username AS Utilisateur,
               a.name AS Activité,
               EXTRACT(EPOCH FROM (d.heure_fin - d.heure_debut)) / 60 AS Minutes
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

    # Agréger les minutes par utilisateur et activité
    df_agg = df.groupby(['Utilisateur', 'Activité'])['Minutes'].sum().reset_index()

    # Transformer les minutes en HH:MM
    df_agg['Heures'] = df_agg['Minutes'].apply(lambda m: f"{int(m)//60:02d}:{int(m)%60:02d}")
    df_agg.drop(columns=['Minutes'], inplace=True)

    # Pivot pour affichage par utilisateur
    pivot_df = df_agg.pivot(index="Utilisateur", columns="Activité", values="Heures").fillna("00:00").reset_index()

    return pivot_df

