"""Main window, menu, and mode switching."""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import chess

from rcm import paths
from rcm.core import Game, PgnError, read_file
from rcm.modes import (
    LocalSession,
    MachineSession,
    RemoteSession,
    ReplaySession,
    Session,
    list_games,
)
from rcm.net import NetSession, Relay
from rcm.net.client import NetError
from rcm.ui.frames import PlayFrame, ReplayFrame, TutorialFrame


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("rik-chess-master")
        self.frame: ttk.Frame | None = None
        self.session: Session | None = None
        self.local_relay: Relay | None = None
        self._build_menu()
        root.protocol("WM_DELETE_WINDOW", self.quit)
        self.show_home()

    # --- menu --------------------------------------------------------
    def _build_menu(self) -> None:
        m = tk.Menu(self.root)
        game = tk.Menu(m, tearoff=0)
        game.add_command(label="Home", command=self.show_home)
        game.add_separator()
        game.add_command(label="Save game...", command=self.save_dialog)
        game.add_command(label="Load game...", command=self.load_dialog)
        game.add_separator()
        game.add_command(label="Quit", command=self.quit)
        m.add_cascade(label="Game", menu=game)
        modes = tk.Menu(m, tearoff=0)
        modes.add_command(label="Tutorial", command=self.start_tutorial)
        modes.add_command(label="Famous Games", command=self.show_famous)
        modes.add_command(label="Two Player (local)", command=self.start_local)
        modes.add_command(label="Two Player (remote)...", command=self.remote_dialog)
        modes.add_command(label="Play vs Machine...", command=self.machine_dialog)
        m.add_cascade(label="Mode", menu=modes)
        self.root.config(menu=m)

    # --- frames ------------------------------------------------------
    def _swap(self, frame: ttk.Frame | None) -> None:
        if self.frame is not None:
            self.frame.destroy()
        self.frame = frame
        self.session = getattr(frame, "session", None) if frame else None
        if frame is not None:
            frame.pack(fill="both", expand=True)

    def show_home(self) -> None:
        f = ttk.Frame(self.root, padding=40)
        ttk.Label(f, text="rik-chess-master", font=("TkDefaultFont", 24, "bold")).pack(pady=(0, 20))
        for text, cmd in (
            ("Tutorial", self.start_tutorial),
            ("Famous Games", self.show_famous),
            ("Two Player (local)", self.start_local),
            ("Two Player (remote)", self.remote_dialog),
            ("Play vs Machine", self.machine_dialog),
        ):
            ttk.Button(f, text=text, command=cmd, width=28).pack(pady=4, ipady=6)
        self._swap(f)
        self.session = None

    def start_session(self, session: Session) -> None:
        self._swap(PlayFrame(self.root, session, self.show_home))
        if isinstance(session, MachineSession):
            session.start()
            if session.notice:
                messagebox.showwarning("Master level unavailable", session.notice, parent=self.root)

    def start_local(self) -> None:
        self.start_session(LocalSession(Game()))

    def start_tutorial(self) -> None:
        self._swap(TutorialFrame(self.root, self.show_home))

    def show_famous(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("Famous Games")
        win.transient(self.root)
        games = list_games()
        lb = tk.Listbox(win, width=70, height=min(12, max(4, len(games))))
        for g in games:
            lb.insert("end", f"{g.white} vs {g.black} ({g.date[:4]}) - {g.title}")
        lb.pack(padx=10, pady=10)

        def go(_e=None):
            sel = lb.curselection()
            if sel:
                path = games[sel[0]].path
                win.destroy()
                self._swap(ReplayFrame(self.root, ReplaySession.from_path(path), self.show_home))

        lb.bind("<Double-Button-1>", go)
        ttk.Button(win, text="Watch", command=go).pack(pady=(0, 10))

    # --- machine -----------------------------------------------------
    def machine_dialog(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("Play vs Machine")
        win.transient(self.root)
        level = tk.StringVar(value="club")
        color = tk.StringVar(value="white")
        for text, val in (
            ("Beginner (random, under 800)", "beginner"),
            ("Club (1200-1500)", "club"),
            ("Master (Stockfish if installed)", "master"),
        ):
            ttk.Radiobutton(win, text=text, variable=level, value=val).pack(
                anchor="w", padx=14, pady=2
            )
        ttk.Separator(win).pack(fill="x", pady=6)
        for text, val in (("Play White", "white"), ("Play Black", "black")):
            ttk.Radiobutton(win, text=text, variable=color, value=val).pack(anchor="w", padx=14)

        def go():
            win.destroy()
            self.start_session(
                MachineSession(level.get(), chess.WHITE if color.get() == "white" else chess.BLACK)
            )

        ttk.Button(win, text="Start", command=go).pack(pady=10)

    # --- remote ------------------------------------------------------
    def remote_dialog(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("Two Player (remote)")
        win.transient(self.root)
        url = tk.StringVar(value=paths.relay_url())
        name = tk.StringVar(value="Player")
        code = tk.StringVar()
        ttk.Label(win, text="Relay URL").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(win, textvariable=url, width=34).grid(row=0, column=1, padx=8)
        ttk.Label(win, text="Your name").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(win, textvariable=name, width=34).grid(row=1, column=1, padx=8)
        ttk.Label(win, text="Room code (to join)").grid(row=2, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(win, textvariable=code, width=34).grid(row=2, column=1, padx=8)
        local = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            win, text="Host on this machine (starts a local relay for LAN play)", variable=local
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=8)

        def host():
            try:
                target = url.get()
                if local.get():
                    self.local_relay = self.local_relay or Relay("0.0.0.0", 0)
                    port = (
                        self.local_relay.port
                        if self.local_relay.running
                        else self.local_relay.start()
                    )
                    target = f"ws://127.0.0.1:{port}"
                    messagebox.showinfo(
                        "Local relay",
                        f"Others join with relay URL ws://<your-ip>:{port}",
                        parent=win,
                    )
                s = RemoteSession.host(NetSession(target), name=name.get() or "Host")
            except NetError as e:
                messagebox.showerror("Cannot host", str(e), parent=win)
                return
            win.destroy()
            self.start_session(s)
            messagebox.showinfo(
                "Room code",
                f"Share this room code with your opponent:\n\n{s.room}",
                parent=self.root,
            )

        def join():
            try:
                s = RemoteSession.join(
                    NetSession(url.get()), code.get(), name=name.get() or "Guest"
                )
            except NetError as e:
                messagebox.showerror("Cannot join", str(e), parent=win)
                return
            win.destroy()
            self.start_session(s)

        row = ttk.Frame(win)
        row.grid(row=4, column=0, columnspan=2, pady=10)
        ttk.Button(row, text="Host a game", command=host).pack(side="left", padx=6)
        ttk.Button(row, text="Join a game", command=join).pack(side="left", padx=6)

    # --- save / load -------------------------------------------------
    def save_dialog(self) -> None:
        if not isinstance(self.session, Session):
            messagebox.showinfo("Save", "Start a game first.", parent=self.root)
            return
        path = filedialog.asksaveasfilename(
            parent=self.root,
            defaultextension=".pgn",
            filetypes=[("PGN", "*.pgn")],
            confirmoverwrite=False,
        )
        if path:
            self.save_to(Path(path))

    def save_to(self, path: Path) -> bool:
        """Never overwrites without asking. Returns True if saved."""
        assert isinstance(self.session, Session)
        overwrite = False
        if path.exists():
            if not messagebox.askyesno(
                "Overwrite?", f"{path.name} already exists. Replace it?", parent=self.root
            ):
                return False
            overwrite = True
        self.session.save(path, overwrite=overwrite)
        return True

    def load_dialog(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.root, filetypes=[("PGN", "*.pgn"), ("All", "*")]
        )
        if path:
            self.load_from(Path(path))

    def load_from(self, path: Path) -> bool:
        try:
            game = read_file(path)
        except (PgnError, OSError) as e:
            messagebox.showerror("Cannot load game", f"{path.name}:\n{e}", parent=self.root)
            return False
        self.resume_game(game)
        return True

    def resume_game(self, game: Game) -> None:
        mode = game.headers.get("RCM_Mode", "two_player_local")
        if mode == "vs_machine":
            s: Session = MachineSession.resume(game)
        elif mode == "two_player_remote":
            if not messagebox.askyesno(
                "Remote game", "Resume this game as a new hosted room?", parent=self.root
            ):
                return
            try:
                s = RemoteSession.host(NetSession(paths.relay_url()), game=game)
            except NetError as e:
                messagebox.showerror("Cannot host", str(e), parent=self.root)
                return
        else:
            s = LocalSession(game)
        self.start_session(s)

    def offer_resume(self) -> None:
        p = paths.autosave_path()
        if not p.exists():
            return
        try:
            game = read_file(p)
        except (PgnError, OSError):
            return
        if (
            game.moves
            and not game.is_over()
            and messagebox.askyesno(
                "Resume game?",
                f"An unfinished game was autosaved ({len(game.moves)} moves). Resume it?",
                parent=self.root,
            )
        ):
            self.resume_game(game)

    def quit(self) -> None:
        if self.local_relay:
            self.local_relay.stop()
        self._swap(None)
        self.root.destroy()


def main() -> None:
    try:
        root = tk.Tk()
    except tk.TclError as e:
        print(f"rcm needs a display: {e}", file=sys.stderr)
        raise SystemExit(1) from e
    ttk.Style().theme_use("clam" if "clam" in ttk.Style().theme_names() else "default")
    app = App(root)
    root.after(300, app.offer_resume)
    root.mainloop()


if __name__ == "__main__":
    main()
