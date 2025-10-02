import os
import sys
import json
import threading
import tkinter as tk
import webbrowser
import requests
from playsound import playsound
import pystray
from PIL import Image, ImageDraw, ImageTk
import time
import queue

# ----- Resource Path for PyInstaller compatibility -----
def resource_path(relative_path):
    try:
        base_path = getattr(sys, '_MEIPASS', os.path.abspath("."))
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, "static", relative_path)

# ----- Config File with GUI Input -----
CONFIG_FILE = os.path.join(os.path.expanduser("~"), "iaxconfig.avisos.json")

def load_config():
    config = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
        except:
            pass

    if "topic" not in config or "cordiax_url" not in config:
        root = tk.Tk()
        root.title("Configuración Inicial")
        root.geometry("400x200")
        root.resizable(False, False)
        root.iconbitmap(resource_path("logo.ico"))  # <<< set icon here

        tk.Label(root, text="Introduce el topic de ntfy.sh:").pack(pady=(20, 5))
        topic_var = tk.StringVar(value=config.get("topic", ""))
        tk.Entry(root, textvariable=topic_var, width=40).pack()

        tk.Label(root, text="Introduce la URL de iControl:").pack(pady=(20, 5))
        url_var = tk.StringVar(value=config.get("cordiax_url", ""))
        tk.Entry(root, textvariable=url_var, width=40).pack()

        def save_and_close():
            config["topic"] = topic_var.get().strip()
            config["cordiax_url"] = url_var.get().strip()
            with open(CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=4)
            root.destroy()

        tk.Button(root, text="Guardar", command=save_and_close).pack(pady=20)
        root.mainloop()

    return config

config = load_config()
TOPIC = config["topic"]
CORDIAX_URL = config["cordiax_url"]
NTFY_URL = f"https://ntfy.sh/{TOPIC}/json"

# ----- Global Variables -----
icon = None
popup_offset = 0
popup_lock = threading.Lock()
sound_threads = {}
notification_queue = queue.Queue()

# ----- High-Priority Sound Loop -----
def play_sound_loop(popup_id, stop_event):
    while not stop_event.is_set():
        try:
            playsound(resource_path("alarm.wav"), block=False)
        except Exception as e:
            print("Error playing alarm.wav:", e, file=sys.stderr)
        stop_event.wait(10)

# ----- Tray Icon -----
def create_icon(color):
    image = Image.new('RGB', (64,64), (255,255,255))
    dc = ImageDraw.Draw(image)
    dc.ellipse((16,16,48,48), fill=color)
    return image

def set_tray_status(color, tooltip):
    global icon
    if icon:
        icon.icon = create_icon(color)
        icon.title = tooltip

# ----- Notification Popup -----
main_root = tk.Tk()
main_root.withdraw()  # hide main window
main_root.iconbitmap(resource_path("logo.ico"))

def show_notification(msg, click_url=None, custom_title=None, priority=3):
    global popup_offset, sound_threads
    popup = tk.Toplevel(main_root)
    popup.title("Notificación iControl")
    popup.geometry("840x440")  # 2x size
    popup.attributes("-topmost", True)  # Always on top
    popup.resizable(False, False)  # Disable resizing

    with popup_lock:
        y_offset = 50 + popup_offset
        popup_offset += 40
    # Disabled
    # popup.geometry(f"+100+{y_offset}")

    # High-priority flashing banner
    if priority > 3:
        banner = tk.Label(popup, text="PRIORITARIO", font=("Arial", 24, "bold"), bg="red", fg="white")
        banner.pack(fill="x")
        def flash():
            current_bg = banner.cget("bg")
            if current_bg == "red":
                banner.config(bg="white", fg="black")
            else:
                banner.config(bg="red", fg="white")
            popup.after(500, flash)
        flash()

    # Frame for scrollable text
    text_frame = tk.Frame(popup)
    text_frame.pack(padx=20, pady=20, fill="both", expand=True)

    scrollbar = tk.Scrollbar(text_frame)
    scrollbar.pack(side="right", fill="y")

    text_widget = tk.Text(
        text_frame, 
        wrap="word", 
        font=("Arial", 25), 
        yscrollcommand=scrollbar.set, 
        bg=popup.cget("bg"), 
        borderwidth=0,
        height=7  # FIX: limit height so buttons stay visible
    )
    text_widget.insert("1.0", msg)
    text_widget.config(state="disabled")
    text_widget.pack(side="left", fill="both", expand=True)

    scrollbar.config(command=text_widget.yview)

    # Buttons frame docked at the bottom
    button_frame = tk.Frame(popup)
    button_frame.pack(side="bottom", pady=20)

    popup_id = id(popup)
    stop_event = threading.Event()
    if priority > 3:
        sound_thread = threading.Thread(target=play_sound_loop, args=(popup_id, stop_event), daemon=True)
        sound_thread.start()
        sound_threads[popup_id] = stop_event

    def stop_sound():
        if popup_id in sound_threads:
            sound_threads[popup_id].set()
            del sound_threads[popup_id]

    def on_close():
        stop_sound()
        set_tray_status((200,0,0), "Conectado (esperando)")
        popup.destroy()
        with popup_lock:
            nonlocal_y = popup.winfo_y()
            if nonlocal_y == popup_offset:
                popup_offset = max(0, popup_offset-40)

    def on_access():
        if click_url:
            webbrowser.open(click_url)
        on_close()

    def on_cordiax():
        webbrowser.open(CORDIAX_URL)
        on_close()

    # Define button styles individually
    btn_font = ("Arial", 24, "bold")
    btn_width = 10
    btn_height = 1

    if click_url:
        btn_access = tk.Button(button_frame, text=custom_title, command=on_access,
                               font=btn_font, width=btn_width, height=btn_height,
                               bg="#2196F3", fg="white", activebackground="#1976D2")
        btn_access.pack(side="left", padx=5)

    btn_accept = tk.Button(button_frame, text="Aceptar", command=on_close,
                           font=btn_font, width=btn_width, height=btn_height,
                           bg="#4CAF50", fg="white", activebackground="#45a049")
    btn_accept.pack(side="left", padx=5)

    btn_cordiax = tk.Button(button_frame, text="iControl", command=on_cordiax,
                            font=btn_font, width=btn_width, height=btn_height,
                            bg="#FF9800", fg="white", activebackground="#FB8C00")
    btn_cordiax.pack(side="left", padx=5)

    if priority > 3:
        def on_silenciar():
            stop_sound()
            silenciar_btn.config(state="disabled", bg="#9E9E9E", fg="white", activebackground="#9E9E9E")

        silenciar_btn = tk.Button(button_frame, text="Silenciar", command=on_silenciar,
                                  font=btn_font, width=btn_width, height=btn_height,
                                  bg="#F44336", fg="white", activebackground="#D32F2F")
        silenciar_btn.pack(side="left", padx=5)

    popup.protocol("WM_DELETE_WINDOW", on_close)

# ----- Notification Queue Processor -----
def process_queue():
    print("Queue size:", notification_queue.qsize())
    try:
        # Process only one notification per call
        data = notification_queue.get_nowait()
    except queue.Empty:
        data = None

    if data:
        msg = data.get("message","")
        click_url = data.get("click")
        custom_title = data.get("title")
        priority = data.get("priority",3)
        print("D.", data.get("event"))
        if data.get("event") == "message":
            print("F.", msg)
            if priority <= 3:
                try:
                    playsound(resource_path("ring.wav"), block=False)
                except:
                    pass
            set_tray_status((0,200,0), "Nueva notificación")
            show_notification(msg, click_url, custom_title, priority)

    # Schedule next check in 100 ms
    main_root.after(100, process_queue)


# ----- Ntfy Listener Worker -----
def listen_ntfy_worker():
    headers = {"Accept":"text/event-stream"}
    while True:
        try:
            set_tray_status((200,0,0), "Conectado (esperando)")
            resp = requests.get(NTFY_URL, stream=True)
            for line in resp.iter_lines():
                if line:
                    try:
                        print("A.", line)
                        print("B.", line.decode("utf-8"))
                        data = json.loads(line.decode("utf-8"))
                        print("C.", data.get("event"))
                        notification_queue.put(data)
                    except Exception as e:
                        print("Error parsing message:", e, file=sys.stderr)
        except Exception as e:
            print("Connection lost:", e, file=sys.stderr)
            set_tray_status((100,180,255), "Desconectado - reintentando...")
            time.sleep(5)
# ----- Start Tray Icon & Tkinter Loop -----
def start_tray():
    global icon

    # Function to exit the app
    def on_exit(icon, item):
        icon.stop()
        sys.exit(0)

    # Create the tray icon
    icon = pystray.Icon(
        "iax_avisos",
        create_icon((200,0,0)),
        "iAvisos",
        menu=pystray.Menu(
            pystray.MenuItem("Salir", on_exit)
        )
    )

    # Start ntfy listener in a daemon thread
    threading.Thread(target=listen_ntfy_worker, daemon=True).start()

    # Run pystray icon in the main thread (blocking here is fine)
    threading.Thread(target=icon.run, daemon=True).start()

    # Start processing the notification queue (via after)
    main_root.after(100, process_queue)

    # Start Tkinter mainloop in a separate daemon thread so `after()` callbacks run
    main_root.mainloop()

# ----- Main -----
if __name__=="__main__":
    if getattr(sys, 'frozen', False):
        import ctypes
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    start_tray()
