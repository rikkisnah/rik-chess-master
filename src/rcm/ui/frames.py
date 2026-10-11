"""Mode frames. Each wraps one BoardView plus mode-specific controls."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

import chess

from rcm.modes import LocalSession, MachineSession, RemoteSession, ReplaySession, Session
from rcm.tutorial import Attempt, LessonRunner, Progress, load_lessons
from rcm.ui.board import BoardView

PROMO_CHOICES = [
    ("Queen", chess.QUEEN),
    ("Rook", chess.ROOK),
    ("Bishop", chess.BISHOP),
    ("Knight", chess.KNIGHT),
]


def ask_promotion(parent: tk.Misc) -> int:
    """Modal piece chooser. Returns a chess piece type."""
    win = tk.Toplevel(parent)
    win.title("Promote to")
    win.transient(parent.winfo_toplevel())
    choice = {"v": chess.QUEEN}
    for name, pt in PROMO_CHOICES:

        def pick(pt=pt):
            choice["v"] = pt
            win.destroy()

        ttk.Button(win, text=name, command=pick).pack(fill="x", padx=12, pady=3)
    win.protocol("WM_DELETE_WINDOW", win.destroy)
    win.grab_set()
    parent.wait_window(win)
    return choice["v"]


def move_rows(sans: list[str], start_white: bool = True) -> list[str]:
    rows, i = [], 0
    if not start_white and sans:
        rows.append(f"1... {sans[0]}")
        i = 1
    n = 1 if start_white else 2
    while i < len(sans):
        pair = sans[i : i + 2]
        rows.append(f"{n}. " + "  ".join(pair))
        i += 2
        n += 1
    return rows


class MoveList(tk.Listbox):
    def __init__(self, master, **kw):
        super().__init__(
            master, width=18, height=22, activestyle="none", exportselection=False, **kw
        )

    def show(self, game_sans: list[str], white_first: bool, highlight: int | None = None) -> None:
        self.delete(0, "end")
        for row in move_rows(game_sans, white_first):
            self.insert("end", row)
        if self.size():
            self.see("end" if highlight is None else min(self.size() - 1, highlight // 2))


class PlayFrame(ttk.Frame):
    """Local, machine, and remote play."""

    def __init__(
        self, master, session: Session, on_exit: Callable[[], None], ask_promo=ask_promotion
    ):
        super().__init__(master)
        self.session = session
        self.on_exit = on_exit
        self.ask_promo = ask_promo
        self.selected: int | None = None
        self.flipped = isinstance(session, MachineSession) and session.human_color == chess.BLACK
        if isinstance(session, RemoteSession):
            self.flipped = session.my_color == chess.BLACK

        self.board_view = BoardView(self, self.on_square)
        self.board_view.grid(row=0, column=0, rowspan=2, padx=8, pady=8)
        side = ttk.Frame(self)
        side.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)
        self.status = ttk.Label(
            side, text="", wraplength=210, justify="left", font=("TkDefaultFont", 11, "bold")
        )
        self.status.pack(anchor="w", pady=(0, 6))
        self.note = ttk.Label(side, text="", wraplength=210, justify="left", foreground="#a05000")
        self.note.pack(anchor="w", pady=(0, 6))
        self.moves = MoveList(side)
        self.moves.pack(fill="y", expand=True)
        self.explain_box = tk.Text(
            side,
            width=26,
            height=7,
            wrap="word",
            state="disabled",
            relief="flat",
            background="#f4f0e8",
        )
        self.buttons = ttk.Frame(self)
        self.buttons.grid(row=1, column=1, sticky="sew", padx=(0, 8), pady=8)
        self._build_buttons()
        session.listeners.append(self.refresh)
        self._job: str | None = None
        self._tick()
        self.refresh()

    # --- buttons -----------------------------------------------------
    def _btn(self, text: str, cmd: Callable[[], None], name: str) -> ttk.Button:
        b = ttk.Button(self.buttons, text=text, command=cmd)
        b.pack(fill="x", pady=1)
        setattr(self, f"btn_{name}", b)
        return b

    def _build_buttons(self) -> None:
        s = self.session
        self._btn("Flip board", self.flip, "flip")
        self._btn("Explain last move", s.request_explain, "explain")
        if isinstance(s, MachineSession):
            self._btn("Hint", s.request_hint, "hint")
            self._btn("Undo move", s.undo, "undo")
        elif isinstance(s, RemoteSession):
            self._btn("Offer draw", s.offer_draw, "draw")
            self._btn("Request takeback", s.request_takeback, "undo")
            self._btn("Reconnect", s.reconnect, "reconnect")
        else:
            self._btn("Undo move", s.undo, "undo")
            self.flip_var = tk.BooleanVar(value=getattr(s, "auto_flip", False))
            ttk.Checkbutton(
                self.buttons,
                text="Auto-flip after each move",
                variable=self.flip_var,
                command=lambda: s.set_auto_flip(self.flip_var.get()),
            ).pack(anchor="w")
        self._btn("Resign", self.resign, "resign")
        self._btn("Back to menu", self.on_exit, "exit")

    def flip(self) -> None:
        self.flipped = not self.flipped
        self.refresh()

    def resign(self) -> None:
        if not self.session.game.is_over():
            self.session.resign(
                self.session.my_color
                if isinstance(self.session, RemoteSession)
                else (
                    self.session.human_color if isinstance(self.session, MachineSession) else None
                )
            )

    # --- board interaction ------------------------------------------
    def on_square(self, sq: int) -> None:
        s = self.session
        if not s.user_can_move():
            return
        if self.selected is not None and sq in {
            m.to_square for m in s.legal_targets(self.selected)
        }:
            frm, self.selected = self.selected, None
            promo = None
            if s.game.needs_promotion(frm, sq):
                promo = self.ask_promo(self)
            s.move(frm, sq, promo)
            return
        piece = s.board.piece_at(sq)
        if piece and piece.color == s.turn and s.legal_targets(sq):
            self.selected = sq
        else:
            self.selected = None
        self.refresh()

    # --- refresh -----------------------------------------------------
    def refresh(self) -> None:
        s = self.session
        if isinstance(s, LocalSession) and s.auto_flip:
            self.flipped = s.flipped
        last = s.board.peek() if s.board.move_stack else None
        targets = (
            [m.to_square for m in s.legal_targets(self.selected)]
            if self.selected is not None
            else []
        )
        hint = getattr(s, "hint_move", None)
        self.board_view.set_state(
            s.board,
            flipped=self.flipped,
            last_move=last,
            selected=self.selected,
            targets=targets,
            hint_move=hint,
        )
        self.status.config(text=s.status())
        self.note.config(text=" ".join(x for x in (getattr(s, "notice", None), s.message) if x))
        white_first = chess.Board(s.game.start_fen).turn == chess.WHITE
        self.moves.show(s.game.san_moves(), white_first)
        self._show_explanation(s.current_explanation())
        self._update_buttons()

    def _show_explanation(self, text: str) -> None:
        if text:
            self.explain_box.pack(fill="x", pady=(6, 0))
        else:
            self.explain_box.pack_forget()
        self.explain_box.config(state="normal")
        self.explain_box.delete("1.0", "end")
        self.explain_box.insert("1.0", text)
        self.explain_box.config(state="disabled")

    def _update_buttons(self) -> None:
        s = self.session
        over = s.game.is_over()
        self.btn_explain.state(["!disabled" if s.game.moves and not s.explaining else "disabled"])
        if hasattr(self, "btn_hint"):
            self.btn_hint.state(["!disabled" if s.user_can_move() else "disabled"])
        if isinstance(s, RemoteSession):
            self.btn_draw.state(["!disabled" if s.connected and not over else "disabled"])
            self.btn_undo.state(
                ["!disabled" if s.connected and s.game.moves and not over else "disabled"]
            )
            self.btn_reconnect.state(["!disabled" if s.peer_gone else "disabled"])
            self._remote_prompts()
        self.btn_resign.state(["disabled" if over else "!disabled"])

    def _remote_prompts(self) -> None:
        """Answer incoming draw / takeback requests. Non-blocking: buttons appear in the frame."""
        s: RemoteSession = self.session  # type: ignore[assignment]
        want = (
            ("Accept draw", "Decline draw", s.draw_offer_pending, s.answer_draw),
            ("Accept takeback", "Decline takeback", s.takeback_pending, s.answer_takeback),
        )
        for name, (yes, no, pending, handler) in zip(("draw_q", "tb_q"), want, strict=True):
            frame = getattr(self, name, None)
            if pending and frame is None:
                f = ttk.Frame(self.buttons)
                f.pack(fill="x", pady=2)
                ttk.Button(f, text=yes, command=lambda h=handler: h(True)).pack(
                    side="left", expand=True, fill="x"
                )
                ttk.Button(f, text=no, command=lambda h=handler: h(False)).pack(
                    side="left", expand=True, fill="x"
                )
                setattr(self, name, f)
            elif not pending and frame is not None:
                frame.destroy()
                setattr(self, name, None)

    def _tick(self) -> None:
        if not self.winfo_exists():
            return
        self.session.pump()
        self._job = self.after(100, self._tick)

    def destroy(self) -> None:
        if self._job:
            self.after_cancel(self._job)
        if self.refresh in self.session.listeners:
            self.session.listeners.remove(self.refresh)
        self.session.close()
        super().destroy()


class ReplayFrame(ttk.Frame):
    def __init__(self, master, session: ReplaySession, on_exit: Callable[[], None]):
        super().__init__(master)
        self.session = session
        self.board_view = BoardView(self)
        self.board_view.interactive = False
        self.board_view.grid(row=0, column=0, rowspan=2, padx=8, pady=8)
        side = ttk.Frame(self)
        side.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)
        h = session.source.headers
        ttk.Label(
            side,
            text=f"{h.get('White')} vs {h.get('Black')}\n{h.get('Event')}  {h.get('Date', '')}",
            wraplength=230,
            font=("TkDefaultFont", 11, "bold"),
        ).pack(anchor="w")
        self.label = ttk.Label(side, text="")
        self.label.pack(anchor="w", pady=4)
        self.comment = tk.Text(
            side,
            width=28,
            height=6,
            wrap="word",
            state="disabled",
            relief="flat",
            background="#f4f0e8",
        )
        self.comment.pack(fill="x", pady=4)
        self.moves = MoveList(side)
        self.moves.pack(fill="y", expand=True)
        self.moves.bind("<<ListboxSelect>>", self._select_row)
        ctl = ttk.Frame(self)
        ctl.grid(row=1, column=1, sticky="sew", padx=(0, 8), pady=8)
        row = ttk.Frame(ctl)
        row.pack(fill="x")
        for text, cmd in (
            ("|<", lambda: session.goto(0)),
            ("<", session.back),
            (">", session.forward),
            (">|", lambda: session.goto(10_000)),
        ):
            ttk.Button(row, text=text, width=4, command=cmd).pack(
                side="left", expand=True, fill="x"
            )
        self.play_btn = ttk.Button(ctl, text="Play", command=self.toggle)
        self.play_btn.pack(fill="x", pady=2)
        self.speed = tk.DoubleVar(value=session.interval)
        ttk.Label(ctl, text="Seconds per move").pack(anchor="w")
        ttk.Scale(
            ctl,
            from_=0.5,
            to=6,
            variable=self.speed,
            command=lambda v: session.set_interval(float(v)),
        ).pack(fill="x")
        ttk.Button(ctl, text="Back to menu", command=on_exit).pack(fill="x", pady=(6, 0))
        session.listeners.append(self.refresh)
        self._job = None
        self.refresh()

    def toggle(self) -> None:
        if self.session.playing:
            self.session.pause()
        else:
            self.session.play()
        self._schedule()

    def _schedule(self) -> None:
        if self._job:
            self.after_cancel(self._job)
            self._job = None
        if self.session.playing:
            self._job = self.after(int(self.session.interval * 1000), self._advance)

    def _advance(self) -> None:
        self._job = None
        self.session.tick()
        self._schedule()

    def _select_row(self, _e=None) -> None:
        sel = self.moves.curselection()
        if sel:
            self.session.goto((sel[0] + 1) * 2)

    def refresh(self) -> None:
        s = self.session
        self.board_view.set_state(s.board, last_move=s.last_move)
        self.label.config(text=s.move_label())
        self.play_btn.config(text="Pause" if s.playing else "Play")
        self.comment.config(state="normal")
        self.comment.delete("1.0", "end")
        self.comment.insert("end", s.commentary)
        self.comment.config(state="disabled")
        self.moves.show(s.source.san_moves(), True, s.position)

    def destroy(self) -> None:
        if self._job:
            self.after_cancel(self._job)
        self.session.close()
        if self.refresh in self.session.listeners:
            self.session.listeners.remove(self.refresh)
        super().destroy()


class TutorialFrame(ttk.Frame):
    def __init__(self, master, on_exit: Callable[[], None], progress: Progress | None = None):
        super().__init__(master)
        self.progress = progress or Progress()
        self.lessons = load_lessons()
        self.runner: LessonRunner | None = None
        self.selected: int | None = None
        left = ttk.Frame(self)
        left.grid(row=0, column=0, sticky="ns", padx=8, pady=8)
        self.tree = ttk.Treeview(left, show="tree", height=24, selectmode="browse")
        self.tree.pack(fill="y", expand=True)
        self._fill_tree()
        self.tree.bind("<<TreeviewSelect>>", self._pick)
        self.board_view = BoardView(self, self.on_square)
        self.board_view.grid(row=0, column=1, padx=8, pady=8)
        right = ttk.Frame(self)
        right.grid(row=0, column=2, sticky="ns", padx=(0, 8), pady=8)
        self.title = ttk.Label(
            right, text="Pick a lesson", font=("TkDefaultFont", 13, "bold"), wraplength=240
        )
        self.title.pack(anchor="w")
        self.text = ttk.Label(right, text="", wraplength=240, justify="left")
        self.text.pack(anchor="w", pady=8)
        self.feedback = ttk.Label(
            right, text="", wraplength=240, justify="left", foreground="#1a6b1a"
        )
        self.feedback.pack(anchor="w", pady=4)
        self.next_btn = ttk.Button(right, text="Next", command=self.next)
        self.next_btn.pack(fill="x", pady=2)
        self.hint_btn = ttk.Button(right, text="Hint", command=self.hint)
        self.hint_btn.pack(fill="x", pady=2)
        ttk.Button(right, text="Back to menu", command=on_exit).pack(side="bottom", fill="x")
        self.after_reply: str | None = None
        self.board_view.interactive = False
        self.next_btn.state(["disabled"])
        self.hint_btn.state(["disabled"])

    def _fill_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        groups: dict[str, str] = {}
        for lesson in self.lessons:
            if lesson.group not in groups:
                groups[lesson.group] = self.tree.insert("", "end", text=lesson.group, open=True)
            mark = "✓ " if self.progress.is_done(lesson.id) else "   "
            self.tree.insert(groups[lesson.group], "end", iid=lesson.id, text=mark + lesson.title)

    def _pick(self, _e=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        lesson = next((x for x in self.lessons if x.id == sel[0]), None)
        if lesson:
            self.start(lesson.id)

    def start(self, lesson_id: str) -> None:
        lesson = next(x for x in self.lessons if x.id == lesson_id)
        self.runner = LessonRunner(lesson, self.progress)
        self.title.config(text=lesson.title)
        self.refresh()

    def refresh(self) -> None:
        r = self.runner
        if r is None:
            return
        if r.completed:
            self.text.config(text="Lesson complete - well done!")
            self.next_btn.state(["disabled"])
            self.hint_btn.state(["disabled"])
            self.board_view.interactive = False
            self._fill_tree()
            return
        s = r.step
        assert s is not None
        flipped = (s.type == "line" and s.color == chess.BLACK) or (
            s.type != "line" and chess.Board(s.fen).turn == chess.BLACK
        )
        self.text.config(text=s.text)
        self.board_view.interactive = r.interactive
        self.board_view.set_state(
            r.board,
            flipped=flipped,
            targets=[t for t in r.legal_targets(self.selected)]
            if self.selected is not None
            else [],
            selected=self.selected,
            last_move=r.board.peek() if r.board.move_stack else None,
        )
        self.next_btn.state(["!disabled" if s.type == "explain" else "disabled"])
        self.hint_btn.state(["!disabled" if r.interactive else "disabled"])

    def next(self) -> None:
        if self.runner:
            self.feedback.config(text="")
            self.runner.advance()
            self.selected = None
            self.refresh()

    def hint(self) -> None:
        if self.runner:
            self.feedback.config(text=self.runner.hint(), foreground="#1a4f8a")

    def on_square(self, sq: int) -> None:
        r = self.runner
        if r is None or not r.interactive:
            return
        if self.selected is not None and sq in r.legal_targets(self.selected):
            frm, self.selected = self.selected, None
            promo = None
            if any(
                x.from_square == frm and x.to_square == sq and x.promotion
                for x in r.board.legal_moves
            ):
                promo = self.ask_promotion()
            self.handle(chess.Move(frm, sq, promo))
            return
        p = r.board.piece_at(sq)
        self.selected = sq if p and p.color == r.board.turn and r.legal_targets(sq) else None
        self.refresh()

    def ask_promotion(self) -> int:
        return ask_promotion(self)

    def handle(self, move: chess.Move) -> Attempt:
        r = self.runner
        assert r is not None
        a = r.attempt(move)
        self.feedback.config(text=a.message, foreground="#1a6b1a" if a.ok else "#a01a1a")
        self.refresh()
        if a.ok and a.step_done:
            self.after(900 if a.reply else 600, self.next)
        return a
