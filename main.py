import os
import sys
from flask import Flask, render_template
import requests
import json
from datetime import datetime, timedelta
from icalendar import Calendar

# Handle PyInstaller frozen executable paths
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    base_path = sys._MEIPASS
    template_folder = os.path.join(base_path, 'templates')
    static_folder = os.path.join(base_path, 'static')
else:
    # Running as normal Python script
    template_folder = 'templates'
    static_folder = 'static'

app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/resumen_diario')
def resumen_diario():
    # Obtener ruta de config.json relativa al ejecutable
    config_path = 'config.json'

    with open(config_path, 'r') as f:
        config = json.load(f)

    cal_url = config.get('Cal_TurnosDeTarde')
    eventos = []
    if cal_url:
        try:
            resp = requests.get(cal_url)
            if resp.status_code == 200:
                cal = Calendar.from_ical(resp.content)
                hoy = datetime.now().date()
                for component in cal.walk():
                    if component.name == "VEVENT":
                        inicio = component.get('dtstart').dt
                        if isinstance(inicio, datetime):
                            inicio = inicio.date()
                        if inicio == hoy:
                            resumen = str(component.get('summary'))
                            hora = component.get('dtstart').dt.strftime('%H:%M') if hasattr(component.get('dtstart').dt, 'strftime') else ''
                            eventos.append({'hora': hora, 'resumen': resumen})
        except Exception as e:
            eventos = [{'hora': '', 'resumen': f'Error al obtener eventos: {e}'}]
    return render_template('resumen_diario.html', eventos=eventos)

@app.route('/sysinfo')
def sysinfo():
    return render_template('sysinfo.html')


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

if __name__ == '__main__':
    if os.environ.get('FLASK_ENV') == 'development':
        app.config['TEMPLATES_AUTO_RELOAD'] = True
        app.run(port=5000, debug=True)
    else:
        app.run(host='0.0.0.0', port=5343, debug=False)