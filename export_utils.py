import pandas as pd
import psycopg2.extras
from datetime import datetime
from calendar import monthrange
import xlsxwriter   # déjà tiré automatiquement par pandas

# --------- 1) Récap global ---------------------------
def get_monthly_summary_dataframe(conn, month: int, year: int) -> pd.DataFrame:
    """
    Retourne un DataFrame : activité | minutes | HH:MM
    On laisse le CALLER fermer le 'conn'.
    """
    sql = """
        SELECT a.name AS activité,
               EXTRACT(EPOCH FROM (d.heure_fin - d.heure_debut))/60 AS minutes
        FROM durees d
        JOIN activities a ON a.id = d.activity_id
        WHERE d.heure_debut IS NOT NULL
          AND d.heure_fin   IS NOT NULL
          AND EXTRACT(MONTH FROM d.date) = %s
          AND EXTRACT(YEAR  FROM d.date) = %s
    """
    df = pd.read_sql(sql, conn, params=(month, year))

    if df.empty:
        return pd.DataFrame(columns=["Activité", "Minutes", "HH:MM"])

    total = (
        df.groupby("activité", as_index=False)["minutes"]
        .sum()
        .assign(**{
            "HH:MM": lambda x: x["minutes"].apply(
                lambda m: f"{int(m)//60:02d}:{int(m)%60:02d}")
        })
    )
    total = total.rename(columns={"minutes": "Minutes", "activité": "Activité"})
    return total[["Activité", "Minutes", "HH:MM"]]


# --------- 2) Récap par utilisateur ------------------
def get_user_activity_summary_dataframe(conn, year: int, month: int) -> pd.DataFrame:
    """
    Retourne un pivot prêt à afficher :
    index = Utilisateur, colonnes = Activité, valeurs = HH:MM
    """
    date_debut = f"{year}-{month:02d}-01"
    date_fin   = f"{year}-{month:02d}-{monthrange(year, month)[1]}"

    sql = """
        SELECT u.username  AS utilisateur,
               a.name      AS activité,
               EXTRACT(EPOCH FROM (d.heure_fin - d.heure_debut))/60 AS minutes
        FROM durees d
        JOIN users      u ON u.id = d.user_id
        JOIN activities a ON a.id = d.activity_id
        WHERE d.heure_debut IS NOT NULL
          AND d.heure_fin   IS NOT NULL
          AND d.date BETWEEN %s AND %s
    """
    df = pd.read_sql(sql, conn, params=(date_debut, date_fin))

    if df.empty:
        return pd.DataFrame()

    # agrégation propre : un utilisateur peut avoir plusieurs lignes pour une activité
    df = (
        df.groupby(["utilisateur", "activité"], as_index=False)["minutes"]
        .sum()
        .assign(**{
            "HH:MM": lambda x: x["minutes"].apply(
                lambda m: f"{int(m)//60:02d}:{int(m)%60:02d}")
        })
    )

    pivot = (
        df.pivot(index="utilisateur", columns="activité", values="HH:MM")
        .fillna("00:00")
        .reset_index()
        .rename(columns={"utilisateur": "Utilisateur"})
    )

    return pivot

def export_to_excel(df: pd.DataFrame, path: str, *, sheet_name: str = "Feuille1") -> None:
    """
    Exporte le DataFrame vers un fichier Excel.
    - Supprime la colonne 'Minutes' brute si elle existe.
    - Crée le classeur avec xlsxwriter.
    """
    if "Minutes" in df.columns:
        df = df.drop(columns=["Minutes"])

    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)