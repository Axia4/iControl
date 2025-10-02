import os
from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/resumen_diario')
def resumen_diario():
    return render_template('resumen_diario.html')

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