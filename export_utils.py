import pandas as pd
import psycopg2.extras
from datetime import datetime
from calendar import monthrange
import xlsxwriter   # déjà tiré automatiquement par pandas

# ──────────────────────────────────────────────────────────
# 1) RÉCAPITULATIF MENSUEL GLOBAL (toutes activités)
# ──────────────────────────────────────────────────────────
def get_monthly_summary_dataframe(conn, month: int, year: int) -> pd.DataFrame:
    """
    Retourne un DataFrame avec, pour chaque activité, la somme des minutes
    saisies sur le mois/année demandés.
    """
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute(
        """
        SELECT a.name   AS Activité,
               SUM(EXTRACT(EPOCH FROM (d.heure_fin - d.heure_debut)) / 60) AS Minutes
        FROM   durees d
        JOIN   activities a ON a.id = d.activity_id
        WHERE  EXTRACT(MONTH FROM d.date) = %s
          AND  EXTRACT(YEAR  FROM d.date) = %s
          AND  d.heure_debut IS NOT NULL
          AND  d.heure_fin   IS NOT NULL
        GROUP  BY a.name
        ORDER  BY a.name;
        """,
        (month, year),
    )
    rows = cur.fetchall()
    conn.close()

    # passage en DataFrame + conversion minutes → HH:MM
    df = pd.DataFrame(rows, columns=["Activité", "Minutes"])
    if df.empty:
        return df

    df["Durée (HH:MM)"] = df["Minutes"].astype(int).apply(_mins_to_hhmm)
    return df[["Activité", "Durée (HH:MM)"]]


# ──────────────────────────────────────────────────────────
# 2) RÉCAPITULATIF MENSUEL PAR COLLABORATEUR
# ──────────────────────────────────────────────────────────
def get_user_activity_summary_dataframe(conn: psycopg2.extensions.connection,
                                        year: int, month: int) -> pd.DataFrame:
    from calendar import monthrange
    date_debut = f"{year}-{month:02d}-01"
    date_fin   = f"{year}-{month:02d}-{monthrange(year, month)[1]}"

    query = """
        SELECT u.username AS utilisateur,          -- ⚠ identifiants en minuscules
               a.name      AS activite,
               CAST(EXTRACT(EPOCH FROM (d.heure_fin - d.heure_debut)) / 60 AS INTEGER) AS minutes
        FROM   durees d
        JOIN   users      u ON u.id = d.user_id
        JOIN   activities a ON a.id = d.activity_id
        WHERE  d.date BETWEEN %s AND %s
          AND  d.heure_debut IS NOT NULL
          AND  d.heure_fin   IS NOT NULL
    """

    df = pd.read_sql_query(query, conn, params=(date_debut, date_fin))
    if df.empty:
        return pd.DataFrame()

    # ── Agrégation exacte minutes par (utilisateur, activité)
    df_agg = (
        df.groupby(["utilisateur", "activite"])["minutes"]
          .sum()
          .reset_index()
    )
    df_agg["heures"] = df_agg["minutes"].apply(_mins_to_hhmm)

    pivot_df = (
        df_agg.pivot_table(index="utilisateur",
                           columns="activite",
                           values="heures",
                           aggfunc="first",
                           fill_value="00:00")
              .reset_index()
              .rename(columns={"utilisateur": "Utilisateur"})  # ✅ ici
              .sort_values("Utilisateur")
    )
    return pivot_df




# ──────────────────────────────────────────────────────────
# 3) EXPORT EXCEL (ré-utilisé par main.py)
# ──────────────────────────────────────────────────────────
def export_to_excel(df: pd.DataFrame, path: str, sheet_name: str = "Feuille1") -> None:
    """
    Écrit le DataFrame dans un fichier Excel (xlsxwriter) sans la colonne brute
    Minutes, seulement HH:MM.
    """
    to_save = df.copy()
    if "Minutes" in to_save.columns:
        to_save.drop(columns=["Minutes"], inplace=True)

    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        to_save.to_excel(writer, index=False, sheet_name=sheet_name)


# ──────────────────────────────────────────────────────────
# 4) UTILITAIRE INTERNE
# ──────────────────────────────────────────────────────────
def _mins_to_hhmm(mins: int) -> str:
    h, m = divmod(int(mins), 60)
    return f"{h:02d}:{m:02d}"