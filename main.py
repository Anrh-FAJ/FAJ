from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.responses import FileResponse
from export_utils import get_monthly_summary_dataframe, export_to_excel
import tempfile
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import psycopg2
from datetime import date
from datetime import datetime
import pandas as pd  # Nécessaire pour l'export
from starlette.middleware.sessions import SessionMiddleware
from fastapi import Form
import calendar
from export_utils import get_user_activity_summary_dataframe, export_to_excel
from fastapi.routing import APIRouter

templates = Jinja2Templates(directory="templates")

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="faj2-secret-key")


# 📁 Templates et fichiers statiques
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


# 🔌 Connexion à la BDD
def get_db_connection():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL environment variable is not set.")
    
    return psycopg2.connect(db_url, cursor_factory=psycopg2.extras.DictCursor)



# 🟦 Page de connexion
@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT username FROM users ORDER BY username")
    users = cursor.fetchall()
    conn.close()
    return templates.TemplateResponse("login.html", {"request": request, "error": None, "users": users})

@app.get("/saisie", response_class=HTMLResponse)
async def saisie_home(request: Request):
    return await render_saisie_page(request)



@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users(request: Request):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""
        SELECT id, username, role FROM users
        ORDER BY 
            CASE role 
                WHEN 'admin' THEN 0 
                WHEN 'user' THEN 1 
                ELSE 2 
            END,
            username ASC
    """)
    users = cursor.fetchall()
    conn.close()
    return templates.TemplateResponse("admin_users.html", {"request": request, "users": users})


def get_user_name(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user["username"] if user else "Inconnu"


async def render_saisie_page(request: Request, error: str = None):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/", status_code=303)

    today = date.today()
    today_str = today.isoformat()

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)


    # ✅ Activités
    cursor.execute("SELECT id, name FROM activities ORDER BY name")
    activities = cursor.fetchall()

    # ✅ Récupération des saisies pour l'utilisateur et la date du jour
    cursor.execute("""
        SELECT d.id, a.name AS activity_name, d.heure_debut, d.heure_fin
        FROM durees d
        JOIN activities a ON d.activity_id = a.id
        WHERE d.date = %s AND d.user_id = %s
        ORDER BY d.heure_debut
    """, (today_str, user_id))
    rows = cursor.fetchall()

    # ✅ Traitement des résultats
    saisies = []
    total_minutes = 0
    for row in rows:
        try:
            debut = datetime.strptime(row["heure_debut"], "%H:%M")
            fin = datetime.strptime(row["heure_fin"], "%H:%M")
            duree = int((fin - debut).total_seconds() // 60)
            total_minutes += duree
            hhmm = f"{duree // 60:02}:{duree % 60:02}"
        except Exception:
            hhmm = "??:??"
        saisies.append({
            "id": row["id"],
            "activity_name": row["activity_name"],
            "heure_debut": row["heure_debut"],
            "heure_fin": row["heure_fin"],
            "duree": hhmm
        })

    total_duree = f"{total_minutes // 60:02}:{total_minutes % 60:02}"

    # ✅ Commentaire global (si existe)
    cursor.execute("""
        SELECT texte FROM commentaire_journalier
        WHERE user_id = %s AND date = %s
    """, (user_id, today_str))
    result = cursor.fetchone()
    commentaire_global = result["texte"] if result else ""

    conn.close()
    
    user_name = get_user_name(user_id)

    return templates.TemplateResponse("saisie.html", {
        "request": request,
        "activities": activities,
        "saisies": saisies,
        "total_duree": total_duree,
        "commentaire_global": commentaire_global,
        "today": today,
        "user_name": user_name,
        "error": error
    })




@app.post("/saisie/add")
async def add_saisie(request: Request, activity_id: int = Form(...), heure_debut: str = Form(...), heure_fin: str = Form(...)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/", status_code=303)

    try:
        debut = datetime.strptime(heure_debut, "%H:%M")
        fin = datetime.strptime(heure_fin, "%H:%M")
        if debut >= fin:
            return await render_saisie_page(request, error="⛔ L'heure de début doit être inférieure à l'heure de fin.")
    except ValueError:
        return await render_saisie_page(request, error="⛔ Format d'heure invalide.")

    today = date.today().isoformat()
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)


    # Vérification du chevauchement
    cursor.execute("""
        SELECT heure_debut, heure_fin FROM durees
        WHERE user_id = %s AND date = %s
    """, (user_id, today))
    existing = cursor.fetchall()
    for row in existing:
        db_debut = datetime.strptime(row["heure_debut"], "%H:%M")
        db_fin = datetime.strptime(row["heure_fin"], "%H:%M")
        if not (fin <= db_debut or debut >= db_fin):
            conn.close()
            return await render_saisie_page(request, error="⛔ Chevauchement avec une autre saisie.")

    # Insertion
    cursor.execute("""
        INSERT INTO durees (user_id, activity_id, date, heure_debut, heure_fin)
        VALUES (%s, %s, %s, %s, %s)
    """, (user_id, activity_id, today, heure_debut, heure_fin))
    conn.commit()
    conn.close()

    return RedirectResponse("/saisie", status_code=303)




@app.post("/saisie/commentaire")
async def ajouter_commentaire(request: Request, commentaire: str = Form(...)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/", status_code=303)

    today = date.today().isoformat()
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)


    # On vérifie s'il existe déjà un commentaire
    cursor.execute("""
        SELECT id FROM commentaire_journalier
        WHERE user_id = %s AND date = %s
    """, (user_id, today))
    existing = cursor.fetchone()

    if existing:
        # Mise à jour si déjà existant
        cursor.execute("""
            UPDATE commentaire_journalier
            SET texte = %s
            WHERE user_id = %s AND date = %s
        """, (commentaire, user_id, today))
    else:
        # Insertion sinon
        cursor.execute("""
            INSERT INTO commentaire_journalier (user_id, date, texte)
            VALUES (%s, %s, %s)
        """, (user_id, today, commentaire))

    conn.commit()
    conn.close()

    return RedirectResponse("/saisie", status_code=303)



@app.post("/saisie/delete-last")
async def delete_last_saisie():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cursor.execute("""
        DELETE FROM durees
        WHERE id = (SELECT id FROM durees WHERE user_id = %s AND date = CURRENT_DATE ORDER BY id DESC LIMIT 1)
    """, (1,))  # Remplacez "1" par l'ID utilisateur réel
    conn.commit()
    conn.close()
    return RedirectResponse("/saisie", status_code=303)

@app.post("/saisie/delete")
async def delete_selected_saisie(request: Request):
    # Récupérer les données du formulaire
    form_data = await request.form()
    
    # Débogage - afficher toutes les valeurs du formulaire
    print("Données du formulaire:", dict(form_data))
    
    # Vérifier si saisie_id est présent
    if "saisie_id" not in form_data:
        return await render_saisie_page(request, error="Aucune ligne sélectionnée pour la suppression.")
    
    saisie_id = form_data["saisie_id"]
    print(f"Valeur de saisie_id: '{saisie_id}', type: {type(saisie_id)}")
    
    try:
        # Convertir en entier
        saisie_id = int(saisie_id)
    except (ValueError, TypeError) as e:
        return await render_saisie_page(request, 
            error=f"Identifiant de saisie invalide: {saisie_id}, erreur: {str(e)}")
    
    
    # Suppression dans la base de données
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cursor.execute("DELETE FROM durees WHERE id = %s", (saisie_id,))
    
    # Vérifier si une ligne a été supprimée
    if cursor.rowcount == 0:
        conn.close()
        return await render_saisie_page(request, error="Saisie introuvable ou déjà supprimée.")
    
    conn.commit()
    conn.close()
    return RedirectResponse("/saisie", status_code=303)


@app.get("/admin/activities", response_class=HTMLResponse)
async def admin_activities(request: Request):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cursor.execute("SELECT id, name FROM activities ORDER BY name")
    activities = cursor.fetchall()
    conn.close()
    return templates.TemplateResponse("admin_activities.html", {"request": request, "activities": activities})

@app.post("/admin/activities/add")
async def add_activity(name: str = Form(...)):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    try:
        cursor.execute("INSERT INTO activities (name) VALUES (%s)", (name,))
        conn.commit()
    except psycopg2.IntegrityError:
        pass
    conn.close()
    return RedirectResponse("/admin/activities", status_code=303)

@app.get("/admin/activities/delete/{activity_id}")
async def delete_activity(activity_id: int):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cursor.execute("DELETE FROM activities WHERE id = %s", (activity_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/admin/activities", status_code=303)
from fastapi.responses import FileResponse

@app.get("/saisie/export")
async def export_excel():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cursor.execute("""
        SELECT d.date, a.name AS Activité, d.heure_debut AS Début, d.heure_fin AS Fin,
               ROUND((EXTRACT(EPOCH FROM (heure_fin::time - heure_debut::time))) * 24, 2) AS Durée,
               d.commentaire AS Commentaire
        FROM durees d
        JOIN activities a ON a.id = d.activity_id
        WHERE d.date = CURRENT_DATE AND user_id = %s
        ORDER BY d.heure_debut
    """, (1,))
    rows = cursor.fetchall()
    df = pd.DataFrame(rows)

    file_path = "export_journalier.xlsx"
    df.to_excel(file_path, index=False)
    conn.close()
    return FileResponse(path=file_path, filename=file_path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.post("/admin/users/add")
async def add_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...)
):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    
    try:
        cursor.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, %s)", (username, password, role))
        conn.commit()
    except psycopg2.IntegrityError:
        # Option : gérer les doublons ici si souhaité
        pass

    conn.close()
    return RedirectResponse("/admin/users", status_code=303)
    
@app.post("/admin/users/edit/{user_id}")
async def edit_user(
    user_id: int,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...)
):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cursor.execute("""
        UPDATE users SET username=%s, password=%s, role=%s WHERE id=%s
    """, (username, password, role, user_id))
    conn.commit()
    conn.close()
    return RedirectResponse("/admin/users", status_code=303)


@app.get("/admin/users/edit/{user_id}", response_class=HTMLResponse)
async def edit_user_form(request: Request, user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    user = cursor.fetchone()
    conn.close()

    if user:
        return templates.TemplateResponse("edit_users.html", {"request": request, "user": user})
    else:
        return RedirectResponse("/admin/users", status_code=303)
@app.get("/admin/users/delete/{user_id}")
async def delete_user(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cursor.execute("DELETE FROM users WHERE id=%s", (user_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/admin/users", status_code=303)

@app.post("/admin/exports/monthly")
async def export_monthly_summary(request: Request, month: int = Form(...), year: int = Form(...)):
    conn = get_db_connection()
    df = get_monthly_summary_dataframe(conn, month, year)
    conn.close()

    if df.empty:
        return templates.TemplateResponse("admin_export.html", {
            "request": request,
            "message": "⛔ Aucune donnée trouvée pour le mois sélectionné.",
            "current_month": month,
            "current_year": year,
            "years": list(range(2022, 2031))
        })

    # Créer un fichier Excel temporaire
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        filename = f"recap_{year}_{month:02d}.xlsx"
        export_to_excel(df, tmp.name, sheet_name=f"{year}_{month:02d}")
        return FileResponse(
            tmp.name,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=filename
        )

@app.post("/admin/exports/users/excel")
async def export_user_summary_excel(month: int = Form(...), year: int = Form(...)):
    conn = get_db_connection()
    df = get_user_activity_summary_dataframe(conn, year, month)
    conn.close()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        sheet_name = f"{year}_{month:02d}"
        export_to_excel(df, tmp.name, sheet_name=sheet_name)
        return FileResponse(
            tmp.name,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=f"recap_collaborateurs_{sheet_name}.xlsx"
        )



@app.post("/admin/exports/users")
async def export_user_summary(request: Request, month: int = Form(...), year: int = Form(...)):
    conn = get_db_connection()
    df = get_user_activity_summary_dataframe(conn, year, month)
    conn.close()

    # Extraire la liste des activités pour l'en-tête du tableau
    activities = list(df.columns)
    if "Utilisateur" in activities:
        activities.remove("Utilisateur")

    user_summary = df.to_dict(orient="records")

    return templates.TemplateResponse("admin_export.html", {
        "request": request,
        "user_summary": user_summary,
        "activities": activities,
        "selected_month": month,
        "selected_year": year
    })



@app.get("/admin/exports", response_class=HTMLResponse)
async def admin_exports(request: Request):
    today = date.today()
    return templates.TemplateResponse("admin_export.html", {
        "request": request,
        "selected_month": today.month,
        "selected_year": today.year,
        "years": list(range(2025, 2031))  # si vous souhaitez garder une liste pour le menu déroulant
    })
    
@app.post("/admin/exports/users/download")
async def export_user_summary(request: Request, year: int = Form(...), month: int = Form(...)):
    conn = get_db_connection()
    df = get_user_activity_summary_dataframe(conn, year, month)
    conn.close()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        sheet_name = f"{year}_{month:02d}"
        export_to_excel(df, tmp.name, sheet_name=sheet_name)
        tmp_path = tmp.name

    filename = f"recap_collaborateurs_{year}_{month:02d}.xlsx"
    return FileResponse(tmp_path, filename=filename, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.get("/admin/journee", response_class=HTMLResponse)
async def get_admin_journee(request: Request):
    today = date.today()
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cursor.execute("SELECT id, username FROM users ORDER BY username")
    utilisateurs = cursor.fetchall()

    cursor.close()
    conn.close()

    return templates.TemplateResponse("admin_journee.html", {
        "request": request,
        "selected_jour": today.day,
        "selected_mois": today.month,
        "selected_annee": today.year,
        "utilisateurs": utilisateurs,
        "selected_user_id": None,
        "enregistrements": None,
        "commentaire": None
    })



@app.post("/admin/journee", response_class=HTMLResponse)
async def admin_journee_post(
    request: Request,
    jour: int = Form(...),
    mois: int = Form(...),
    annee: int = Form(...),
    user_id: int = Form(...)
):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    date_str = f"{annee:04d}-{mois:02d}-{jour:02d}"  # format 'YYYY-MM-DD'

    # Récupérer les enregistrements d'activité pour ce jour et cet utilisateur
    cursor.execute("""
        SELECT a.name, d.heure_debut, d.heure_fin
        FROM durees d
        JOIN activities a ON d.activity_id = a.id
        WHERE d.user_id = %s AND d.date = %s
        ORDER BY d.heure_debut ASC
    """, (user_id, date_str))
    enregistrements = cursor.fetchall()

    # Récupérer le commentaire journalier (s'il existe)
    cursor.execute("""
        SELECT texte FROM commentaire_journalier
        WHERE user_id = %s AND date = %s
    """, (user_id, date_str))
    commentaire = cursor.fetchone()
    commentaire = commentaire["texte"] if commentaire else ""

    # Récupérer la liste des utilisateurs
    cursor.execute("SELECT id, username FROM users ORDER BY username")
    utilisateurs = cursor.fetchall()

    cursor.close()
    conn.close()

    return templates.TemplateResponse("admin_journee.html", {
        "request": request,
        "enregistrements": enregistrements,
        "commentaire": commentaire,
        "selected_user_id": user_id,
        "selected_jour": jour,
        "selected_mois": mois,
        "selected_annee": annee,
        "utilisateurs": utilisateurs
    })


# 🔐 Traitement de la connexion
@app.post("/login")
async def login(request: Request, identifiant: str = Form(...), mot_de_passe: str = Form(...)):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # Utiliser les bons noms de colonnes de la BDD
    cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s", (identifiant, mot_de_passe))
    user = cursor.fetchone()
    conn.close()

    if user:
        request.session["user_id"] = user["id"]
        role = user["role"]
        if role == "admin":
            return RedirectResponse("/admin", status_code=303)
        else:
            return RedirectResponse("/saisie", status_code=303)
    else:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "⛔ Identifiant ou mot de passe incorrect."
        })



# 👨‍💼 Page Admin
@app.get("/admin", response_class=HTMLResponse)
async def admin_home(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})

# 👉 Autres routes (admin_users, edit_users, admin_activities, admin_export) à ajouter ensuite...
