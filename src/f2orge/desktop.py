"""A small offline Tkinter IDE for editing and running F²ORGE programs."""
from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .errors import ForgeError
from .interpreter import Interpreter
from .linear_algebra import Vector
from .units import Unit
from .visual_graph import NODE_INPUTS, NODE_SYMBOLS, VisualGraph


def run_source(text: str, path: Optional[Path] = None) -> Tuple[str, bool]:
    """Run editor contents with imports relative to the current file, returning output and status."""
    location = path.resolve() if path is not None else None
    interpreter = Interpreter(base_dir=location.parent if location else Path.cwd())
    output: List[str] = []
    interpreter.out = output.append
    try:
        interpreter.run(text, str(location) if location else "<editor>")
    except ForgeError as err:
        output.append(err.format())
        return "\n".join(output), False
    return "\n".join(output), True


class DesktopSession:
    """Persistent interpreter state shared by editor scripts and command-window input."""

    def __init__(self, base_dir: Optional[Path] = None):
        self.interpreter = Interpreter(base_dir=base_dir or Path.cwd(), plotter=self._record_plot)
        self.plots: List[Dict[str, object]] = []

    def _record_plot(self, title: str, x_label: str, y_label: str,
                     points: List[Tuple[float, float]]) -> None:
        self.plots.append({"title": title, "xLabel": x_label, "yLabel": y_label, "points": points})

    def execute(self, text: str, path: Optional[Path] = None) -> Tuple[str, bool]:
        output: List[str] = []
        interpreter = self.interpreter
        interpreter.out = output.append
        if path is not None:
            directory = path.resolve().parent
            interpreter.base_dir = directory
            interpreter._dirs = [directory]
        try:
            interpreter.run(text, str(path.resolve()) if path else "<command window>")
        except ForgeError as err:
            output.append(err.format())
            return "\n".join(output), False
        return "\n".join(output), True

    def clear(self) -> None:
        self.interpreter = Interpreter(base_dir=self.interpreter.base_dir, plotter=self._record_plot)
        self.plots.clear()

    def plot_data(self, command: str) -> Tuple[str, str, List[Tuple[float, float]]]:
        """Parse `plot y`, `plot x, y`, or `plot(x, y)` using vector workspace values."""
        match = re.fullmatch(
            r"\s*plot\s*(?:\(\s*([A-Za-z_]\w*)\s*(?:,\s*([A-Za-z_]\w*)\s*)?\)|"
            r"([A-Za-z_]\w*)(?:\s*,\s*([A-Za-z_]\w*))?)\s*",
            command,
        )
        if not match:
            raise ForgeError(
                "use plot y, plot x, y, or plot(x, y)",
                title="Invalid plot command",
            )
        if match.group(1) is not None:
            x_name, y_name = match.group(1), match.group(2) or match.group(1)
        elif match.group(4) is not None:
            x_name, y_name = match.group(3), match.group(4)
        else:
            x_name, y_name = None, match.group(3)
        variables = self.interpreter.variables
        y_value = variables.get(y_name)
        if not isinstance(y_value, Vector):
            raise ForgeError(f"'{y_name}' is not a vector in the workspace", title="Cannot plot")
        x_value = None
        if x_name is not None:
            x_value = variables.get(x_name)
            if not isinstance(x_value, Vector):
                raise ForgeError(f"'{x_name}' is not a vector in the workspace", title="Cannot plot")
        return plot_series(x_name, x_value, y_name, y_value)


def plot_series(x_name: Optional[str], x_value: Optional[Vector],
                y_name: str, y_value: Vector) -> Tuple[str, str, List[Tuple[float, float]]]:
    """Turn workspace vectors into (x label, y label, points) for a graph."""
    y_values = y_value.items
    if x_value is None:
        x_values: List[float] = list(range(1, len(y_values) + 1))
        x_label = "Index"
    else:
        x_quantities = x_value.items
        if len(x_quantities) != len(y_values):
            raise ForgeError("x and y vectors must have the same length", title="Cannot plot")
        x_unit = x_quantities[0].unit
        if any(value.dim != x_quantities[0].dim for value in x_quantities):
            raise ForgeError("all x values must have matching units", title="Cannot plot")
        x_values = [value.magnitude(x_unit) if x_unit else value.value for value in x_quantities]
        x_label = f"{x_name} ({x_unit.symbol()})" if x_unit else str(x_name)
    if len(y_values) < 2:
        raise ForgeError("a plot needs at least two points", title="Cannot plot")
    if any(value.dim != y_values[0].dim for value in y_values):
        raise ForgeError("all y values must have matching units", title="Cannot plot")
    y_unit = y_values[0].unit or Unit.from_dim(y_values[0].dim)
    y_data = [value.magnitude(y_unit) for value in y_values]
    y_label = f"{y_name} ({y_unit.symbol()})" if y_unit.symbol() else y_name
    return x_label, y_label, list(zip(x_values, y_data))


def launch_desktop_ide() -> None:
    """Launch the native desktop editor, importing Tkinter only when requested."""
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, simpledialog, ttk
    except ImportError as err:
        raise ForgeError(
            "Tkinter is not available in this Python installation",
            title="Cannot start desktop IDE",
            hint="Install or select a Python build that includes Tcl/Tk.",
        ) from err

    try:
        root = tk.Tk()
    except tk.TclError as err:
        raise ForgeError(
            f"cannot start the desktop window: {err}",
            title="Cannot start desktop IDE",
            hint="Check that a graphical desktop session is available.",
        ) from err

    current_path: Optional[Path] = None
    session = DesktopSession()
    visual_graph = VisualGraph()
    command_history: List[str] = []
    history_index = 0
    dark_mode = False
    wire_source: Optional[int] = None
    wire_mouse = (0.0, 0.0)
    dragging_node: Optional[int] = None
    resizing_node: Optional[int] = None
    drag_origin: Optional[Tuple[float, float]] = None
    size_origin: Optional[Tuple[float, float]] = None
    selected_node: Optional[int] = None
    grid_extent: Optional[Tuple[int, int, str]] = None

    def refresh_title() -> None:
        filename = current_path.name if current_path else "Untitled.forge"
        changed = " *" if editor.edit_modified() else ""
        root.title(f"F²ORGE IDE — {filename}{changed}")

    def set_status(text: str) -> None:
        status.set(text)

    def reset_modified() -> None:
        editor.edit_modified(False)
        refresh_title()

    def save_file() -> bool:
        nonlocal current_path
        if current_path is None:
            selected = filedialog.asksaveasfilename(
                title="Save F²ORGE program",
                defaultextension=".forge",
                filetypes=(("F²ORGE programs", "*.forge"), ("Equation files", "*.eq"), ("All files", "*.*")),
            )
            if not selected:
                return False
            current_path = Path(selected)
        try:
            current_path.write_text(editor.get("1.0", "end-1c"), encoding="utf-8")
        except OSError as err:
            messagebox.showerror("Could not save file", str(err), parent=root)
            return False
        reset_modified()
        set_status(f"Saved {current_path}")
        return True

    def confirm_discard() -> bool:
        if not editor.edit_modified():
            return True
        answer = messagebox.askyesnocancel("Unsaved changes", "Save changes before continuing?", parent=root)
        if answer is None:
            return False
        return save_file() if answer else True

    def new_file() -> None:
        nonlocal current_path
        if not confirm_discard():
            return
        current_path = None
        editor.delete("1.0", "end")
        reset_modified()
        set_status("New program")

    def open_file() -> None:
        nonlocal current_path
        if not confirm_discard():
            return
        selected = filedialog.askopenfilename(
            title="Open F²ORGE program",
            filetypes=(("F²ORGE files", "*.forge *.eq"), ("All files", "*.*")),
        )
        if not selected:
            return
        path = Path(selected)
        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError as err:
            messagebox.showerror("Could not open file", str(err), parent=root)
            return
        current_path = path
        editor.delete("1.0", "end")
        editor.insert("1.0", text)
        reset_modified()
        set_status(f"Opened {path}")

    def show_output(text: str) -> None:
        output.configure(state="normal")
        output.delete("1.0", "end")
        output.insert("1.0", text or "(No output)")
        output.configure(state="disabled")

    def refresh_workspace() -> None:
        workspace.delete(*workspace.get_children())
        for name, value in sorted(session.interpreter.variables.items()):
            workspace.insert("", "end", values=("Variable", name, str(value)))
        for name, equation in sorted(session.interpreter.equations.items()):
            signature = f"{', '.join(equation.inputs)} -> {', '.join(equation.outputs)}"
            workspace.insert("", "end", values=("Equation", name, signature))
        for name, kind in sorted(session.interpreter.object_types.items()):
            props = ", ".join(kind.properties)
            workspace.insert("", "end", values=("Object", name,
                                                f"{props} ({len(kind.formulas)} formula)"))

    def append_console(text: str) -> None:
        console.configure(state="normal")
        console.insert("end", text.rstrip() + "\n")
        console.see("end")
        console.configure(state="disabled")

    def run_program() -> None:
        session.plots.clear()
        result, success = session.execute(editor.get("1.0", "end-1c"), current_path)
        show_output(result)
        refresh_workspace()
        for plot in session.plots:
            draw_plot_data(str(plot["title"]), str(plot["xLabel"]), str(plot["yLabel"]),
                           plot["points"])
        set_status("Run completed" if success else "Run failed — see output")

    def draw_plot(command: str) -> None:
        x_label, y_label, points = session.plot_data(command)
        draw_plot_data(f"Plot: {y_label} vs {x_label}", x_label, y_label, points)

    def draw_plot_data(title: str, x_label: str, y_label: str,
                       points: List[Tuple[float, float]]) -> None:
        window = tk.Toplevel(root)
        window.title(title)
        window.geometry("760x500")
        canvas = tk.Canvas(window, background="white", highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        def redraw(_event=None) -> None:
            canvas.delete("all")
            width, height = max(canvas.winfo_width(), 100), max(canvas.winfo_height(), 100)
            left, right, top, bottom = 72, 24, 28, 60
            dark_plot = dark_mode
            grid_color = "#34383d" if dark_plot else "#e9e2d8"
            axis_color = "#68645e" if dark_plot else "#746b60"
            text_color = "#c5cbd3" if dark_plot else "#37332e"
            canvas.configure(background="#17191c" if dark_plot else "#fcfaf5")
            xs, ys = [p[0] for p in points], [p[1] for p in points]
            xmin, xmax = min(xs), max(xs)
            ymin, ymax = min(ys), max(ys)
            if xmin == xmax:
                xmin, xmax = xmin - 0.5, xmax + 0.5
            if ymin == ymax:
                pad = max(abs(ymin) * 0.05, 0.5)
                ymin, ymax = ymin - pad, ymax + pad
            xpad, ypad = (xmax - xmin) * 0.04, (ymax - ymin) * 0.04
            xmin, xmax, ymin, ymax = xmin - xpad, xmax + xpad, ymin - ypad, ymax + ypad

            def screen_x(value):
                return left + (value - xmin) / (xmax - xmin) * (width - left - right)

            def screen_y(value):
                return height - bottom - (value - ymin) / (ymax - ymin) * (height - top - bottom)

            for index in range(6):
                x = left + index * (width - left - right) / 5
                y = top + index * (height - top - bottom) / 5
                xv = xmin + index * (xmax - xmin) / 5
                yv = ymax - index * (ymax - ymin) / 5
                canvas.create_line(x, top, x, height - bottom, fill=grid_color)
                canvas.create_line(left, y, width - right, y, fill=grid_color)
                canvas.create_text(x, height - bottom + 16, text=f"{xv:.5g}", fill=text_color)
                canvas.create_text(left - 8, y, text=f"{yv:.5g}", anchor="e", fill=text_color)
            canvas.create_line(left, top, left, height - bottom, fill=axis_color)
            canvas.create_line(left, height - bottom, width - right, height - bottom, fill=axis_color)
            coordinates = [coordinate for x, y in points for coordinate in (screen_x(x), screen_y(y))]
            canvas.create_line(*coordinates, fill="#cf8656" if dark_plot else "#c76124",
                               width=2, smooth=False)
            canvas.create_text((left + width - right) / 2, height - 18, text=x_label, fill=text_color)
            canvas.create_text(18, (top + height - bottom) / 2, text=y_label, angle=90, fill=text_color)

        canvas.bind("<Configure>", redraw)
        redraw()

    def apply_theme() -> None:
        palette = {
            "background": "#17191c" if dark_mode else "#f5f2eb",
            "panel": "#1c1e22" if dark_mode else "#fcfaf5",
            "foreground": "#cbd1d9" if dark_mode else "#37332e",
            "muted": "#9ba4b0" if dark_mode else "#77746e",
            "grid": "#282c31" if dark_mode else "#ebe6de",
            "grid_major": "#353a40" if dark_mode else "#ded8ce",
            "selection": "#49362a" if dark_mode else "#f5e5d7",
            "node": "#202327" if dark_mode else "#fffdf8",
            "node_border": "#53575c" if dark_mode else "#d8cfc4",
            "wire": "#cf8656" if dark_mode else "#c9753c",
            "accent": "#d97635" if dark_mode else "#c76124",
        }
        style = ttk.Style(root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(".", background=palette["background"], foreground=palette["foreground"])
        style.configure("TFrame", background=palette["background"])
        style.configure("TLabel", background=palette["background"], foreground=palette["foreground"])
        style.configure("TLabelframe", background=palette["background"], foreground=palette["foreground"])
        style.configure("TLabelframe.Label", background=palette["background"], foreground=palette["foreground"])
        style.configure("TPanedwindow", background=palette["background"])
        style.configure("TButton", padding=(9, 5), background=palette["panel"],
                        foreground=palette["foreground"])
        style.map("TButton", background=[("active", palette["grid_major"])],
                  foreground=[("active", palette["foreground"])])
        style.configure("Accent.TButton", padding=(10, 5),
                        background=palette["accent"], foreground="#fffaf5")
        style.map("Accent.TButton",
                  background=[("active", "#b8521e" if not dark_mode else "#c66b34")],
                  foreground=[("active", "#fffaf5")])
        style.configure("Treeview", background=palette["panel"], fieldbackground=palette["panel"],
                        foreground=palette["foreground"])
        style.configure("Treeview.Heading", background=palette["background"], foreground=palette["foreground"])
        style.map("Treeview", background=[("selected", palette["selection"])],
                  foreground=[("selected", palette["foreground"])])
        style.configure("TNotebook", background=palette["background"])
        style.configure("TNotebook.Tab", padding=(10, 5))
        style.map("TNotebook.Tab",
                  background=[("selected", palette["panel"]), ("active", palette["grid"])],
                  foreground=[("selected", palette["accent"])])
        root.configure(background=palette["background"])
        for widget in (editor, output, console):
            widget.configure(background=palette["panel"], foreground=palette["foreground"],
                            insertbackground=palette["foreground"])
        theme_button.configure(text=f"Dark: {'On' if dark_mode else 'Off'}")
        redraw_visual_graph()
        set_status("Dark mode" if dark_mode else "Light mode")

    def toggle_theme() -> None:
        nonlocal dark_mode
        dark_mode = not dark_mode
        apply_theme()

    def redraw_visual_graph() -> None:
        nonlocal grid_extent
        canvas = visual_canvas
        dark = dark_mode
        background = "#17191c" if dark else "#f5f1e9"
        minor = "#282c31" if dark else "#e9e3da"
        major = "#353a40" if dark else "#d6cec2"
        text_color = "#cbd1d9" if dark else "#37332e"
        width = max(2400, max((node.x + node.width + 70 for node in visual_graph.nodes.values()), default=0))
        height = max(1600, max((node.y + node.height + 70 for node in visual_graph.nodes.values()), default=0))
        width = int(width // 100 + 1) * 100
        height = int(height // 100 + 1) * 100
        canvas.configure(scrollregion=(0, 0, width, height), background=background)
        extent = (width, height, background)
        if grid_extent != extent:
            canvas.delete("grid")
            for x in range(0, width + 1, 20):
                color = major if x % 100 == 0 else minor
                canvas.create_line(x, 0, x, height, fill=color, tags=("grid",))
            for y in range(0, height + 1, 20):
                color = major if y % 100 == 0 else minor
                canvas.create_line(0, y, width, y, fill=color, tags=("grid",))
            grid_extent = extent
        canvas.delete("wire")
        canvas.delete("node")
        canvas.delete("pin")
        canvas.delete("preview-wire")
        for (target_id, input_index), source_id in visual_graph.connections.items():
            source, target = visual_graph.nodes[source_id], visual_graph.nodes[target_id]
            sx, sy = source.x + source.width, source.y + source.height / 2
            tx, ty = target.x, target.y + 42 + input_index * 22
            canvas.create_line(sx, sy, sx + 48, sy, tx - 48, ty, tx, ty,
                               fill="#cf8656" if dark else "#c9753c", width=3,
                               smooth=True, arrow="last", tags=("wire",))
        header_colors = {
            "Input": "#76513a",
            "Constant": "#685541",
            "Script": "#59534f",
            "Function": "#59534f",
            "Call": "#5d5a46",
            "Compare": "#675344",
            "Output2": "#704b43",
            "Add": "#675344",
            "Subtract": "#675344",
            "Multiply": "#675344",
            "Divide": "#675344",
            "Power": "#675344",
            "Output": "#704b43",
        }
        light_header_colors = {
            "Input": "#bf6b3b",
            "Constant": "#a87c50",
            "Script": "#887b70",
            "Function": "#887b70",
            "Call": "#9a8b62",
            "Compare": "#9a765c",
            "Output2": "#a76351",
            "Add": "#9a765c",
            "Subtract": "#9a765c",
            "Multiply": "#9a765c",
            "Divide": "#9a765c",
            "Power": "#9a765c",
            "Output": "#a76351",
        }
        for node in visual_graph.nodes.values():
            x, y = node.x, node.y
            height = max(76, node.height)
            width = max(150, node.width)
            fill = "#202327" if dark else "#fffdf8"
            border = "#53575c" if dark else "#d8cfc4"
            header = header_colors[node.kind] if dark else light_header_colors[node.kind]
            if selected_node == node.id:
                border = "#cf8656" if dark else "#dd7a35"
            canvas.create_rectangle(x, y, x + width, y + height, fill=fill,
                                   outline=border, width=2, tags=("node", f"node:{node.id}"))
            canvas.create_rectangle(x, y, x + width, y + 28, fill=header,
                                   outline=header, tags=("node", f"node:{node.id}"))
            canvas.create_text(x + 10, y + 14, anchor="w", text=node.kind,
                               fill="#f3f4f6" if dark else "white",
                               font=("Segoe UI", 10, "bold"),
                               tags=("node", f"node:{node.id}"))
            if node.kind in ("Input", "Output", "Output2") and any(
                other.id != node.id
                and other.kind != node.kind
                and other.value == node.value
                for other in visual_graph.nodes.values()
            ):
                canvas.create_text(x + width - 10, y + 14, anchor="e", text="SHARED",
                                   fill="#ffe3cb" if dark else "white",
                                   font=("Segoe UI", 7, "bold"),
                                   tags=("node", f"node:{node.id}"))
            value_text = (node.value.splitlines()[0][:24] + "…"
                          if node.kind == "Script" and node.value else node.value)
            value_text = value_text if value_text else "connect inputs"
            canvas.create_text(x + 10, y + 48, anchor="w", text=value_text,
                               fill=text_color, font=("Consolas", 10),
                               tags=("node", f"node:{node.id}"))
            canvas.create_line(x + width - 13, y + height - 8,
                               x + width - 8, y + height - 13,
                               fill="#c1a68d" if not dark else "#8e7866",
                               width=2, tags=("resize", f"resize:{node.id}"))
            canvas.create_line(x + width - 8, y + height - 8,
                               x + width - 8, y + height - 13,
                               fill="#c1a68d" if not dark else "#8e7866",
                               width=2, tags=("resize", f"resize:{node.id}"))
            canvas.create_line(x + width - 8, y + height - 8,
                               x + width - 13, y + height - 8,
                               fill="#c1a68d" if not dark else "#8e7866",
                               width=2, tags=("resize", f"resize:{node.id}"))
            for index in range(NODE_INPUTS[node.kind]):
                py = y + 42 + index * 22
                canvas.create_oval(x - 6, py - 6, x + 6, py + 6,
                                   fill="#bd946d" if dark else "#c58a4d",
                                   outline=fill,
                                   tags=("pin", f"input:{node.id}:{index}"))
                canvas.create_text(x + 13, py, anchor="w", text=f"in {index + 1}",
                                   fill=text_color, font=("Segoe UI", 8),
                                   tags=("node", f"node:{node.id}"))
            if node.kind not in ("Output", "Output2", "Script"):
                canvas.create_oval(x + width - 6, y + height / 2 - 6,
                                   x + width + 6, y + height / 2 + 6,
                                   fill="#7f9b8a" if dark else "#849587",
                                   outline=fill,
                                   tags=("pin", f"output:{node.id}"))
            if node.kind in NODE_SYMBOLS:
                canvas.create_text(x + 95, y + height - 14, text=NODE_SYMBOLS[node.kind],
                                   fill="#b6b7b6" if dark else "#9a765c",
                                   font=("Segoe UI", 10, "bold"),
                                   tags=("node", f"node:{node.id}"))
        if wire_source is not None:
            node = visual_graph.nodes.get(wire_source)
            if node:
                canvas.create_line(node.x + node.width, node.y + node.height / 2,
                                   wire_mouse[0], wire_mouse[1],
                                   fill="#e39a67" if dark else "#dd7a35", width=2,
                                   dash=(5, 3), tags=("preview-wire",))
        canvas.tag_lower("grid")

    def edit_script_text(title: str, initial_value: str) -> Optional[str]:
        window = tk.Toplevel(root)
        window.title(title)
        window.transient(root)
        window.resizable(True, True)
        window.geometry("600x420")
        result: List[Optional[str]] = [None]
        ttk.Label(window, text="Write any valid F²ORGE statements.",
                  padding=(12, 12, 12, 6)).pack(anchor="w")
        script_editor = tk.Text(window, wrap="none", undo=True, font=("Consolas", 10),
                                padx=10, pady=8)
        script_editor.pack(fill="both", expand=True, padx=12)
        script_editor.insert("1.0", initial_value)
        actions = ttk.Frame(window, padding=12)
        actions.pack(fill="x")

        def finish(confirmed: bool) -> None:
            if confirmed:
                result[0] = script_editor.get("1.0", "end-1c")
            window.destroy()

        ttk.Button(actions, text="Cancel", command=lambda: finish(False)).pack(side="right")
        ttk.Button(actions, text="Save script", command=lambda: finish(True),
                   style="Accent.TButton").pack(side="right", padx=(0, 6))
        window.protocol("WM_DELETE_WINDOW", lambda: finish(False))
        window.grab_set()
        script_editor.focus_set()
        root.wait_window(window)
        return result[0]

    def confirm_shared_name(kind: str, value: str, exclude_id: Optional[int] = None) -> bool:
        if kind == "Output2":
            return True  # each unpacked name is checked by the graph when it compiles
        opposite = "Output" if kind == "Input" else "Input"
        if not any(node.id != exclude_id and node.kind == opposite and node.value == value
                   for node in visual_graph.nodes.values()):
            return True
        if kind == "Output":
            detail = (f"An Input node already uses '{value}'. This Output assigns that variable, "
                      "so dependent outputs will run after it.")
        else:
            detail = (f"An Output node already assigns '{value}'. This Input will read that "
                      "variable, and the graph compiler will run its output first.")
        return messagebox.askyesno(
            "Share this variable?", f"{detail}\n\nContinue and share the variable?",
            parent=root,
        )

    def add_visual_node(kind: str) -> None:
        value = ""
        if kind in ("Input", "Output"):
            value = simpledialog.askstring(f"{kind} node", "Variable name:", parent=root) or ""
            if not value:
                return
        elif kind == "Output2":
            value = simpledialog.askstring(
                "Two-output node", "Names to unpack, separated by commas (time, velocity):",
                parent=root) or ""
            if not value:
                return
        elif kind == "Call":
            value = simpledialog.askstring(
                "Call node", "Function or equation to call (area, Force, solveODE):",
                parent=root) or ""
            if not value:
                return
        elif kind == "Compare":
            value = simpledialog.askstring(
                "Compare node", "Comparison (<, <=, >, >=, ==, !=):", initialvalue="<=",
                parent=root) or ""
            if not value:
                return
        elif kind == "Function":
            value = simpledialog.askstring(
                "Function node", "Function (sin, sqrt, fft, ...):", parent=root
            ) or ""
            if not value:
                return
        elif kind == "Constant":
            value = simpledialog.askstring("Constant node", "F²ORGE value (e.g. 9.81 m/s^2):",
                                           parent=root) or ""
            if not value:
                return
        elif kind == "Script":
            value = edit_script_text("Add F²ORGE script", "# F²ORGE statements\n") or ""
            if not value.strip():
                return
        value = value.strip()
        if kind in ("Input", "Output") and not confirm_shared_name(kind, value):
            set_status("Shared variable cancelled")
            return
        try:
            index = len(visual_graph.nodes)
            visual_graph.add_node(kind, value, 100 + (index % 5) * 230, 100 + (index // 5) * 150)
            redraw_visual_graph()
            set_status(f"Added {kind} node")
        except ForgeError as err:
            messagebox.showerror("Could not add node", err.message, parent=root)

    def visual_click(event) -> None:
        nonlocal wire_source, dragging_node, resizing_node, drag_origin, size_origin
        nonlocal wire_mouse, selected_node
        visual_canvas.focus_set()
        x, y = visual_canvas.canvasx(event.x), visual_canvas.canvasy(event.y)
        items = visual_canvas.find_overlapping(x - 3, y - 3, x + 3, y + 3)
        tags = [tag for item in reversed(items) for tag in visual_canvas.gettags(item)]
        for tag in tags:
            parts = tag.split(":")
            try:
                if parts[0] == "resize" and len(parts) == 2:
                    resizing_node = int(parts[1])
                    selected_node = resizing_node
                    node = visual_graph.nodes[resizing_node]
                    drag_origin = (x, y)
                    size_origin = (node.width, node.height)
                    redraw_visual_graph()
                    return
                if parts[0] == "output" and len(parts) == 2:
                    wire_source = int(parts[1])
                    wire_mouse = (x, y)
                    redraw_visual_graph()
                    return
                if parts[0] == "input" and len(parts) == 3 and wire_source is not None:
                    visual_graph.connect(wire_source, int(parts[1]), int(parts[2]))
                    wire_source = None
                    redraw_visual_graph()
                    set_status("Nodes connected")
                    return
                if parts[0] == "node" and len(parts) == 2:
                    dragging_node = int(parts[1])
                    selected_node = dragging_node
                    drag_origin = (x, y)
                    redraw_visual_graph()
                    return
            except (ValueError, ForgeError) as err:
                wire_source = None
                redraw_visual_graph()
                messagebox.showerror("Invalid connection", getattr(err, "message", str(err)), parent=root)
                return
        if selected_node is not None:
            selected_node = None
            redraw_visual_graph()
        if wire_source is not None:
            wire_source = None
            redraw_visual_graph()

    def visual_drag(event) -> None:
        nonlocal drag_origin, size_origin, wire_mouse
        x, y = visual_canvas.canvasx(event.x), visual_canvas.canvasy(event.y)
        if wire_source is not None:
            wire_mouse = (x, y)
            redraw_visual_graph()
        elif resizing_node is not None and drag_origin is not None and size_origin is not None:
            node = visual_graph.nodes[resizing_node]
            node.width = min(900, max(150, size_origin[0] + x - drag_origin[0]))
            node.height = min(
                900,
                max(88, 62 + NODE_INPUTS[node.kind] * 22, size_origin[1] + y - drag_origin[1]),
            )
            redraw_visual_graph()
        elif dragging_node is not None and drag_origin is not None:
            node = visual_graph.nodes[dragging_node]
            node.x = max(0, node.x + x - drag_origin[0])
            node.y = max(0, node.y + y - drag_origin[1])
            drag_origin = (x, y)
            redraw_visual_graph()

    def visual_release(_event) -> None:
        nonlocal dragging_node, resizing_node, drag_origin, size_origin
        dragging_node = None
        resizing_node = None
        drag_origin = None
        size_origin = None

    def visual_double_click(_event) -> None:
        x, y = visual_canvas.canvasx(_event.x), visual_canvas.canvasy(_event.y)
        items = visual_canvas.find_overlapping(x - 3, y - 3, x + 3, y + 3)
        for item in reversed(items):
            for tag in visual_canvas.gettags(item):
                if tag.startswith("node:"):
                    node = visual_graph.nodes[int(tag.split(":")[1])]
                    if node.kind == "Script":
                        value = edit_script_text("Edit F²ORGE script", node.value)
                    elif node.kind in ("Input", "Constant", "Output", "Output2", "Call", "Compare"):
                        value = simpledialog.askstring(
                            f"Edit {node.kind} node", "Value:", initialvalue=node.value, parent=root
                        )
                    else:
                        value = None
                    if value is not None:
                        try:
                            value = value.strip()
                            probe = VisualGraph()
                            probe.add_node(node.kind, value)
                            if node.kind in ("Input", "Output") and not confirm_shared_name(
                                node.kind, value, exclude_id=node.id
                            ):
                                return
                            node.value = value.strip()
                            redraw_visual_graph()
                        except ForgeError as err:
                            messagebox.showerror("Invalid node value", err.message, parent=root)
                    break

    def delete_visual_node(_event=None) -> None:
        nonlocal selected_node, wire_source
        if selected_node is not None:
            visual_graph.remove_node(selected_node)
            selected_node = None
            wire_source = None
            redraw_visual_graph()
            set_status("Node deleted")
        else:
            set_status("Select a node to delete")

    def visual_select(event) -> None:
        nonlocal selected_node
        x, y = visual_canvas.canvasx(event.x), visual_canvas.canvasy(event.y)
        for item in reversed(visual_canvas.find_overlapping(x - 3, y - 3, x + 3, y + 3)):
            for tag in visual_canvas.gettags(item):
                if tag.startswith("node:"):
                    selected_node = int(tag.split(":")[1])
                    return

    def run_visual_graph() -> None:
        try:
            program = visual_graph.compile()
        except ForgeError as err:
            messagebox.showerror("Cannot run visual graph", err.message, parent=root)
            set_status("Visual graph is incomplete")
            return
        result, success = session.execute(program, current_path)
        show_output(result)
        refresh_workspace()
        main_tabs.select(script_tab)
        tabs.select(output_frame)
        set_status("Visual graph completed" if success else "Visual graph failed")

    def save_visual_graph() -> None:
        selected = filedialog.asksaveasfilename(
            title="Save visual graph", defaultextension=".fgraph",
            filetypes=(("F²ORGE visual graphs", "*.fgraph"), ("All files", "*.*")),
        )
        if not selected:
            return
        try:
            Path(selected).write_text(json.dumps(visual_graph.to_data(), indent=2), encoding="utf-8")
        except OSError as err:
            messagebox.showerror("Could not save visual graph", str(err), parent=root)
            return
        set_status(f"Saved visual graph {selected}")

    def open_visual_graph() -> None:
        selected = filedialog.askopenfilename(
            title="Open visual graph", filetypes=(("F²ORGE visual graphs", "*.fgraph"), ("All files", "*.*")),
        )
        if not selected:
            return
        try:
            data = json.loads(Path(selected).read_text(encoding="utf-8"))
            loaded = VisualGraph.from_data(data)
        except (OSError, json.JSONDecodeError, ForgeError) as err:
            messagebox.showerror("Could not open visual graph", getattr(err, "message", str(err)), parent=root)
            return
        nonlocal visual_graph
        visual_graph = loaded
        redraw_visual_graph()
        set_status(f"Opened visual graph {selected}")

    def submit_command(_event=None) -> None:
        nonlocal history_index
        command = command_entry.get().strip()
        if not command:
            return
        command_entry.delete(0, "end")
        command_history.append(command)
        history_index = len(command_history)
        append_console(f">>> {command}")
        if command in (":clear", "clear"):
            session.clear()
            show_output("")
            refresh_workspace()
            set_status("Workspace cleared")
            return
        if command == ":help":
            append_console("Enter F²ORGE expressions or assignments. plot(y) and plot(x, y) draw "
                           "workspace vectors, and a plot statement in a script opens its graph "
                           "after the run. :clear resets variables; :trace runs the editor's "
                           "program statement by statement; :profile reports where its time goes; "
                           ":vars lists values; Up/Down recalls commands.")
            return
        if command in (":trace", ":profile"):
            text = editor.get("1.0", "end-1c")
            try:
                if command == ":trace":
                    from .debug import trace_of

                    frames = trace_of(text, current_path.name if current_path else "<editor>",
                                      base_dir=current_path.parent if current_path else None)
                    for frame in frames:
                        append_console(f"{frame.line:>4}  {frame.kind:<11} {frame.source.strip()}")
                    append_console(f"{len(frames)} statements ran")
                else:
                    from .debug import profile

                    result = profile(text, current_path.name if current_path else "<editor>",
                                     base_dir=current_path.parent if current_path else None)
                    append_console(result.report())
                    if result.error is not None:
                        append_console(result.error.format())
                set_status("Trace complete" if command == ":trace" else "Profile complete")
            except ForgeError as err:
                append_console(err.format())
                set_status("Trace failed" if command == ":trace" else "Profile failed")
            return
        if re.match(r"^\s*plot(?:\s|\()", command):
            try:
                draw_plot(command)
                append_console("Opened plot window")
                set_status("Plot opened")
            except ForgeError as err:
                append_console(err.format())
                set_status("Plot failed")
            return
        session.plots.clear()
        result, success = session.execute(command, current_path)
        if result:
            append_console(result)
        for plot in session.plots:
            draw_plot_data(str(plot["title"]), str(plot["xLabel"]), str(plot["yLabel"]),
                           plot["points"])
        refresh_workspace()
        set_status("Command completed" if success else "Command failed")

    def move_history(direction: int) -> None:
        nonlocal history_index
        if not command_history:
            return
        history_index = min(max(history_index + direction, 0), len(command_history))
        command_entry.delete(0, "end")
        if history_index < len(command_history):
            command_entry.insert(0, command_history[history_index])

    root.title("F²ORGE IDE — Untitled.forge")
    root.geometry("1200x780")
    root.minsize(760, 500)
    toolbar = ttk.Frame(root, padding=(8, 8, 8, 4))
    toolbar.pack(fill="x")
    for label, command in (("New", new_file), ("Open", open_file), ("Save", save_file),
                           ("Run  F5", run_program), ("Clear Workspace", lambda: submit_clear())):
        style_name = "Accent.TButton" if label.startswith("Run") else "TButton"
        ttk.Button(toolbar, text=label, command=command, style=style_name).pack(
            side="left", padx=(0, 6)
        )
    theme_button = ttk.Button(toolbar, text="Dark: Off", command=toggle_theme)
    theme_button.pack(side="left", padx=(0, 6))

    panes = ttk.Panedwindow(root, orient="horizontal")
    panes.pack(fill="both", expand=True, padx=8, pady=4)
    workspace_frame = ttk.LabelFrame(panes, text="Workspace", padding=4)
    main_frame = ttk.Frame(panes)
    panes.add(workspace_frame, weight=1)
    panes.add(main_frame, weight=4)

    workspace = ttk.Treeview(workspace_frame, columns=("kind", "name", "value"),
                             show="headings", selectmode="browse")
    workspace.heading("kind", text="Type")
    workspace.heading("name", text="Name")
    workspace.heading("value", text="Value")
    workspace.column("kind", width=70, stretch=False)
    workspace.column("name", width=100, stretch=False)
    workspace.column("value", width=180)
    workspace.pack(fill="both", expand=True)

    main_tabs = ttk.Notebook(main_frame)
    main_tabs.pack(fill="both", expand=True)
    script_tab = ttk.Frame(main_tabs)
    visual_tab = ttk.Frame(main_tabs)
    main_tabs.add(script_tab, text="Script Editor")
    main_tabs.add(visual_tab, text="Blueprint")

    vertical = ttk.Panedwindow(script_tab, orient="vertical")
    vertical.pack(fill="both", expand=True)
    editor_frame = ttk.LabelFrame(vertical, text="Editor", padding=4)
    lower_frame = ttk.Frame(vertical)
    vertical.add(editor_frame, weight=3)
    vertical.add(lower_frame, weight=2)
    editor_scroll = ttk.Scrollbar(editor_frame)
    editor_scroll.pack(side="right", fill="y")
    editor = tk.Text(editor_frame, wrap="none", undo=True, font=("Consolas", 11),
                     yscrollcommand=editor_scroll.set)
    editor.pack(side="left", fill="both", expand=True)
    editor_scroll.configure(command=editor.yview)

    tabs = ttk.Notebook(lower_frame)
    tabs.pack(fill="both", expand=True)
    output_frame = ttk.Frame(tabs, padding=4)
    console_frame = ttk.Frame(tabs, padding=4)
    tabs.add(output_frame, text="Output")
    tabs.add(console_frame, text="Command Window")
    output_scroll = ttk.Scrollbar(output_frame)
    output_scroll.pack(side="right", fill="y")
    output = tk.Text(output_frame, wrap="word", state="disabled", font=("Consolas", 10),
                     yscrollcommand=output_scroll.set)
    output.pack(side="left", fill="both", expand=True)
    output_scroll.configure(command=output.yview)
    console_scroll = ttk.Scrollbar(console_frame)
    console_scroll.pack(side="right", fill="y")
    console = tk.Text(console_frame, wrap="word", state="disabled", font=("Consolas", 10),
                      yscrollcommand=console_scroll.set)
    console.pack(side="top", fill="both", expand=True)
    console_scroll.configure(command=console.yview)
    command_row = ttk.Frame(console_frame)
    command_row.pack(fill="x", pady=(4, 0))
    ttk.Label(command_row, text=">>>").pack(side="left", padx=(0, 6))
    command_entry = ttk.Entry(command_row)
    command_entry.pack(side="left", fill="x", expand=True)
    command_entry.bind("<Return>", submit_command)
    command_entry.bind("<Up>", lambda _event: (move_history(-1), "break")[1])
    command_entry.bind("<Down>", lambda _event: (move_history(1), "break")[1])

    visual_toolbar = ttk.Frame(visual_tab, padding=6)
    visual_toolbar.pack(fill="x")
    for kind in ("Input", "Constant", "Function", "Call", "Script", "Add", "Subtract", "Multiply",
                 "Divide", "Power", "Compare", "Output", "Output2"):
        ttk.Button(visual_toolbar, text=f"+ {kind}", command=lambda k=kind: add_visual_node(k)).pack(
            side="left", padx=(0, 4)
        )
    ttk.Button(visual_toolbar, text="Run Graph", command=run_visual_graph,
               style="Accent.TButton").pack(side="left", padx=(8, 4))
    ttk.Button(visual_toolbar, text="Open Graph", command=open_visual_graph).pack(side="left", padx=4)
    ttk.Button(visual_toolbar, text="Save Graph", command=save_visual_graph).pack(side="left", padx=4)
    ttk.Button(visual_toolbar, text="Delete Node", command=delete_visual_node).pack(side="left", padx=4)
    ttk.Label(visual_tab, text="Drag node headers to move · resize from the corner · double-click to edit · Delete removes the selected node · middle-drag to pan").pack(
        anchor="w", padx=8, pady=(0, 4)
    )
    graph_frame = ttk.Frame(visual_tab)
    graph_frame.pack(fill="both", expand=True, padx=6, pady=(0, 6))
    graph_y_scroll = ttk.Scrollbar(graph_frame, orient="vertical")
    graph_x_scroll = ttk.Scrollbar(graph_frame, orient="horizontal")
    graph_y_scroll.pack(side="right", fill="y")
    graph_x_scroll.pack(side="bottom", fill="x")
    visual_canvas = tk.Canvas(
        graph_frame, width=800, height=520, background="#f5f1e9",
        xscrollcommand=graph_x_scroll.set, yscrollcommand=graph_y_scroll.set,
        highlightthickness=0, takefocus=True,
    )
    visual_canvas.pack(side="left", fill="both", expand=True)
    graph_y_scroll.configure(command=visual_canvas.yview)
    graph_x_scroll.configure(command=visual_canvas.xview)
    visual_canvas.bind("<Button-1>", visual_click)
    visual_canvas.bind("<B1-Motion>", visual_drag)
    visual_canvas.bind("<ButtonRelease-1>", visual_release)
    visual_canvas.bind("<Double-Button-1>", visual_double_click)
    visual_canvas.bind("<Button-3>", lambda _event: cancel_wire())
    visual_canvas.bind("<Delete>", delete_visual_node)
    visual_canvas.bind("<ButtonPress-2>", lambda event: visual_canvas.scan_mark(event.x, event.y))
    visual_canvas.bind("<B2-Motion>", lambda event: visual_canvas.scan_dragto(event.x, event.y, gain=1))
    visual_canvas.bind("<MouseWheel>", lambda event: visual_canvas.yview_scroll(-int(event.delta / 120), "units"))
    visual_canvas.bind("<Shift-MouseWheel>",
                       lambda event: visual_canvas.xview_scroll(-int(event.delta / 120), "units"))

    def submit_clear() -> None:
        session.clear()
        show_output("")
        refresh_workspace()
        set_status("Workspace cleared")

    def cancel_wire() -> None:
        nonlocal wire_source
        wire_source = None
        redraw_visual_graph()

    status = tk.StringVar(value="Ready — F5 to run; Blueprint tab builds node graphs")
    ttk.Label(root, textvariable=status, anchor="w", padding=(8, 4)).pack(fill="x")
    editor.bind("<<Modified>>", lambda _event: refresh_title())
    root.bind("<Control-o>", lambda _event: open_file())
    root.bind("<Control-s>", lambda _event: save_file())
    root.bind("<F5>", lambda _event: run_program())
    root.protocol("WM_DELETE_WINDOW", lambda: root.destroy() if confirm_discard() else None)
    refresh_workspace()
    apply_theme()
    editor.focus_set()
    root.mainloop()
