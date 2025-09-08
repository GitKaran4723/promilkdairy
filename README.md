# Milk Diary (Flask + SQLite)

## Setup (Linux / macOS)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# initialize DB and seed
export FLASK_APP=app.py
flask --app app init-db   # or: flask init-db

# run
flask --app app run

Open http://127.0.0.1:5000
Login: phone=admin, password=adminpass

## Notes
- Use the `init-db` CLI command to (re)create DB and seed milk types.
- For production, set a proper SECRET_KEY and run under gunicorn + nginx.
- Add icons in static/icons/ for PWA install.
