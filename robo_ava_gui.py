"""Interface gráfica para o RoboAVA. A automação em ava_py permanece intacta."""

from __future__ import annotations

import json
import os
import queue
import ctypes
import subprocess
import sys
import threading
import time
from pathlib import Path
import psutil

if getattr(sys, "frozen", False):
    bundle = Path(sys._MEIPASS)
    os.environ.setdefault("TCL_LIBRARY", str(bundle / "tcl" / "tcl8.6"))
    os.environ.setdefault("TK_LIBRARY", str(bundle / "tcl" / "tk8.6"))
import tkinter as tk
from tkinter import messagebox, ttk

from ava_py.__main__ import ROOT
from ava_py.browser import PORTAL


PROJECT = Path(__file__).resolve().parent
ASSETS = Path(getattr(sys, "_MEIPASS", PROJECT)) / "assets"
PROFILE = "principal"
REPORT = ROOT / ".reports" / f"{PROFILE}.json"
DEMO_RA = "TESTE-235558"
DEMO_PASSWORD = "Luna#7g8K70jLbZ"
BG = "#050507"
CARD = "#111114"
TEXT = "#faf7ff"
MUTED = "#a99fba"
ACCENT = "#bd79ea"
NAVY = "#08090e"
BORDER = "#45315d"
FIELD = "#0d0d11"
LOG_BG = "#09090d"


class App:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("RoboAVA Luna")
        self.root.geometry("1040x680")
        self.root.minsize(870, 600)
        self.root.configure(bg=BG)
        self.logo_small = tk.PhotoImage(file=str(ASSETS / "luna_logo_small.png"))
        self.night_photo = tk.PhotoImage(file=str(ASSETS / "night_mountains.png"))
        self.root.iconphoto(True, self.logo_small)
        if sys.platform == "win32":
            self.root.iconbitmap(str(ASSETS / "luna.ico"))
        self._style_window(self.root)
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.process: subprocess.Popen[str] | None = None
        self.login_context = None
        self.login_ready = threading.Event()
        self.stop_login = threading.Event()
        self.stop_requested = threading.Event()
        self.busy = False
        self.paused = False
        self.suspended_pids: list[int] = []
        self.control_window: tk.Toplevel | None = None
        self.control_log: tk.Text | None = None
        self.control_count: tk.Label | None = None
        self.status = tk.StringVar(value="Pronto para começar")
        self.ra = tk.StringVar()
        self.password = tk.StringVar()
        self._build()
        self.root.after(100, self._drain)
        self.root.after(1500, self._refresh_report)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self) -> None:
        left = tk.Frame(self.root, bg=BG)
        left.place(relx=0, rely=0, relwidth=.48, relheight=1)
        self.art = tk.Canvas(self.root, bg=NAVY, highlightthickness=0)
        self.art.place(relx=.48, rely=0, relwidth=.52, relheight=1)
        self.art.bind("<Configure>", self._draw_night)

        brand = tk.Frame(left, bg=BG)
        brand.place(x=55, y=29)
        tk.Label(brand, image=self.logo_small, bg=BG).pack(side="left")
        tk.Label(brand, text="ROBOAVA  /  LUNA", bg=BG, fg=TEXT,
                 font=("Segoe UI Semibold", 11)).pack(side="left", padx=(10, 0))
        form = tk.Frame(left, bg=BG)
        form.place(relx=.5, rely=.48, relwidth=.76, anchor="center")
        tk.Label(form, text="Faça seu login.", bg=BG, fg=TEXT,
                 font=("Segoe UI Semibold", 29)).pack(anchor="w", pady=(0, 7))
        tk.Label(form, text="Entre com o RA e a senha da sua faculdade.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 30))
        self._field(form, "RA / matrícula", self.ra, 0, False)
        self._field(form, "Senha", self.password, 1, True)
        self.start_button = self._button(form, "Entrar  →", self._start, "#9254d9", TEXT)
        self.start_button.pack(fill="x", pady=(22, 9), ipady=4)
        self.continue_button = self._button(form, "Já fiz o login", self._continue, CARD, TEXT)
        self.continue_button.pack(fill="x", pady=(0, 7))
        self.continue_button.config(state="disabled")
        self.stop_button = self._button(form, "Cancelar", self._stop, BG, MUTED)
        self.stop_button.pack(fill="x")
        self.stop_button.config(state="disabled")

        footer = tk.Frame(left, bg=BG)
        footer.place(relx=.5, rely=.91, relwidth=.76, anchor="center")
        tk.Label(footer, textvariable=self.status, bg=BG, fg=ACCENT,
                 font=("Segoe UI Semibold", 9)).pack(anchor="w")
        self.count = tk.Label(footer, text="Nenhum relatório ainda", bg=BG,
                              fg=MUTED, font=("Segoe UI", 9))
        self.count.pack(anchor="w", pady=(3, 0))
        self.log = tk.Text(left, height=1, width=1, state="disabled")
        self._log("Pronto. Informe seu RA e senha para abrir o portal.")

    def _draw_night(self, event) -> None:
        canvas = self.art
        canvas.delete("all")
        w, h = max(event.width, 1), max(event.height, 1)
        canvas.create_image(w / 2, h / 2, image=self.night_photo)
        canvas.create_text(w * .07, h * .94, anchor="w",
                           text="UM NOVO JEITO DE ACOMPANHAR SEU AVA",
                           fill="#e8e8ee", font=("Segoe UI Semibold", 9))

    @staticmethod
    def _style_window(window: tk.Misc) -> None:
        """Use a dark title bar and violet system border on Windows 11."""
        if sys.platform != "win32":
            return
        try:
            window.update_idletasks()
            handle = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
            dark = ctypes.c_int(1)
            border = ctypes.c_uint(0x00B676BD)  # COLORREF: violet
            caption = ctypes.c_uint(0x000F0709)  # COLORREF: near black
            ctypes.windll.dwmapi.DwmSetWindowAttribute(handle, 20, ctypes.byref(dark), ctypes.sizeof(dark))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(handle, 34, ctypes.byref(border), ctypes.sizeof(border))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(handle, 35, ctypes.byref(caption), ctypes.sizeof(caption))
        except (AttributeError, OSError):
            pass

    def _field(self, parent: tk.Frame, label: str, variable: tk.StringVar,
               column: int, secret: bool) -> None:
        cell = tk.Frame(parent, bg=BG)
        cell.pack(fill="x", pady=(0, 17))
        tk.Label(cell, text=label, bg=BG, fg=MUTED,
                 font=("Segoe UI", 10)).pack(anchor="w")
        entry = tk.Entry(cell, textvariable=variable, show="•" if secret else "",
                         bg=FIELD, fg=TEXT, insertbackground=TEXT,
                         relief="flat", highlightbackground=BORDER,
                         highlightcolor=ACCENT, highlightthickness=1,
                         font=("Segoe UI", 12))
        entry.pack(fill="x", ipady=11, pady=(7, 0))
        if not secret:
            entry.focus_set()

    @staticmethod
    def _button(parent: tk.Frame, label: str, command, bg: str, fg: str) -> tk.Button:
        return tk.Button(parent, text=label, command=command, bg=bg, fg=fg,
                         activebackground=bg, activeforeground=fg, relief="flat",
                         cursor="hand2", padx=15, pady=8, font=("Segoe UI Semibold", 9))

    def _log(self, message: str) -> None:
        for widget in (self.log, self.control_log):
            if widget is None:
                continue
            widget.config(state="normal")
            widget.insert("end", message.rstrip() + "\n")
            widget.see("end")
            widget.config(state="disabled")

    def _start(self) -> None:
        ra, password = self.ra.get().strip(), self.password.get()
        if not ra or not password:
            messagebox.showinfo("Dados necessários", "Informe o RA e a senha para abrir o portal.")
            return
        if ra == DEMO_RA and password == DEMO_PASSWORD:
            self.password.set("")
            self.status.set("Acesso temporário. Bot aguardando início")
            self._show_controls()
            self._log("Acesso temporário liberado. Ao iniciar o bot, faça o login real no navegador do portal.")
            return
        self.password.set("")
        self.busy = True
        self.stop_login.clear()
        self.login_ready.clear()
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.status.set("Abrindo o portal...")
        self._log("Abrindo o navegador com o perfil principal...")
        threading.Thread(target=self._login, args=(ra, password), daemon=True).start()

    def _login(self, ra: str, password: str) -> None:
        try:
            from playwright.sync_api import sync_playwright

            profile = ROOT / ".profiles" / PROFILE
            profile.mkdir(parents=True, exist_ok=True)
            with sync_playwright() as playwright:
                options = {"user_data_dir": str(profile), "headless": False}
                if not getattr(sys, "frozen", False):
                    options["channel"] = "chrome"
                context = playwright.chromium.launch_persistent_context(**options)
                self.login_context = context
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(PORTAL, wait_until="domcontentloaded", timeout=30000)
                self._fill_login(page, ra, password)
                self.events.put(("login_ready", None))
                while not self.login_ready.is_set() and not self.stop_login.is_set():
                    time.sleep(0.2)
                context.close()
                self.login_context = None
                if not self.stop_login.is_set():
                    self.events.put(("control_ready", None))
        except Exception as exc:
            self.events.put(("error", str(exc)))
        finally:
            ra = password = ""
            self.events.put(("login_finished", None))

    def _fill_login(self, page, ra: str, password: str) -> None:
        """Fill visible login fields only; leave submission and extra checks to the user."""
        try:
            user_input = page.locator(
                'input[autocomplete="username"], input[name*="usuario" i], '
                'input[name*="user" i], input[name*="login" i], '
                'input[name*="ra" i], input[type="text"]'
            ).first
            pass_input = page.locator('input[type="password"]').first
            user_input.wait_for(state="visible", timeout=12000)
            pass_input.wait_for(state="visible", timeout=12000)
            user_input.fill(ra)
            pass_input.fill(password)
            self.events.put(("log", "RA e senha preenchidos no portal. Confira e conclua o login no navegador."))
        except Exception:
            self.events.put(("log", "Não localizei os campos de login. Preencha os dados diretamente no navegador."))

    def _continue(self) -> None:
        self.continue_button.config(state="disabled")
        self.status.set("Preparando controles...")
        self._log("Login concluído. Preparando a janela de controle...")
        self.login_ready.set()

    def _show_controls(self) -> None:
        self.control_window = tk.Toplevel(self.root)
        self.control_window.title("RoboAVA Luna — Controle do bot")
        self.control_window.geometry("820x560")
        self.control_window.minsize(680, 470)
        self.control_window.configure(bg=BG)
        self.control_window.iconphoto(True, self.logo_small)
        if sys.platform == "win32":
            self.control_window.iconbitmap(str(ASSETS / "luna.ico"))
        self._style_window(self.control_window)
        self.control_window.protocol("WM_DELETE_WINDOW", self._close)
        self.root.withdraw()
        shell = tk.Frame(self.control_window, bg=BG, padx=32, pady=28)
        shell.pack(fill="both", expand=True)
        brand = tk.Frame(shell, bg=BG)
        brand.pack(anchor="w")
        tk.Label(brand, image=self.logo_small, bg=BG).pack(side="left")
        tk.Label(brand, text="ROBOAVA  /  LUNA", bg=BG, fg=TEXT,
                 font=("Segoe UI Semibold", 10)).pack(side="left", padx=(8, 0))
        tk.Label(shell, text="Controle do bot", bg=BG, fg=TEXT,
                 font=("Segoe UI Semibold", 25)).pack(anchor="w", pady=(7, 3))
        tk.Label(shell, text="Acompanhe e controle a execução das atividades.", bg=BG,
                 fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 20))
        card = tk.Frame(shell, bg=CARD, padx=21, pady=19,
                        highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="x")
        tk.Label(card, text="ESTADO ATUAL", bg=CARD, fg=MUTED,
                 font=("Segoe UI Semibold", 9)).pack(anchor="w")
        info = tk.Frame(card, bg=CARD)
        info.pack(fill="x", pady=(6, 17))
        tk.Label(info, textvariable=self.status, bg=CARD, fg=TEXT,
                 font=("Segoe UI Semibold", 13)).pack(side="left")
        self.control_count = tk.Label(info, text=self.count.cget("text"), bg=CARD,
                                      fg=ACCENT, font=("Segoe UI Semibold", 10))
        self.control_count.pack(side="right")
        actions = tk.Frame(card, bg=CARD)
        actions.pack(fill="x")
        self.control_start_button = self._button(actions, "Iniciar bot", self._control_start, ACCENT, "#ffffff")
        self.control_start_button.pack(side="left")
        self.control_pause_button = self._button(actions, "Pausar bot", self._control_pause, "#332047", TEXT)
        self.control_pause_button.pack(side="left", padx=8)
        self.control_pause_button.config(state="disabled")
        self.control_stop_button = self._button(actions, "Encerrar bot", self._control_stop, "#4a203c", "#ffb4c9")
        self.control_stop_button.pack(side="right")
        log_card = tk.Frame(shell, bg=CARD, padx=18, pady=15,
                            highlightbackground=BORDER, highlightthickness=1)
        log_card.pack(fill="both", expand=True, pady=(17, 0))
        tk.Label(log_card, text="Atividade em tempo real", bg=CARD, fg=TEXT,
                 font=("Segoe UI Semibold", 13)).pack(anchor="w", pady=(0, 10))
        self.control_log = tk.Text(log_card, bg=LOG_BG, fg="#d8cde7",
                                   relief="flat", padx=13, pady=11, wrap="word",
                                   font=("Consolas", 9), state="disabled")
        self.control_log.pack(fill="both", expand=True)
        self._log("Pronto para iniciar o bot.")

    def _control_start(self) -> None:
        if self.process is not None and self.process.poll() is None:
            return
        self.stop_requested.clear()
        self.control_start_button.config(state="disabled")
        self.status.set("Iniciando a automação...")
        threading.Thread(target=self._run_backend, daemon=True).start()

    def _control_pause(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        suspended: list[int] = []
        try:
            worker = psutil.Process(self.process.pid)
            if self.paused:
                for pid in reversed(self.suspended_pids):
                    try:
                        psutil.Process(pid).resume()
                    except psutil.NoSuchProcess:
                        pass
                self.suspended_pids.clear()
                self.paused = False
            else:
                targets = worker.children(recursive=True) + [worker]
                for target in targets:
                    try:
                        target.suspend()
                        suspended.append(target.pid)
                    except psutil.NoSuchProcess:
                        pass
                self.suspended_pids = suspended
                self.paused = True
        except (psutil.Error, OSError) as exc:
            for pid in reversed(suspended):
                try:
                    psutil.Process(pid).resume()
                except psutil.Error:
                    pass
            self._log(f"Não foi possível alterar a pausa: {exc}")
            return
        self.status.set("Bot pausado" if self.paused else "Automação em andamento")
        self.control_pause_button.config(text="Retomar bot" if self.paused else "Pausar bot")
        self._log("Bot pausado." if self.paused else "Bot retomado.")

    def _control_stop(self) -> None:
        self._stop()
        self.status.set("Bot encerrado")
        self.control_start_button.config(state="disabled")
        self.control_pause_button.config(state="disabled", text="Pausar bot")

    def _run_backend(self) -> None:
        if getattr(sys, "frozen", False):
            command = [str(Path(sys.executable).with_name("RoboAVA-Worker.exe")),
                       "run", "--profile", PROFILE]
        else:
            command = [sys.executable, "-u", "-m", "ava_py", "run", "--profile", PROFILE]
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        hidden_console = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        try:
            if self.stop_requested.is_set():
                return
            self.process = subprocess.Popen(command, cwd=PROJECT, env=env, stdin=subprocess.PIPE,
                                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            text=True, encoding="utf-8", errors="replace", bufsize=1,
                                            creationflags=hidden_console)
            if self.stop_requested.is_set():
                self.process.terminate()
                return
            self.events.put(("running", None))
            # O back-end usa input() ao terminar; a linha fica disponível até esse ponto.
            self._send_enter()
            assert self.process.stdout is not None
            for line in self.process.stdout:
                self.events.put(("log", line.rstrip()))
            code = self.process.wait()
            self.events.put(("log", f"Processo encerrado (código {code})."))
        except Exception as exc:
            self.events.put(("error", str(exc)))
        finally:
            self.process = None
            self.events.put(("done", None))

    def _send_enter(self) -> None:
        if self.process and self.process.stdin:
            try:
                self.process.stdin.write("\n")
                self.process.stdin.flush()
            except OSError:
                pass

    def _stop(self) -> None:
        self.stop_requested.set()
        self.stop_login.set()
        self.login_ready.set()
        if self.process and self.process.poll() is None:
            try:
                worker = psutil.Process(self.process.pid)
                if self.paused:
                    for pid in reversed(self.suspended_pids):
                        try:
                            psutil.Process(pid).resume()
                        except psutil.NoSuchProcess:
                            pass
                for target in worker.children(recursive=True) + [worker]:
                    try:
                        target.terminate()
                    except psutil.NoSuchProcess:
                        pass
            except (psutil.Error, OSError):
                self.process.terminate()
        self.paused = False
        self.suspended_pids.clear()
        self._log("Interrupção solicitada.")

    def _drain(self) -> None:
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "log":
                    self._log(str(value))
                elif kind == "login_ready":
                    self.status.set("Conclua o acesso no navegador")
                    self.continue_button.config(state="normal")
                elif kind == "running":
                    self.status.set("Automação em andamento")
                    self.control_pause_button.config(state="normal")
                elif kind == "control_ready":
                    self.status.set("Login concluído. Bot aguardando início")
                    self._show_controls()
                elif kind == "error":
                    self._log(f"Erro: {value}")
                    self.status.set("Não foi possível continuar")
                    if self.control_window is None:
                        self.busy = False
                        self.start_button.config(state="normal")
                        self.stop_button.config(state="disabled")
                elif kind == "login_finished":
                    if self.control_window is None:
                        self.busy = False
                        self.start_button.config(state="normal")
                        self.stop_button.config(state="disabled")
                elif kind == "done":
                    self.busy = False
                    self.paused = False
                    self.suspended_pids.clear()
                    self.start_button.config(state="normal")
                    self.continue_button.config(state="disabled")
                    self.stop_button.config(state="disabled")
                    if self.control_window is not None:
                        self.control_start_button.config(state="normal")
                        self.control_pause_button.config(state="disabled", text="Pausar bot")
                    if self.status.get() == "Automação em andamento":
                        self.status.set("Execução encerrada")
        except queue.Empty:
            pass
        self.root.after(100, self._drain)

    def _refresh_report(self) -> None:
        try:
            data = json.loads(REPORT.read_text(encoding="utf-8"))
            activities = data.get("activities", [])
            done = sum(item.get("status") == "concluída" for item in activities)
            self.count.config(text=f"{done}/{len(activities)} atividades concluídas")
            if self.control_count is not None:
                self.control_count.config(text=f"{done}/{len(activities)} atividades concluídas")
        except (OSError, ValueError, TypeError):
            pass
        self.root.after(1500, self._refresh_report)

    def _close(self) -> None:
        self._stop()
        self.root.destroy()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in {"open", "scan", "status", "solve", "run", "setup-key"}:
        # O mesmo executável atende ao processo filho sem abrir outra janela.
        from ava_py.__main__ import main
        main()
    else:
        App().root.mainloop()
