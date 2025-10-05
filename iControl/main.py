import os
import sys
from flask import Flask, render_template, flash, request, redirect, url_for
import requests
import json
from datetime import datetime, timedelta
from icalendar import Calendar
import csv
import io
import threading
import time
import webbrowser

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
DB.create_table('menus')
DB.create_table('config')
DB.create_table('recordatorios')

# Initialize default configuration if not exists
def init_config():
    """Initialize default configuration values if they don't exist"""
    # First, try to migrate from existing config file
    migrate_config_file()
    
    default_configs = {
        'Cal_TurnosDeTarde': {'key': 'Cal_TurnosDeTarde', 'value': '', 'description': 'URL del calendario de turnos de tarde'},
        'Cal_Recordatorios': {'key': 'Cal_Recordatorios', 'value': '', 'description': 'URL del calendario de recordatorios'},
        'url_base': {'key': 'url_base', 'value': 'http://localhost:5343', 'description': 'URL base para enlaces en notificaciones'},
        'url_base_launcher': {'key': 'url_base_launcher', 'value': 'http://localhost:5343', 'description': 'URL base para abrir automáticamente al iniciar el ejecutable'},
    }
    
    for config_key, config_data in default_configs.items():
        existing = DB.find('config', {'key': config_key})
        if not existing:
            DB.insert('config', config_data)

def migrate_config_file():
    """Migrate configuration from old JSON file to database if it exists"""
    config_path = '_datos/iControl.config'
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            for key, value in config.items():
                existing = DB.find('config', {'key': key})
                if not existing:
                    description = ''
                    if key == 'Cal_TurnosDeTarde':
                        description = 'URL del calendario de turnos de tarde'
                    elif key == 'Cal_Recordatorios':
                        description = 'URL del calendario de recordatorios'
                    
                    DB.insert('config', {'key': key, 'value': value, 'description': description})
            
            # Optionally rename the old config file to prevent re-migration
            backup_path = config_path + '.migrated'
            os.rename(config_path, backup_path)
            print(f"Configuration migrated from {config_path} to database. Old file backed up as {backup_path}")
            
        except Exception as e:
            print(f"Error migrating config file: {e}")

def get_config(key: str, default_value: str = '') -> str:
    """Get a configuration value by key"""
    result = DB.find('config', {'key': key})
    if result:
        return result[0].get('value', default_value)
    return default_value

def set_config(key: str, value: str, description: str = '') -> None:
    """Set a configuration value by key"""
    existing = DB.find('config', {'key': key})
    if existing:
        # Update existing
        config_id = existing[0]['id']
        DB.update_by_id('config', config_id, {'value': value, 'description': description})
    else:
        # Create new
        DB.insert('config', {'key': key, 'value': value, 'description': description})

# Initialize configuration on startup
init_config()

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
    # Get configuration from database instead of config file
    cal_url_tarde = get_config('Cal_TurnosDeTarde')
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
    
    cal_url_recordatorios = get_config('Cal_Recordatorios')
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
    
    # Get today's menus
    hoy_str = datetime.now().strftime('%Y-%m-%d')
    menus_hoy = []
    all_menus = DB.get_all('menus')
    for menu_id, menu_data in all_menus.items():
        if menu_data.get('date') == hoy_str:
            menus_hoy.append(menu_data)
    
    return render_template('resumen_diario.html', eventos_tarde=eventos_tarde, eventos_recordatorios=eventos_recordatorios, menus_hoy=menus_hoy)

@app.route('/sysinfo')
def sysinfo():
    return render_template('sysinfo.html')

#region Menu Comedor
@app.route('/menu_comedor')
def menu_comedor():
    menus = DB.get_all('menus')
    # Group menus by menu type
    menu_types = {}
    for menu_id, menu_data in menus.items():
        menu_type = menu_data.get('menu_type', 'Unknown')
        if menu_type not in menu_types:
            menu_types[menu_type] = []
        menu_types[menu_type].append(menu_data)
    
    # Sort menus by date (newest first)
    for menu_type in menu_types:
        menu_types[menu_type].sort(key=lambda x: x.get('date', ''), reverse=True)
    
    return render_template('menu_comedor/index.html', menu_types=menu_types)

@app.route('/menu_comedor/import', methods=['GET', 'POST'])
def menu_comedor_import():
    if request.method == 'POST':
        menu_type = request.form.get('menu_type', '').strip()
        csv_data = request.form.get('csv_data', '').strip()
        
        if not menu_type:
            flash("El tipo de menú es obligatorio.")
            return render_template('menu_comedor/import.html')
        
        if not csv_data:
            flash("Debes proporcionar datos CSV.")
            return render_template('menu_comedor/import.html')
        
        # Parse CSV
        imported_count = 0
        errors = []
        
        csv_reader = csv.reader(io.StringIO(csv_data), delimiter=';')
        for line_num, row in enumerate(csv_reader, 1):
            if len(row) != 5:
                errors.append(f"Línea {line_num}: formato incorrecto (se esperan 5 campos)")
                continue
            
            date_str, primer_plato, segundo_plato, postre, es_apetecible = row
            
            # Validate date format YYYY-MM-DD
            try:
                date_obj = datetime.strptime(date_str.strip(), '%Y-%m-%d')
                date_formatted = date_obj.strftime('%Y_%m_%d')
            except ValueError:
                errors.append(f"Línea {line_num}: fecha inválida '{date_str}' (formato esperado: YYYY-MM-DD)")
                continue
            
            # Validate es_apetecible
            es_apetecible = es_apetecible.strip().upper()
            if es_apetecible not in ['OK', 'KO']:
                errors.append(f"Línea {line_num}: es_apetecible debe ser OK o KO, recibido '{es_apetecible}'")
                continue
            
            # Create unique ID: MenuType|YYYY_MM_DD
            menu_id = f"{menu_type}|{date_formatted}"
            
            # Insert or update menu
            menu_record = {
                'id': menu_id,
                'menu_type': menu_type,
                'date': date_str.strip(),
                'primer_plato': primer_plato.strip(),
                'segundo_plato': segundo_plato.strip(),
                'postre': postre.strip(),
                'es_apetecible': es_apetecible == 'OK'
            }
            
            DB.insert('menus', menu_record)
            imported_count += 1
        
        if errors:
            flash(f"Importados {imported_count} menús con {len(errors)} errores:\n" + "\n".join(errors))
        else:
            flash(f"Importados {imported_count} menús correctamente.")
        
        return redirect('/menu_comedor')
    
    return render_template('menu_comedor/import.html')

@app.route('/menu_comedor/delete/<menu_id>', methods=['POST'])
def menu_comedor_delete(menu_id):
    DB.delete_by_id('menus', menu_id)
    flash("Menú eliminado correctamente.")
    return redirect('/menu_comedor')

#endregion

#region Recordatorios
@app.route('/recordatorios')
def recordatorios():
    # Get all recordatorios and organize them
    all_recordatorios = DB.get_all('recordatorios')
    
    # Separate by type
    day_assigned = []
    todo_tasks = []
    
    for recordatorio_id, recordatorio in all_recordatorios.items():
        if recordatorio.get('type') == 'day_assigned':
            day_assigned.append(recordatorio)
        elif recordatorio.get('type') == 'todo':
            todo_tasks.append(recordatorio)
    
    # Sort day-assigned by date
    day_assigned.sort(key=lambda x: x.get('assigned_date', ''), reverse=False)
    
    # Sort todo tasks by status (todo -> doing -> done) and creation date
    status_order = {'todo': 0, 'doing': 1, 'done': 2}
    todo_tasks.sort(key=lambda x: (status_order.get(x.get('status', 'todo'), 0), x.get('created_at', '')))
    
    return render_template('recordatorios/index.html', 
                         day_assigned=day_assigned, 
                         todo_tasks=todo_tasks)

@app.route('/recordatorios/add', methods=['GET', 'POST'])
def recordatorios_add():
    if request.method == 'POST':
        recordatorio_type = request.form.get('type')
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        
        if not title:
            flash("El título es obligatorio.")
            return render_template('recordatorios/add.html')
        
        if not recordatorio_type or recordatorio_type not in ['day_assigned', 'todo']:
            flash("Tipo de recordatorio inválido.")
            return render_template('recordatorios/add.html')
        
        recordatorio_data = {
            'type': recordatorio_type,
            'title': title,
            'description': description,
            'created_at': datetime.now().isoformat()
        }
        
        if recordatorio_type == 'day_assigned':
            assigned_date = request.form.get('assigned_date', '').strip()
            if not assigned_date:
                flash("La fecha es obligatoria para recordatorios asignados a un día.")
                return render_template('recordatorios/add.html')
            recordatorio_data['assigned_date'] = assigned_date
            recordatorio_data['completed'] = False
        elif recordatorio_type == 'todo':
            recordatorio_data['status'] = 'todo'  # todo, doing, done
        
        DB.insert('recordatorios', recordatorio_data)
        flash("Recordatorio creado correctamente.")
        return redirect('/recordatorios')
    
    return render_template('recordatorios/add.html')

@app.route('/recordatorios/edit/<recordatorio_id>', methods=['GET', 'POST'])
def recordatorios_edit(recordatorio_id):
    recordatorio = DB.find_by_id('recordatorios', recordatorio_id)
    if not recordatorio:
        flash("Recordatorio no encontrado.")
        return redirect('/recordatorios')
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        
        if not title:
            flash("El título es obligatorio.")
            return render_template('recordatorios/edit.html', recordatorio=recordatorio, id=recordatorio_id)
        
        updates = {
            'title': title,
            'description': description
        }
        
        if recordatorio.get('type') == 'day_assigned':
            assigned_date = request.form.get('assigned_date', '').strip()
            if not assigned_date:
                flash("La fecha es obligatoria para recordatorios asignados a un día.")
                return render_template('recordatorios/edit.html', recordatorio=recordatorio, id=recordatorio_id)
            updates['assigned_date'] = assigned_date
            updates['completed'] = request.form.get('completed') == 'on'
        elif recordatorio.get('type') == 'todo':
            status = request.form.get('status', 'todo')
            if status not in ['todo', 'doing', 'done']:
                status = 'todo'
            updates['status'] = status
        
        DB.update_by_id('recordatorios', recordatorio_id, updates)
        flash("Recordatorio actualizado correctamente.")
        return redirect('/recordatorios')
    
    return render_template('recordatorios/edit.html', recordatorio=recordatorio, id=recordatorio_id)

@app.route('/recordatorios/delete/<recordatorio_id>', methods=['POST'])
def recordatorios_delete(recordatorio_id):
    recordatorio = DB.find_by_id('recordatorios', recordatorio_id)
    if not recordatorio:
        flash("Recordatorio no encontrado.")
        return redirect('/recordatorios')
    
    DB.delete_by_id('recordatorios', recordatorio_id)
    flash("Recordatorio eliminado correctamente.")
    return redirect('/recordatorios')

@app.route('/recordatorios/quick_status/<recordatorio_id>', methods=['POST'])
def recordatorios_quick_status(recordatorio_id):
    """Quick status change for todo-style recordatorios"""
    recordatorio = DB.find_by_id('recordatorios', recordatorio_id)
    if not recordatorio or recordatorio.get('type') != 'todo':
        flash("Recordatorio no encontrado o no es de tipo todo.")
        return redirect('/recordatorios')
    
    current_status = recordatorio.get('status', 'todo')
    status_cycle = {'todo': 'doing', 'doing': 'done', 'done': 'todo'}
    new_status = status_cycle.get(current_status, 'todo')
    
    DB.update_by_id('recordatorios', recordatorio_id, {'status': new_status})
    return redirect('/recordatorios')

@app.route('/recordatorios/toggle_complete/<recordatorio_id>', methods=['POST'])
def recordatorios_toggle_complete(recordatorio_id):
    """Toggle completion for day-assigned recordatorios"""
    recordatorio = DB.find_by_id('recordatorios', recordatorio_id)
    if not recordatorio or recordatorio.get('type') != 'day_assigned':
        flash("Recordatorio no encontrado o no es de tipo día asignado.")
        return redirect('/recordatorios')
    
    current_completed = recordatorio.get('completed', False)
    DB.update_by_id('recordatorios', recordatorio_id, {'completed': not current_completed})
    return redirect('/recordatorios')

#endregion

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

#region Admin -> Config
@app.route('/admin/config')
def admin_config():
    configs = DB.get_all('config')
    return render_template('admin/config/index.html', configs=configs.items())

@app.route('/admin/config/edit/<config_id>', methods=['GET', 'POST'])
def admin_config_edit(config_id):
    config = DB.find_by_id('config', config_id)
    if not config:
        flash("Configuración no encontrada.")
        return redirect('/admin/config')
    
    if request.method == 'POST':
        value = request.form.get('value', '')
        description = request.form.get('description', '')
        
        DB.update_by_id('config', config_id, {'value': value, 'description': description})
        flash(f"Configuración '{config['key']}' actualizada correctamente.")
        return redirect('/admin/config')
    
    return render_template('admin/config/edit.html', config=config, id=config_id)

@app.route('/admin/config/add', methods=['GET', 'POST'])
def admin_config_add():
    if request.method == 'POST':
        key = request.form.get('key', '').strip()
        value = request.form.get('value', '').strip()
        description = request.form.get('description', '').strip()
        
        if not key:
            flash("La clave es obligatoria.")
            return render_template('admin/config/add.html')
        
        # Check if key already exists
        existing = DB.find('config', {'key': key})
        if existing:
            flash("Ya existe una configuración con esa clave.")
            return render_template('admin/config/add.html')
        
        DB.insert('config', {'key': key, 'value': value, 'description': description})
        flash(f"Configuración '{key}' creada correctamente.")
        return redirect('/admin/config')
    
    return render_template('admin/config/add.html')

@app.route('/admin/config/delete/<config_id>', methods=['POST'])
def admin_config_delete(config_id):
    config = DB.find_by_id('config', config_id)
    if not config:
        flash("Configuración no encontrada.")
        return redirect('/admin/config')
    
    DB.delete_by_id('config', config_id)
    flash(f"Configuración '{config['key']}' eliminada correctamente.")
    return redirect('/admin/config')

#endregion

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

def schedule_daily_menu_notification():
    """Background task to send menu notifications at 12:15 daily"""
    while True:
        now = datetime.now()
        # Calculate next 12:15
        target_time = now.replace(hour=12, minute=15, second=0, microsecond=0)
        if now >= target_time:
            # If we've passed 12:15 today, schedule for tomorrow
            target_time += timedelta(days=1)
        
        # Calculate seconds until target time
        sleep_seconds = (target_time - now).total_seconds()
        time.sleep(sleep_seconds)
        
        # Send notifications
        try:
            hoy_str = datetime.now().strftime('%Y-%m-%d')
            menus_hoy = []
            all_menus = DB.get_all('menus')
            for menu_id, menu_data in all_menus.items():
                if menu_data.get('date') == hoy_str:
                    menus_hoy.append(menu_data)
            
            if menus_hoy:
                # Build message
                message_lines = ["🍽️ Menú del comedor de hoy:"]
                for menu in menus_hoy:
                    menu_type = menu.get('menu_type', 'Menú')
                    message_lines.append(f"\n📋 {menu_type}:")
                    message_lines.append(f"  1º: {menu.get('primer_plato', 'N/A')}")
                    message_lines.append(f"  2º: {menu.get('segundo_plato', 'N/A')}")
                    message_lines.append(f"  Postre: {menu.get('postre', 'N/A')}")
                    if menu.get('es_apetecible'):
                        message_lines.append(f"  ✅ Apetecible")
                    else:
                        message_lines.append(f"  ❌ No muy apetecible")
                
                message = '\n'.join(message_lines)
                
                # Send to all devices
                devices = DB.get_all('devices')
                for device_id, device in devices.items():
                    ntfy_topic = device.get('ntfy_topic')
                    if ntfy_topic:
                        notify(ntfy_topic, message, "Ver menú completo", get_config("url_base") + "/menu_comedor", 3)
        except Exception as e:
            print(f"Error sending daily menu notification: {e}")

def schedule_daily_recordatorios_notification():
    """Background task to send recordatorios notifications at 10:30 daily"""
    while True:
        now = datetime.now()
        # Calculate next 10:30
        target_time = now.replace(hour=10, minute=30, second=0, microsecond=0)
        if now >= target_time:
            # If we've passed 10:30 today, schedule for tomorrow
            target_time += timedelta(days=1)
        
        # Calculate seconds until target time
        sleep_seconds = (target_time - now).total_seconds()
        time.sleep(sleep_seconds)
        
        # Send notifications
        try:
            hoy_str = datetime.now().strftime('%Y-%m-%d')
            recordatorios_hoy = []
            all_recordatorios = DB.get_all('recordatorios')
            
            for recordatorio_id, recordatorio in all_recordatorios.items():
                # Only day-assigned recordatorios for today that are not completed
                if (recordatorio.get('type') == 'day_assigned' and 
                    recordatorio.get('assigned_date') == hoy_str and 
                    not recordatorio.get('completed', False)):
                    recordatorios_hoy.append(recordatorio)
            
            if recordatorios_hoy:
                # Build message
                if len(recordatorios_hoy) == 1:
                    message_lines = ["📝 Recordatorio para hoy:"]
                else:
                    message_lines = [f"📝 {len(recordatorios_hoy)} recordatorios para hoy:"]
                
                for i, recordatorio in enumerate(recordatorios_hoy, 1):
                    if len(recordatorios_hoy) > 1:
                        message_lines.append(f"\n{i}. 📌 {recordatorio.get('title', 'Sin título')}")
                    else:
                        message_lines.append(f"\n📌 {recordatorio.get('title', 'Sin título')}")
                    
                    if recordatorio.get('description'):
                        # Truncate description if too long
                        desc = recordatorio.get('description')
                        if len(desc) > 100:
                            desc = desc[:100] + "..."
                        message_lines.append(f"   {desc}")
                
                message = '\n'.join(message_lines)
                
                # Send to all devices
                devices = DB.get_all('devices')
                for device_id, device in devices.items():
                    ntfy_topic = device.get('ntfy_topic')
                    if ntfy_topic:
                        notify(ntfy_topic, message, "Ver recordatorios", get_config("url_base") + "/recordatorios", 2)
            
            # Also send notification for pending TODO tasks (optional)
            todo_pendientes = []
            for recordatorio_id, recordatorio in all_recordatorios.items():
                if (recordatorio.get('type') == 'todo' and 
                    recordatorio.get('status') in ['todo', 'doing']):
                    todo_pendientes.append(recordatorio)
            
            if todo_pendientes and len(todo_pendientes) >= 3:  # Only if 3+ pending tasks
                message_lines = [f"⚡ Tienes {len(todo_pendientes)} tareas pendientes:"]
                
                # Show first 3 tasks
                for i, recordatorio in enumerate(todo_pendientes[:3], 1):
                    status_icon = "📋" if recordatorio.get('status') == 'todo' else "⚡"
                    message_lines.append(f"\n{status_icon} {recordatorio.get('title', 'Sin título')}")
                
                if len(todo_pendientes) > 3:
                    message_lines.append(f"\n... y {len(todo_pendientes) - 3} más")
                
                message = '\n'.join(message_lines)
                
                # Send to all devices with lower priority
                devices = DB.get_all('devices')
                for device_id, device in devices.items():
                    ntfy_topic = device.get('ntfy_topic')
                    if ntfy_topic:
                        notify(ntfy_topic, message, "Ver tareas", get_config("url_base") + "/recordatorios", 1)

        except Exception as e:
            print(f"Error sending daily recordatorios notification: {e}")

if __name__ == '__main__':
    app.config['SECRET_KEY'] = 'supersecretkey'
    
    # Start notification schedulers in background
    menu_notification_thread = threading.Thread(target=schedule_daily_menu_notification, daemon=True)
    menu_notification_thread.start()
    
    recordatorios_notification_thread = threading.Thread(target=schedule_daily_recordatorios_notification, daemon=True)
    recordatorios_notification_thread.start()
    
    if os.environ.get('FLASK_ENV') == 'development' or sys.argv[1:] == ['--dev']:
        app.config['TEMPLATES_AUTO_RELOAD'] = True
        app.run(port=5000, debug=True)
    else:
        if hasattr(sys, 'frozen', False):
            # Open the web browser automatically when running as a frozen executable
            url_base = get_config("url_base_launcher", "http://localhost:5343")
            webbrowser.open(url_base)
        app.run(host='0.0.0.0', port=5343, debug=False)