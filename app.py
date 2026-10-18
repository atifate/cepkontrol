"""CepKontrol — attended Windows remote desktop."""
import ctypes
import json
import os
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk
import qrcode
from tkinter import messagebox

from PIL import Image, ImageTk
from transport import Session
from wire import make_code, parse_code, validate_url
from defaults import DEFAULT_SERVER
from pairing import TrustedStore
from diagnostics import configure_logging
from desktop import Tray, startup_enabled, set_startup

BG = '#0c1425'
CARD = '#152238'
TEXT = '#ecf2fc'
MUTED = '#9baec8'
ACCENT = '#46dfb2'
CONFIG = Path(os.environ.get('APPDATA', str(Path.home()))) / 'AcikDestek' / 'settings.json'
KEYS = {'Return': 'enter', 'BackSpace': 'backspace', 'Tab': 'tab', 'Escape': 'esc',
        'Delete': 'delete', 'Insert': 'insert', 'Home': 'home', 'End': 'end',
        'Prior': 'pageup', 'Next': 'pagedown', 'Left': 'left', 'Right': 'right',
        'Up': 'up', 'Down': 'down', 'Shift_L': 'shiftleft', 'Shift_R': 'shiftright',
        'Control_L': 'ctrlleft', 'Control_R': 'ctrlright', 'Alt_L': 'altleft',
        'Alt_R': 'altright', 'Super_L': 'winleft', 'Super_R': 'winright',
        'Caps_Lock': 'capslock', 'space': 'space'}


def label(parent, text, size=11, color=TEXT, **kw):
    return tk.Label(parent, text=text, font=('Segoe UI', size), bg=parent['bg'], fg=color, **kw)


def button(parent, text, command, primary=False):
    return tk.Button(parent, text=text, command=command, font=('Segoe UI', 11, 'bold'),
                     bg=ACCENT if primary else '#243750', fg=BG if primary else TEXT,
                     activebackground='#73ebc7', activeforeground=BG, relief='flat',
                     bd=0, padx=18, pady=11, cursor='hand2')


def entry(parent, var, **kw):
    return tk.Entry(parent, textvariable=var, bg='#0c182b', fg=TEXT, insertbackground=TEXT,
                    relief='flat', font=('Segoe UI', 11), highlightthickness=1,
                    highlightbackground='#304159', highlightcolor=ACCENT, **kw)


class App:
    def __init__(self, root):
        self.root = root
        root.title('CepKontrol · Kayıtlı telefon erişimi')
        root.geometry('920x660')
        root.minsize(780, 620)
        root.configure(bg=BG)
        try:
            root.iconbitmap(str(Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'assets' / 'icon.ico'))
        except tk.TclError:
            pass
        self.events = queue.Queue()
        self.session = None
        self.latest_frame = None
        self.frame_lock = threading.Lock()
        self.viewer = None
        self.consent = None
        self.phone_popup = None
        self.enrollment = None
        self.running = True
        self.tray = None
        self.instance = None
        self.retry_job = None
        self.start_job = None
        self.hide_job = None
        try:
            self.trust = TrustedStore(CONFIG.parent / 'phones.dat')
        except Exception:
            self.trust = None
        self.photo = None
        self.last_move = 0
        self.view_bounds = None
        self.server = tk.StringVar(value=DEFAULT_SERVER)
        try:
            self.server.set(json.loads(CONFIG.read_text(encoding='utf-8'))['server'])
        except (OSError, ValueError, KeyError):
            pass
        self.code = tk.StringVar()
        self.remote_code = tk.StringVar()
        self.status = tk.StringVar(value='Hazır · Bir bağlantı başlatın')
        self.host_control = tk.BooleanVar(value=self.trust.control if self.trust else True)
        self.viewer_control = tk.BooleanVar(value=True)
        self.build()
        self.poll_job = root.after(40, self.poll)
        root.protocol('WM_DELETE_WINDOW', self.hide)
        if self.trust and self.trust.enabled:
            self.start_job = root.after(250, self.resume_host)

    def build(self):
        outer = tk.Frame(self.root, bg=BG, padx=32, pady=24)
        outer.pack(fill='both', expand=True)
        label(outer, '↗  CepKontrol', 27).pack(anchor='w')
        label(outer, 'Kendi sunucun. İzinli bağlantı. Ücretsiz uzaktan destek.', 11, MUTED).pack(anchor='w', pady=(5, 24))
        settings = tk.Frame(outer, bg=BG)
        settings.pack(fill='x', pady=(0, 22))
        label(settings, 'Uçtan uca şifreli · Eşleşmiş telefonundan doğrudan erişim', 10, ACCENT).pack(side='left')
        button(settings, 'Ayarlar', self.settings).pack(side='right')
        cards = tk.Frame(outer, bg=BG)
        cards.pack(fill='both', expand=True)
        cards.columnconfigure((0, 1), weight=1, uniform='card')
        cards.rowconfigure(0, weight=1)
        host = tk.Frame(cards, bg=CARD, padx=22, pady=22)
        host.grid(row=0, column=0, sticky='nsew', padx=(0, 9))
        label(host, '01  Telefonundan kontrol et', 17).pack(anchor='w')
        label(host, 'Telefonunu bir kez QR ile eşleştir.\nSonra bilgisayardan onay gerekmez.', 11, MUTED, justify='left').pack(anchor='w', pady=(12, 18))
        self.share_button = button(host, 'Telefonu eşleştir / QR göster', self.pair_phone, True)
        self.share_button.pack(fill='x')
        label(host, 'BU BİLGİSAYARIN BAĞLANTI KODU', 9, MUTED).pack(anchor='w', pady=(20, 8))
        entry(host, self.code, state='readonly', readonlybackground='#0c182b').pack(fill='x', ipady=10)
        self.copy_button = button(host, 'Kodu kopyala', self.copy)
        self.copy_button.pack(fill='x', pady=(10, 12))
        tk.Checkbutton(host, text='Fare ve klavye kontrolüne izin ver', variable=self.host_control,
                       command=self.set_control, bg=CARD, fg=TEXT, selectcolor=BG,
                       activebackground=CARD, activeforeground=TEXT, font=('Segoe UI', 10)).pack(anchor='w')
        viewer = tk.Frame(cards, bg=CARD, padx=22, pady=22)
        viewer.grid(row=0, column=1, sticky='nsew', padx=(9, 0))
        label(viewer, '02  Bilgisayardan bağlan', 17).pack(anchor='w')
        label(viewer, 'Karşı tarafın bağlantı kodunu yapıştır.\nOnaydan sonra ekranı görüntüle.', 11, MUTED, justify='left').pack(anchor='w', pady=(12, 18))
        entry(viewer, self.remote_code).pack(fill='x', ipady=12)
        button(viewer, 'Kodu yapıştır', self.paste).pack(fill='x', pady=(8, 0))
        self.connect_button = button(viewer, 'Bağlan', self.connect, True)
        self.connect_button.pack(fill='x', pady=(12, 20))
        label(viewer, 'Şifreli ekran aktarımı\nFare, klavye ve Türkçe yazı desteği\nİstediğin an bağlantıyı kes', 11, MUTED, justify='left').pack(anchor='w')
        footer = tk.Frame(outer, bg=BG)
        footer.pack(fill='x', pady=(22, 0))
        label(footer, '', 10, ACCENT, textvariable=self.status, wraplength=610, justify='left').pack(side='left')
        button(footer, 'Bağlantıyı kes', self.disconnect).pack(side='right')

    def enable_tray(self, instance, background=False):
        self.instance = instance
        try:
            self.tray = Tray(Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'assets' / 'icon.ico')
        except Exception:
            self.tray = None
            self.status.set('Sistem tepsisi açılamadı; pencereyi kapatmak uygulamadan çıkar.')
        if background:
            self.hide_job = self.root.after(500, self.hide)

    def show(self):
        self.root.deiconify()
        self.root.state('normal')
        self.root.lift()

    def hide(self):
        if self.tray and self.tray.ready.is_set():
            self.root.withdraw()
        elif self.tray and self.tray.thread.is_alive():
            self.show()
            self.status.set('Sistem tepsisi hazırlanıyor; bağlantı arka planda açık kalacak.')
        else:
            self.tray = None
            self.quit()

    def emit(self, session, kind, payload):
        if kind == 'frame':
            with self.frame_lock:
                self.latest_frame = (session, payload)
        else:
            self.events.put((session, kind, payload))

    def begin(self, data, role, persistent=False):
        if self.session:
            messagebox.showinfo('Açık oturum', 'Önce mevcut bağlantıyı kesin.')
            return False
        session = Session(data, role, lambda k, p: self.emit(session, k, p), trusted_store=self.trust if persistent else None)
        session.control = self.host_control.get()
        self.session = session
        self.share_button.configure(state='disabled')
        self.connect_button.configure(state='disabled')
        self.status.set('Sunucuya bağlanılıyor…')
        session.start()
        return True

    def resume_host(self):
        if self.retry_job:
            self.root.after_cancel(self.retry_job)
        self.retry_job = None
        if self.running and self.trust and self.trust.enabled and not self.session:
            host = self.trust.host()
            self.pending_code = host['code']
            self.begin(host['data'], 'host', persistent=True)

    def pair_phone(self):
        if not self.trust:
            messagebox.showerror('Telefon kaydı', 'Şifreli telefon kayıt dosyası okunamıyor. Kayıt dosyasını düzeltmeden doğrudan erişim açılmaz.')
            return
        if self.session and (self.session.role != 'host' or self.session.approved.is_set() or not self.session.trusted_store):
            messagebox.showinfo('Açık bağlantı', 'Önce mevcut bağlantıyı kesin; ardından telefonu eşleştirin.')
            return
        try:
            self.trust.configure(validate_url(self.server.get().strip()))
            self.enrollment = self.trust.enrollment()
            if self.phone_popup:
                self.phone_popup.destroy()
                self.phone_popup = None
            if self.session:
                self.show_phone()
            else:
                self.resume_host()
        except Exception as exc:
            messagebox.showerror('Telefon eşleştirme', str(exc))

    def share(self):
        try:
            url = validate_url(self.server.get().strip())
            code, data = make_code(url)
            if self.begin(data, 'host'):
                self.pending_code = code
                CONFIG.parent.mkdir(parents=True, exist_ok=True)
                CONFIG.write_text(json.dumps({'server': url}), encoding='utf-8')
        except Exception as exc:
            messagebox.showerror('Bağlantı başlatılamadı', str(exc))

    def connect(self):
        try:
            self.begin(parse_code(self.remote_code.get().strip(), self.server.get().strip()), 'viewer')
        except Exception as exc:
            messagebox.showerror('Bağlantı kodu', str(exc))

    def copy(self):
        if self.code.get():
            self.root.clipboard_clear()
            self.root.clipboard_append(self.code.get())
            self.status.set('Kod kopyalandı · Yalnızca güvendiğiniz kişiyle paylaşın')

    def paste(self):
        try:
            self.remote_code.set(self.root.clipboard_get().strip())
        except tk.TclError:
            self.status.set('Panoda bağlantı kodu bulunamadı')

    def settings(self):
        popup = tk.Toplevel(self.root)
        popup.title('Sunucu ayarı')
        popup.configure(bg=CARD)
        popup.geometry('590x620')
        automatic = tk.BooleanVar(value=startup_enabled())
        def toggle_startup():
            try:
                set_startup(automatic.get())
            except OSError as exc:
                automatic.set(startup_enabled())
                messagebox.showerror('Windows başlangıcı',str(exc),parent=popup)
        tk.Checkbutton(popup,text='Windows’a giriş yaptığımda arka planda başlat',variable=automatic,
            command=toggle_startup,bg=CARD,fg=TEXT,selectcolor=BG,activebackground=CARD,activeforeground=TEXT).pack(anchor='w',padx=22,pady=(16,0))
        label(popup, 'Aktarım sunucusu', 17).pack(anchor='w', padx=22, pady=(20, 10))
        value = tk.StringVar(value=self.server.get())
        entry(popup, value).pack(fill='x', padx=22, ipady=10)
        def save():
            try:
                url = validate_url(value.get().strip())
                if self.trust and self.trust.host() and self.trust.host()['data']['url'] != url:
                    self.disconnect()
                    self.enrollment = None
                CONFIG.parent.mkdir(parents=True, exist_ok=True)
                CONFIG.write_text(json.dumps({'server': url}), encoding='utf-8')
                self.server.set(url)
                popup.destroy()
            except Exception as exc:
                messagebox.showerror('Sunucu adresi', str(exc), parent=popup)
        button(popup, 'Kaydet', save, True).pack(anchor='e', padx=22, pady=18)
        label(popup, 'Kayıtlı telefonlardan onaysız erişim', 15).pack(anchor='w', padx=22, pady=(5, 10))
        enabled = tk.BooleanVar(value=bool(self.trust and self.trust.enabled))
        def toggle():
            if not self.trust or not self.trust.host():
                enabled.set(False)
                messagebox.showinfo('Telefon eşleştirme', 'Önce ana ekrandan telefonunu QR kodla eşleştir.', parent=popup)
                return
            self.trust.enable(enabled.get())
            if enabled.get():
                self.resume_host()
            elif self.session and self.session.trusted_store:
                self.disconnect()
        tk.Checkbutton(popup, text='Kayıtlı telefonlar doğrudan bağlanabilsin', variable=enabled,
                       command=toggle, bg=CARD, fg=TEXT, selectcolor=BG,
                       activebackground=CARD, activeforeground=TEXT).pack(anchor='w', padx=22)
        phones_frame = tk.Frame(popup, bg=CARD)
        phones_frame.pack(fill='x', padx=22, pady=12)
        def refresh_phones():
            for child in phones_frame.winfo_children():
                child.destroy()
            phones = self.trust.phones() if self.trust else []
            if not phones:
                label(phones_frame, 'Henüz eşleşmiş telefon yok.', 11, MUTED).pack(anchor='w')
            for phone in phones:
                row = tk.Frame(phones_frame, bg=CARD)
                row.pack(fill='x', pady=4)
                label(row, phone['name'], 11).pack(side='left')
                def remove(identity=phone['id']):
                    self.trust.remove(identity)
                    if self.session and (self.session.phone_id == identity or not self.trust.enabled):
                        self.session.closed.set()
                        threading.Thread(target=self.session.close, daemon=True).start()
                    enabled.set(self.trust.enabled)
                    refresh_phones()
                button(row, 'Kaldır', remove).pack(side='right')
        refresh_phones()
        label(popup, 'Erişim için bu uygulama ve bilgisayar açık kalmalı.\nTelefon kaydı bu Windows kullanıcısına bağlı şifreli saklanır.', 10, MUTED, justify='left').pack(anchor='w', padx=22, pady=8)

    def set_control(self):
        if self.trust:
            self.trust.set_control(self.host_control.get())
        if self.session and self.session.role == 'host':
            with self.session.input_lock:
                self.session.control = self.host_control.get()
                if not self.session.control:
                    self.session.release_inputs()

    def poll(self):
        if not self.running:
            return
        commands = []
        if self.instance:
            commands.append(self.instance.command())
        if self.tray:
            while not self.tray.commands.empty():
                commands.append(self.tray.commands.get())
        for command in commands:
            if command == 'quit':
                self.quit()
                return
            if command == 'show':
                self.show()
        for _ in range(30):
            try:
                session, kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if session is not self.session:
                continue
            if kind == 'ready':
                if session.role == 'host':
                    self.code.set(self.pending_code)
                    self.status.set('Hazır · Kayıtlı telefonun doğrudan bağlanabilir' if session.trusted_store else 'Kod hazır · Bağlantı isteği bekleniyor (5 dakika)')
                    if session.trusted_store:
                        self.share_button.configure(state='normal')
                    if not session.trusted_store or self.enrollment:
                        self.show_phone()
                else:
                    self.status.set('Karşı tarafın onayı bekleniyor…')
            elif kind == 'consent':
                self.ask_consent(session, payload)
            elif kind == 'accepted':
                self.status.set('Bağlı · ' + ('Ekranınız paylaşılıyor' if session.role == 'host' else 'Uzak ekran açık'))
                if session.role == 'host' and self.phone_popup:
                    self.phone_popup.destroy()
                    self.phone_popup = None
                    self.enrollment = None
                if session.role == 'viewer':
                    self.open_viewer()
            elif kind == 'error':
                self.status.set(payload)
                if not session.trusted_store:
                    messagebox.showerror('Bağlantı bilgisi', payload, parent=self.root)
            elif kind == 'ended':
                resume = bool(session.trusted_store and self.trust.enabled and self.running)
                self.cleanup()
                if resume:
                    self.status.set('Telefon bağlantısı bekleniyor · Sunucuya yeniden bağlanılıyor…')
                    self.retry_job = self.root.after(2000, self.resume_host)
        with self.frame_lock:
            frame, self.latest_frame = self.latest_frame, None
        if frame and frame[0] is self.session and self.viewer:
            self.draw(frame[1])
        self.poll_job = self.root.after(40, self.poll)

    def ask_consent(self, session, name):
        popup = self.consent = tk.Toplevel(self.root)
        popup.title('Bağlantı izni gerekiyor')
        popup.configure(bg=CARD)
        popup.geometry('510x280')
        popup.attributes('-topmost', True)
        label(popup, 'Bir bilgisayar bağlanmak istiyor', 17).pack(pady=(24, 10))
        label(popup, name, 13, ACCENT).pack()
        label(popup, 'Onay verirseniz ekranınız görüntülenir.\nKontrol izni açıksa fare ve klavyeniz kullanılabilir.\nBilgisayar adı karşı tarafın beyanıdır.', 11, MUTED, justify='center').pack(pady=15)
        row = tk.Frame(popup, bg=CARD)
        row.pack()
        def respond(allowed):
            if self.consent is popup:
                self.consent = None
                popup.destroy()
                threading.Thread(target=session.accept, args=(allowed, self.host_control.get()), daemon=True).start()
        button(row, 'Reddet', lambda: respond(False)).pack(side='left', padx=6)
        button(row, 'Bağlantıya izin ver', lambda: respond(True), True).pack(side='left', padx=6)
        popup.protocol('WM_DELETE_WINDOW', lambda: respond(False))
        popup.after(45000, lambda: respond(False))

    def show_phone(self):
        if not self.session or self.session.role != 'host' or not self.code.get():
            return
        if self.phone_popup:
            self.phone_popup.lift()
            return
        url = self.session.data['url'].replace('wss://', 'https://', 1).replace('ws://', 'http://', 1)
        invitation = url + '/#code=' + self.code.get()
        if self.enrollment:
            invitation += '&pairId=' + self.enrollment['id'] + '&pairToken=' + self.enrollment['token']
        popup = self.phone_popup = tk.Toplevel(self.root)
        popup.title('Telefonunla QR kodu okut')
        popup.configure(bg=CARD)
        popup.geometry('450x540')
        popup.resizable(False, False)
        label(popup, 'Telefonunla QR kodu okut', 20).pack(pady=(24, 8))
        instructions = 'Telefonun kamerasını aç ve koda tut.\nBu telefon kaydedilir; sonraki girişlerde onay gerekmez.' if self.enrollment else 'Telefonun kamerasını aç ve koda tut.\nSonra bu bilgisayarda bağlantıya izin ver.'
        label(popup, instructions, 11, MUTED, justify='center').pack(pady=(0, 16))
        bitmap = qrcode.make(invitation).get_image().resize((292, 292), Image.Resampling.NEAREST)
        popup.qr_photo = ImageTk.PhotoImage(bitmap)
        tk.Label(popup, image=popup.qr_photo, bg='white', padx=8, pady=8).pack()
        def copy_link():
            self.root.clipboard_clear()
            self.root.clipboard_append(invitation)
            self.status.set('Telefon bağlantısı kopyalandı · Yalnızca kendi telefonuna gönder')
        button(popup, 'Telefon bağlantısını kopyala', copy_link, True).pack(pady=14)
        def close():
            self.phone_popup = None
            popup.destroy()
        popup.protocol('WM_DELETE_WINDOW', close)

    def open_viewer(self):
        view = self.viewer = tk.Toplevel(self.root)
        view.title('CepKontrol · Uzak ekran')
        view.geometry('1150x760')
        view.configure(bg=BG)
        toolbar = tk.Frame(view, bg=CARD, padx=12, pady=6)
        toolbar.pack(fill='x')
        label(toolbar, 'UZAK EKRAN', 10, ACCENT).pack(side='left', padx=8)
        tk.Checkbutton(toolbar, text='Kontrolü gönder', variable=self.viewer_control,
                       command=self.release, bg=CARD, fg=TEXT, selectcolor=BG,
                       activebackground=CARD, activeforeground=TEXT).pack(side='left', padx=10)
        button(toolbar, 'Tam ekran (F11)', self.fullscreen).pack(side='left', padx=8)
        button(toolbar, 'Bağlantıyı kes', self.disconnect).pack(side='right')
        self.canvas = tk.Canvas(view, bg='#080d16', highlightthickness=0, takefocus=True)
        self.canvas.pack(fill='both', expand=True)
        label(view, 'Kontrol için ekranın içine tıklayın · Esc: tuşları bırak ve tam ekrandan çık · Ctrl+Alt+Del desteklenmez', 9, MUTED).pack(pady=5)
        self.canvas.bind('<Motion>', self.move)
        for number, name in ((1, 'left'), (2, 'middle'), (3, 'right')):
            self.canvas.bind(f'<ButtonPress-{number}>', lambda e, b=name: self.pointer(e, 'down', b))
            self.canvas.bind(f'<ButtonRelease-{number}>', lambda e, b=name: self.pointer(e, 'up', b))
        self.canvas.bind('<MouseWheel>', lambda e: self.send_input({'kind': 'scroll', 'steps': int(e.delta / 120)}))
        self.canvas.bind('<KeyPress>', self.keydown)
        self.canvas.bind('<KeyRelease>', self.keyup)
        self.canvas.bind('<FocusOut>', lambda e: self.release())
        view.bind('<F11>', lambda e: self.fullscreen())
        view.protocol('WM_DELETE_WINDOW', self.disconnect)
        self.canvas.focus_set()
        self.heartbeat()

    def heartbeat(self):
        if self.viewer and self.session and self.session.approved.is_set():
            self.send_input({'kind': 'heartbeat'}, always=True)
            self.viewer.after(1000, self.heartbeat)

    def fullscreen(self):
        if self.viewer:
            self.viewer.attributes('-fullscreen', not self.viewer.attributes('-fullscreen'))

    def draw(self, image):
        w, h = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        image.thumbnail((w, h), Image.Resampling.BILINEAR)
        x, y = (w - image.width) // 2, (h - image.height) // 2
        self.view_bounds = (x, y, image.width, image.height)
        self.photo = ImageTk.PhotoImage(image)
        self.canvas.delete('all')
        self.canvas.create_image(x, y, image=self.photo, anchor='nw')

    def coords(self, event):
        if self.view_bounds:
            x, y, w, h = self.view_bounds
            if x <= event.x < x+w and y <= event.y < y+h:
                return (event.x-x)/w, (event.y-y)/h

    def pointer(self, event, kind, button_name):
        self.canvas.focus_set()
        pos = self.coords(event)
        if pos:
            self.send_input({'kind': kind, 'x': pos[0], 'y': pos[1], 'button': button_name})
        elif kind == 'up':
            self.release()

    def move(self, event):
        now = time.monotonic()
        if now - self.last_move > .035:
            self.last_move = now
            pos = self.coords(event)
            if pos:
                self.send_input({'kind': 'move', 'x': pos[0], 'y': pos[1]})

    def send_input(self, event, always=False):
        if self.session and self.session.role == 'viewer' and (always or self.viewer_control.get()):
            try:
                self.session.input(event)
            except Exception:
                self.disconnect()

    def release(self):
        self.send_input({'kind': 'release'}, always=True)

    def keydown(self, event):
        if event.keysym == 'F11':
            self.fullscreen()
            return 'break'
        if event.keysym == 'Escape':
            self.send_input({'kind': 'keydown', 'key': 'esc'})
            self.send_input({'kind': 'keyup', 'key': 'esc'})
            self.release()
            self.viewer.attributes('-fullscreen', False)
            self.root.focus_set()
            return 'break'
        if event.char and event.char.isprintable() and not event.state & 0x000c:
            self.send_input({'kind': 'text', 'text': event.char})
        else:
            self.send_input({'kind': 'keydown', 'key': KEYS.get(event.keysym, event.keysym.lower())})
        return 'break'

    def keyup(self, event):
        self.send_input({'kind': 'keyup', 'key': KEYS.get(event.keysym, event.keysym.lower())})
        return 'break'

    def disconnect(self, pause=True):
        if self.retry_job:
            self.root.after_cancel(self.retry_job)
            self.retry_job = None
        if pause and self.trust and self.trust.enabled:
            self.trust.enable(False)
        if self.session:
            self.session.closed.set()
            self.session.release_inputs()
            threading.Thread(target=self.session.close, daemon=True).start()
        self.cleanup()

    def cleanup(self):
        self.session = None
        self.code.set('')
        if self.consent:
            self.consent.destroy()
            self.consent = None
        if self.phone_popup:
            self.phone_popup.destroy()
            self.phone_popup = None
        if self.viewer:
            self.viewer.destroy()
            self.viewer = None
        self.view_bounds = None
        self.photo = None
        self.share_button.configure(state='normal')
        self.connect_button.configure(state='normal')
        self.status.set('Bağlantı kapalı · Yeni bağlantı için yeni kod oluşturun')

    def quit(self):
        if not self.running:
            return
        self.running = False
        if self.poll_job:
            self.root.after_cancel(self.poll_job)
            self.poll_job = None
        if self.start_job:
            self.root.after_cancel(self.start_job)
            self.start_job = None
        if self.hide_job:
            self.root.after_cancel(self.hide_job)
            self.hide_job = None
        self.disconnect(pause=False)
        if self.tray:
            self.tray.stop()
        self.root.destroy()


if __name__ == '__main__':
    from instance import Instance
    instance = Instance('quit' if '--quit' in sys.argv else 'background' if '--background' in sys.argv else 'show')
    if not instance.owner:
        instance.close()
        sys.exit(0)
    configure_logging()
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    root = tk.Tk()
    if '--background' in sys.argv:
        root.withdraw()
    app = App(root)
    if '--enable-startup' in sys.argv or startup_enabled():
        set_startup(True)
    app.enable_tray(instance, background='--background' in sys.argv)
    if '--pair-phone' in sys.argv:
        root.after(350, app.pair_phone)
    try:
        root.mainloop()
    finally:
        instance.close()
