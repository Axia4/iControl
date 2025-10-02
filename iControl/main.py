import os
import sys
from flask import Flask, render_template, flash, request, redirect, url_for
import requests
import json
from datetime import datetime, timedelta
from icalendar import Calendar

from iaxshared.notify import notify
from iaxshared.iax_db import SimpleJSONDB

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

# Initialize the new database
DB = SimpleJSONDB('_datos/iControl.iax')
DB.create_table('devices')

app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/notify', methods=['GET', 'POST'])
def notify_route():
    devices = DB.get_all('devices')
    if request.method == 'POST':
        targets = request.form.getlist('targets')
        message = request.form.get('message')
        button_title = request.form.get('button_title')
        button_url = request.form.get('button_url')
        priority = request.form.get('priority', "0")
        if not message:
            flash("El mensaje no puede estar vacío.")
            return render_template('notify.html', devices=devices.items())
        if not targets:
            flash("Debe seleccionar al menos un dispositivo.")
            return render_template('notify.html', devices=devices.items())
        for target in targets:
            notify(target, message, button_title, button_url, priority)
        flash("Notificaciones enviadas a {} dispositivos.".format(len(targets)))
        return redirect(url_for('index'))
    return render_template('notify.html', devices=devices.items())

@app.route('/resumen_diario')
def resumen_diario():
    # Obtener ruta de config.json relativa al ejecutable
    config_path = 'iControl-Datos/config.json'

    with open(config_path, 'r') as f:
        config = json.load(f)

    cal_url_tarde = config.get('Cal_TurnosDeTarde')
    eventos_tarde = []
    if cal_url_tarde:
        try:
            resp = requests.get(cal_url_tarde)
            if resp.status_code == 200:
                cal = Calendar.from_ical(resp.content)
                hoy = datetime.now().date()
                for component in cal.walk():
                    if component.name == "VEVENT":
                        dtstart = component.get('dtstart').dt
                        dtend = component.get('dtend').dt if component.get('dtend') else dtstart
                        # Convertir a date si es datetime
                        if isinstance(dtstart, datetime):
                            dtstart = dtstart.date()
                        if isinstance(dtend, datetime):
                            dtend = dtend.date()
                        # Mostrar si hoy está en el rango [dtstart, dtend)
                        if dtstart <= hoy < dtend:
                            resumen = str(component.get('summary'))
                            if isinstance(component.get('dtstart').dt, datetime):
                                hora = component.get('dtstart').dt.strftime('%H:%M')
                            else:
                                hora = 'Todo el día'
                            eventos_tarde.append({'hora': hora, 'resumen': resumen})
        except Exception as e:
            eventos_tarde = [{'hora': '', 'resumen': f'Error al obtener eventos: {e}'}]
    cal_url_recordatorios = config.get('Cal_Recordatorios')
    eventos_recordatorios = []
    if cal_url_recordatorios:
        try:
            resp = requests.get(cal_url_recordatorios)
            if resp.status_code == 200:
                cal = Calendar.from_ical(resp.content)
                hoy = datetime.now().date()
                for component in cal.walk():
                    if component.name == "VEVENT":
                        dtstart = component.get('dtstart').dt
                        dtend = component.get('dtend').dt if component.get('dtend') else dtstart
                        if isinstance(dtstart, datetime):
                            dtstart = dtstart.date()
                        if isinstance(dtend, datetime):
                            dtend = dtend.date()
                        if dtstart <= hoy < dtend:
                            resumen = str(component.get('summary'))
                            if isinstance(component.get('dtstart').dt, datetime):
                                hora = component.get('dtstart').dt.strftime('%H:%M')
                            else:
                                hora = 'Todo el día'
                            eventos_recordatorios.append({'hora': hora, 'resumen': resumen})
        except Exception as e:
            eventos_recordatorios = [{'hora': '', 'resumen': f'Error al obtener eventos: {e}'}]
    return render_template('resumen_diario.html', eventos_tarde=eventos_tarde, eventos_recordatorios=eventos_recordatorios)

@app.route('/sysinfo')
def sysinfo():
    return render_template('sysinfo.html')

#region Admin -> Devices
@app.route('/admin/devices')
def admin_devices():
    devices = DB.get_all('devices')
    return render_template('admin/devices/index.html', devices=devices.items())

@app.route('/admin/devices/add', methods=['GET', 'POST'])
def admin_devices_add():
    if request.method == 'POST':
        name = request.form.get('name')
        ntfy_topic = request.form.get('ntfy_topic')
        description = request.form.get('description', '')
        if not name or not ntfy_topic:
            flash("El nombre y el topic son obligatorios.")
            return render_template('admin/devices/add.html')
        # Verificar si el topic ya existe
        existing = DB.find('devices', {'ntfy_topic': ntfy_topic})
        if existing:
            flash("Ya existe un dispositivo con ese topic.\nEs mejor usar uno por dispositivo para poder diferenciar los avisos.\nSe creará de todas formas.")
        DB.insert('devices', {'name': name, 'ntfy_topic': ntfy_topic, 'description': description})
        return redirect('/admin/devices')
    return render_template('admin/devices/add.html')

@app.route('/admin/devices/delete/<device_id>', methods=['POST'])
def admin_devices_delete(device_id):
    device = DB.find_by_id('devices', device_id)
    if not device:
        flash("Dispositivo no encontrado.")
        return redirect('/admin/devices')
    DB.delete_by_id('devices', device_id)
    return redirect('/admin/devices')

@app.route('/admin/devices/<device_id>/edit', methods=['GET', 'POST'])
def admin_devices_edit(device_id):
    device = DB.find_by_id('devices', device_id)
    if not device:
        flash("Dispositivo no encontrado.")
        return redirect('/admin/devices')
    if request.method == 'POST':
        name = request.form.get('name')
        ntfy_topic = request.form.get('ntfy_topic')
        description = request.form.get('description', '')
        if not name or not ntfy_topic:
            flash("El nombre y el topic son obligatorios.")
            return render_template('admin/devices/edit.html', device=device, id=device_id)
        # Verificar si el topic ya existe en otro dispositivo
        existing = DB.find('devices', {'ntfy_topic': ntfy_topic})
        if len(existing) > 1 or (len(existing) == 1 and existing[0]['id'] != device_id):
            flash("Ya existe un dispositivo con ese topic.\nEs mejor usar uno por dispositivo para poder diferenciar los avisos.\nSe actualizará de todas formas.")
        DB.update_by_id('devices', device_id, {'name': name, 'ntfy_topic': ntfy_topic, 'description': description})
        return redirect('/admin/devices')
    return render_template('admin/devices/edit.html', device=device, id=device_id)

@app.route('/admin/devices/<device_id>')
def admin_devices_view(device_id):
    device = DB.find_by_id('devices', device_id)
    if not device:
        flash("Dispositivo no encontrado.")
        return redirect('/admin/devices')
    return render_template('admin/devices/view.html', device=device, id=device_id)

#endregion

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

if __name__ == '__main__':
    app.config['SECRET_KEY'] = 'supersecretkey'
    if os.environ.get('FLASK_ENV') == 'development' or sys.argv[1:] == ['--dev']:
        app.config['TEMPLATES_AUTO_RELOAD'] = True
        app.run(port=5000, debug=True)
    else:
        app.run(host='0.0.0.0', port=5343, debug=False)