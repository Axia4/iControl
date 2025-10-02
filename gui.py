from flask import Flask
import webbrowser
from main import app
import sys
import threading
from time import sleep


def start_server():
    app.run(host='0.0.0.0', port=5343)

if __name__ == '__main__':

    t = threading.Thread(target=start_server)
    t.daemon = True
    t.start()
    sleep(0.5)
    webbrowser.open('http://127.0.0.1:5343/')
    input("Pulsa intro para apagar el servidor y cerrar la aplicación...")
    sys.exit()