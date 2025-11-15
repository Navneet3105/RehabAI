# therapist_page.py
import tkinter as tk
from tkinter import messagebox, scrolledtext, simpledialog
import json
from datetime import datetime
from exercise_tracker import OPTIMAL_RANGES, record_custom_exercise, load_custom_exercises, pick_primary_joint_from_limits
import os

DB = "database.json"
EX_FILE = "exercises.json"

def load_db():
    if not os.path.exists(DB):
        with open(DB, "w") as f:
            json.dump({"therapists": {}, "patients": {}}, f, indent=4)
    with open(DB, "r") as f:
        return json.load(f)

def save_db(db):
    with open(DB, "w") as f:
        json.dump(db, f, indent=4)

def _ensure_patient_structure(db, username):
    p = db["patients"].setdefault(username, {})
    p.setdefault("messages", {})
    p["messages"].setdefault("from_therapist", [])
    p["messages"].setdefault("from_patient", [])
    p.setdefault("assigned", {})
    p.setdefault("assigned_sets", {})
    p.setdefault("sets_completed", {})
    p.setdefault("completed", {})
    p.setdefault("angle_stats", {})
    return p

def load_exercises_file():
    if not os.path.exists(EX_FILE):
        with open(EX_FILE, "w") as f:
            json.dump({"custom_exercises": {}}, f, indent=4)
    with open(EX_FILE, "r") as f:
        return json.load(f)

def save_exercises_file(data):
    with open(EX_FILE, "w") as f:
        json.dump(data, f, indent=4)
    # mirror into DB snapshot too
    db = load_db()
    db.setdefault("exercises", {})
    for k,v in data.get("custom_exercises", {}).items():
        db["exercises"][k] = db["exercises"].get(k, {})
        # copy joints and any metadata
        db["exercises"][k]["joints"] = v.get("joints")
        if "default_sets" in v:
            db["exercises"][k]["default_sets"] = v.get("default_sets")
        if "optimal_range" in v:
            db["exercises"][k]["optimal_range"] = v.get("optimal_range")
        db["exercises"][k]["created"] = v.get("created")
    save_db(db)

class ScrollableFrame(tk.Frame):
    """A vertically scrollable frame that expands to the width of its container."""
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self.v_scroll = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.v_scroll.set)

        self.v_scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        # This frame holds the actual widgets
        self.inner = tk.Frame(self.canvas)
        self.inner_id = self.canvas.create_window((0,0), window=self.inner, anchor="nw")

        # Bindings to resize canvas scrollregion
        self.inner.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Mousewheel support
        self.inner.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_frame_configure(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        # Make the inner frame match the canvas width
        canvas_width = event.width
        self.canvas.itemconfig(self.inner_id, width=canvas_width)

    def _on_mousewheel(self, event):
        # For Windows and Mac typical delta are different; normalize.
        delta = int(-1*(event.delta/120))
        self.canvas.yview_scroll(delta, "units")

def therapist_window(username, login_window):
    try:
        login_window.destroy()
    except Exception:
        pass

    db = load_db()
    win = tk.Tk()
    win.title(f"Therapist - {username}")
    # start slightly larger to show many sections; user can resize
    win.geometry("980x920")

    tk.Label(win, text=f"Therapist: {username}", font=("Arial", 16)).pack(pady=6)

    # Main scrollable area
    sf = ScrollableFrame(win)
    sf.pack(fill="both", expand=True, padx=8, pady=(0,8))

    # --- Patient selection ---
    top_frame = tk.Frame(sf.inner)
    top_frame.pack(fill="x", pady=(4,8))

    tk.Label(top_frame, text="Select patient:", font=("Arial", 12)).pack(side="left")

    patients = list(db["patients"].keys())
    if not patients:
        tk.Label(top_frame, text=" (No patients found)", fg="red").pack(side="left", padx=6)

    sel = tk.StringVar(win)
    if patients:
        sel.set(patients[0])
    else:
        sel.set("")

    # dropdown (recreate when patients list changes)
    dd = tk.OptionMenu(top_frame, sel, *patients) if patients else tk.Label(top_frame, text="--")
    if isinstance(dd, tk.OptionMenu):
        dd.pack(side="left", padx=8)
    else:
        dd.pack(side="left", padx=8)

    # --- Assign reps (built-ins) ---
    assign_frame = tk.LabelFrame(sf.inner, text="Assign Reps (built-ins)", padx=8, pady=8)
    assign_frame.pack(pady=4, fill="x")

    exercises = ["squat", "pushup", "curl", "raise"]
    rep_entries = {}
    for ex in exercises:
        f = tk.Frame(assign_frame)
        f.pack(anchor="w", pady=3, fill="x")
        tk.Label(f, text=ex.capitalize()+": ", width=12, anchor="w").pack(side="left")
        e = tk.Entry(f, width=8)
        e.insert(0, "0")
        e.pack(side="left")
        rep_entries[ex] = e

    def assign_reps():
        db2 = load_db()
        patient = sel.get()
        if not patient:
            messagebox.showwarning("No patient", "No patient selected.")
            return
        _ensure_patient_structure(db2, patient)
        for ex in exercises:
            val = rep_entries[ex].get().strip()
            if val.isdigit():
                db2["patients"][patient]["assigned"][ex] = int(val)
            else:
                messagebox.showwarning("Invalid", f"Invalid number for {ex}")
                return
        save_db(db2)
        messagebox.showinfo("Saved", "Assignments updated.")

    tk.Button(assign_frame, text="Assign Reps", command=assign_reps, width=20).pack(pady=6)

    # --- Optimal ranges for built-ins ---
    ranges_frame = tk.LabelFrame(sf.inner, text="Patient Optimal Ranges (Default vs Custom)", padx=8, pady=8)
    ranges_frame.pack(pady=4, fill="x")

    radio_vars = {}
    range_entries = {}
    for ex in exercises:
        row = tk.Frame(ranges_frame)
        row.pack(anchor="w", pady=4, fill="x")
        tk.Label(row, text=ex.capitalize()+":", width=12).pack(side="left")
        rv = tk.IntVar(value=0)
        radio_vars[ex] = rv
        tk.Radiobutton(row, text="Default", variable=rv, value=0).pack(side="left")
        tk.Radiobutton(row, text="Custom", variable=rv, value=1).pack(side="left", padx=(6,10))
        tk.Label(row, text="Min").pack(side="left")
        e_min = tk.Entry(row, width=6)
        e_min.pack(side="left", padx=(2,6))
        tk.Label(row, text="Max").pack(side="left")
        e_max = tk.Entry(row, width=6)
        e_max.pack(side="left", padx=(2,6))
        range_entries[ex] = (e_min, e_max)

    def load_patient_custom():
        db2 = load_db()
        patient = sel.get()
        if not patient:
            return
        _ensure_patient_structure(db2, patient)
        assigned = db2["patients"][patient].get("assigned", {})
        for ex in exercises:
            rep_entries[ex].delete(0, tk.END)
            rep_entries[ex].insert(0, str(assigned.get(ex, 0)))
        custom = db2["patients"][patient].get("custom_optimal", {})
        for ex in exercises:
            e_min, e_max = range_entries[ex]
            c = custom.get(ex)
            if c and isinstance(c, list) and len(c) == 2:
                radio_vars[ex].set(1)
                e_min.delete(0, tk.END); e_min.insert(0, str(c[0]))
                e_max.delete(0, tk.END); e_max.insert(0, str(c[1]))
            else:
                radio_vars[ex].set(0)
                e_min.delete(0, tk.END)
                e_max.delete(0, tk.END)

    def save_ranges_for_patient():
        db2 = load_db()
        patient = sel.get()
        if not patient:
            messagebox.showwarning("No patient", "No patient selected.")
            return
        _ensure_patient_structure(db2, patient)
        custom = db2["patients"][patient].setdefault("custom_optimal", {})
        for ex in exercises:
            mode = radio_vars[ex].get()
            e_min, e_max = range_entries[ex]
            minv = e_min.get().strip()
            maxv = e_max.get().strip()
            if mode == 0:
                d_min, d_max = OPTIMAL_RANGES.get(ex, (0,0))
                if d_min is None or d_max is None:
                    custom[ex] = None
                else:
                    custom[ex] = [int(d_min), int(d_max)]
            else:
                if minv == "" or maxv == "":
                    messagebox.showwarning("Invalid", f"For {ex}, enter both min and max or choose Default.")
                    return
                if not (minv.lstrip('-').isdigit() and maxv.lstrip('-').isdigit()):
                    messagebox.showwarning("Invalid", f"Invalid number for {ex}. Enter integers.")
                    return
                min_i = int(minv); max_i = int(maxv)
                if min_i >= max_i:
                    messagebox.showwarning("Invalid", f"For {ex}, min must be less than max.")
                    return
                custom[ex] = [min_i, max_i]
        save_db(db2)
        messagebox.showinfo("Saved", "Patient optimal ranges updated (defaults saved if chosen).")

    tk.Button(ranges_frame, text="Save Optimal Ranges for Patient", command=save_ranges_for_patient, width=36).pack(pady=8)

    # --- Custom exercise creation ---
    custom_frame = tk.LabelFrame(sf.inner, text="Custom Exercises (Create / Manage)", padx=8, pady=8)
    custom_frame.pack(pady=4, fill="x")

    tk.Label(custom_frame, text="Create a custom exercise (records min/max angles of joints using camera)").pack(anchor="w", pady=(0,6))

    def on_add_custom():
        name = simpledialog.askstring("Custom Exercise Name", "Enter a name for this custom exercise (no slashes):", parent=win)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        messagebox.showinfo("Recording", "Recording will start AFTER a 3-second countdown displayed on the camera window.\nPress ESC to finish when done.")
        joint_limits = record_custom_exercise(name, countdown_seconds=3)
        if not joint_limits:
            messagebox.showerror("Failed", "No joint data collected. Make sure the person is visible and try again.")
            return

        # determine primary joint
        primary = pick_primary_joint_from_limits(joint_limits)
        # ask therapist for a default number of sets for this custom exercise
        default_sets = simpledialog.askinteger("Default Sets", f"Enter default number of sets for custom exercise '{name}' (0 for none):", parent=win, minvalue=0)
        if default_sets is None:
            default_sets = 0

        # Ask if therapist wants to set an optimal range for the primary joint
        optimal_obj = None
        if primary:
            want_opt = messagebox.askyesno("Set Optimal Range?", f"Primary joint detected: {primary}. Do you want to set a custom optimal min/max for this joint?")
            if want_opt:
                while True:
                    minv = simpledialog.askstring("Optimal Min", f"Enter optimal MIN angle (degrees) for {primary}:", parent=win)
                    maxv = simpledialog.askstring("Optimal Max", f"Enter optimal MAX angle (degrees) for {primary}:", parent=win)
                    try:
                        if minv is None or maxv is None:
                            optimal_obj = None
                            break
                        minf = float(minv); maxf = float(maxv)
                        if minf >= maxf:
                            messagebox.showwarning("Invalid range", "Min must be less than Max. Try again.")
                            continue
                        optimal_obj = {"joint": primary, "min": float(minf), "max": float(maxf)}
                        break
                    except Exception:
                        messagebox.showwarning("Invalid", "Enter numeric values for min and max.")
        else:
            messagebox.showinfo("No primary joint", "Could not detect a clear primary joint. You may edit this exercise later.")

        # Save joints to exercises.json (save_custom_exercise already saved joints in tracker; we'll now attach metadata)
        data = load_exercises_file()
        data.setdefault("custom_exercises", {})
        data["custom_exercises"][name] = data["custom_exercises"].get(name, {})
        data["custom_exercises"][name]["joints"] = joint_limits
        data["custom_exercises"][name]["created"] = datetime.utcnow().isoformat()
        data["custom_exercises"][name]["default_sets"] = int(default_sets)
        if optimal_obj:
            data["custom_exercises"][name]["optimal_range"] = optimal_obj
        save_exercises_file(data)

        message = f"Custom exercise '{name}' saved.\nPrimary joint: {primary}\nDefault sets: {default_sets}"
        if optimal_obj:
            message += f"\nOptimal range for {optimal_obj['joint']}: {optimal_obj['min']}° - {optimal_obj['max']}°"
        messagebox.showinfo("Saved", message)

        # refresh custom exercises UI
        load_custom_for_sets()
        refresh_custom_exercises_list()

    tk.Button(custom_frame, text="Add Custom Exercise (Record + set defaults)", command=on_add_custom, width=36).pack(pady=6)

    # --- Assign sets per patient (existing UI) ---
    sets_frame = tk.LabelFrame(sf.inner, text="Assign Sets (Custom Exercises per Patient)", padx=8, pady=4)
    sets_frame.pack(pady=4, fill="x")

    sets_entries = {}  # name -> Entry widget

    def load_custom_for_sets():
        # clear frame contents but keep the save button at the bottom
        for widget in sets_frame.winfo_children():
            widget.destroy()

        tk.Label(sets_frame, text="Set how many sets the patient should perform for each custom exercise:").pack(anchor="w")
        custom_exs = load_custom_exercises()
        if not custom_exs:
            tk.Label(sets_frame, text="(No custom exercises available)").pack(anchor="w")
            return
        patient = sel.get()
        db2 = load_db()
        if patient:
            _ensure_patient_structure(db2, patient)
            assigned_sets = db2["patients"][patient].get("assigned_sets", {})
        else:
            assigned_sets = {}
        # recreate entries mapping
        sets_entries.clear()
        for name, meta in custom_exs.items():
            row = tk.Frame(sets_frame)
            row.pack(anchor="w", pady=3, fill="x")
            tk.Label(row, text=name, width=28, anchor="w").pack(side="left")
            e = tk.Entry(row, width=8)
            pre = assigned_sets.get(name, meta.get("default_sets", 0))
            e.insert(0, str(pre))
            e.pack(side="left")
            sets_entries[name] = e

        tk.Button(sets_frame, text="Save Assigned Sets", command=save_assigned_sets, width=28).pack(pady=6)

    def save_assigned_sets():
        db2 = load_db()
        patient = sel.get()
        if not patient:
            messagebox.showwarning("No patient", "No patient selected.")
            return
        _ensure_patient_structure(db2, patient)
        for name, ent in sets_entries.items():
            val = ent.get().strip()
            if val == "":
                # skip empty
                continue
            if not val.isdigit():
                messagebox.showwarning("Invalid", f"Invalid sets value for {name}. Enter a non-negative integer.")
                return
            db2["patients"][patient].setdefault("assigned_sets", {})[name] = int(val)
        save_db(db2)
        messagebox.showinfo("Saved", "Assigned sets updated for patient.")
        # update progress area if visible
        refresh_progress_display()

    load_custom_for_sets()

    # --- Messaging UI (embedded in main window) ---
    msg_frame = tk.LabelFrame(sf.inner, text="Messages (Patient ↔ Therapist)", padx=8, pady=4)
    msg_frame.pack(padx=4, pady=6, fill="both", expand=False)

    chat_display = scrolledtext.ScrolledText(msg_frame, wrap=tk.WORD, width=100, height=12, state='disabled')
    chat_display.pack(padx=6, pady=6, fill="both", expand=True)

    send_frame = tk.Frame(msg_frame)
    send_frame.pack(fill="x", padx=6, pady=(0,6))
    tk.Label(send_frame, text="Write recommendation to patient:").pack(anchor="w")
    therapist_msg_ent = tk.Entry(send_frame, width=100)
    therapist_msg_ent.pack(side="left", padx=(0,6), expand=True, fill="x")

    def load_messages_into_display():
        chat_display.configure(state='normal')
        chat_display.delete('1.0', tk.END)
        db = load_db()
        patient = sel.get()
        if not patient:
            chat_display.insert(tk.END, "(No patient selected)\n")
            chat_display.configure(state='disabled')
            return
        _ensure_patient_structure(db, patient)
        msgs_t = db["patients"][patient]["messages"].get("from_therapist", [])
        msgs_p = db["patients"][patient]["messages"].get("from_patient", [])
        combined = []
        for m in msgs_t:
            combined.append(("Therapist", m.get("timestamp", ""), m.get("text", "")))
        for m in msgs_p:
            combined.append(("Patient", m.get("timestamp", ""), m.get("text", "")))
        combined.sort(key=lambda x: x[1])
        for who, ts, text in combined:
            chat_display.insert(tk.END, f"{who} [{ts}]: {text}\n")
        chat_display.see(tk.END)
        chat_display.configure(state='disabled')

    def send_therapist_message():
        text = therapist_msg_ent.get().strip()
        if not text:
            return
        db = load_db()
        patient = sel.get()
        if not patient:
            messagebox.showwarning("No patient", "No patient selected.")
            return
        _ensure_patient_structure(db, patient)
        entry = {"timestamp": datetime.utcnow().isoformat(), "text": text}
        db["patients"][patient]["messages"]["from_therapist"].append(entry)
        save_db(db)
        therapist_msg_ent.delete(0, tk.END)
        load_messages_into_display()
        messagebox.showinfo("Sent", f"Message sent to {patient}.")

    tk.Button(send_frame, text="Send", command=send_therapist_message).pack(side="right", padx=(6,0))

    # --- Progress view embedded (shows assigned sets, default sets and optimal ranges if present) ---
    progress_frame = tk.LabelFrame(sf.inner, text="Patient Progress Snapshot", padx=8, pady=8)
    progress_frame.pack(padx=4, pady=6, fill="both", expand=False)

    progress_text = scrolledtext.ScrolledText(progress_frame, wrap=tk.WORD, width=100, height=10, state='disabled')
    progress_text.pack(fill="both", expand=True, padx=6, pady=(0,6))

    def refresh_progress_display():
        db3 = load_db()
        patient = sel.get()
        progress_text.configure(state='normal')
        progress_text.delete('1.0', tk.END)
        if not patient:
            progress_text.insert(tk.END, "(No patient selected)\n")
            progress_text.configure(state='disabled')
            return
        _ensure_patient_structure(db3, patient)
        comp = db3["patients"][patient].get("completed", {})
        assigned = db3["patients"][patient].get("assigned", {})
        assigned_sets = db3["patients"][patient].get("assigned_sets", {})
        sets_completed = db3["patients"][patient].get("sets_completed", {})
        text = ""
        for ex in exercises:
            a = assigned.get(ex, 0)
            c = comp.get(ex, 0)
            text += f"{ex.capitalize()}: Assigned reps={a}  Completed reps={c}\n"
            hist = db3["patients"][patient].get("angle_stats", {}).get(ex, [])
            if hist:
                last = hist[-1]
                text += f"  Last session ({last.get('timestamp','')}): reps={last.get('reps',0)}, deviation={last.get('deviation_percent',0.0)}%\n"
            else:
                opt_min, opt_max = OPTIMAL_RANGES.get(ex, (0,0))
                text += f"  Optimal range: {opt_min}° - {opt_max}°\n"

        custom_exs = load_custom_exercises()
        if custom_exs:
            text += "\nCustom Exercises:\n"
            for name, meta in custom_exs.items():
                a_sets = assigned_sets.get(name, meta.get("default_sets", 0))
                s_comp = sets_completed.get(name, 0)
                text += f"{name}: Assigned sets (patient-level) = {db3['patients'][patient].get('assigned_sets', {}).get(name, 'none')} | Default sets (exercise) = {meta.get('default_sets', 0)} | Sets completed = {s_comp}\n"
                hist = db3['patients'][patient].get("angle_stats", {}).get(name, [])
                if hist:
                    last = hist[-1]
                    text += f"  Last set ({last.get('timestamp','')}): reps={last.get('reps',0)}, deviation={last.get('deviation_percent',0.0)}%, opt_range={meta.get('optimal_range')}\n"
                else:
                    text += f"  No recorded sets yet for {name}. Exercise optimal_range: {meta.get('optimal_range')}\n"

        progress_text.insert(tk.END, text)
        progress_text.configure(state='disabled')

    tk.Button(progress_frame, text="Refresh Progress Snapshot", command=refresh_progress_display).pack(pady=(0,6))

    # Helper UI to list custom exercise names (for convenience)
    custom_list_frame = tk.LabelFrame(sf.inner, text="Available Custom Exercises", padx=8, pady=8)
    custom_list_frame.pack(padx=4, pady=4, fill="x")
    custom_listbox = tk.Listbox(custom_list_frame, height=4)
    custom_listbox.pack(fill="x", padx=4, pady=4)

    def refresh_custom_exercises_list():
        custom_listbox.delete(0, tk.END)
        exs = load_custom_exercises()
        for name, meta in exs.items():
            ds = meta.get("default_sets", 0)
            opt = meta.get("optimal_range")
            line = f"{name} (default sets: {ds})"
            if opt:
                line += f" opt({opt.get('joint')} {opt.get('min')}-{opt.get('max')})"
            custom_listbox.insert(tk.END, line)

    refresh_custom_exercises_list()

    # Called when patient selection changes
    def on_patient_change(*args):
        # reload assigned reps, custom ranges, sets, messages, progress snapshot
        load_patient_custom()
        load_custom_for_sets()
        load_messages_into_display()
        refresh_progress_display()

    sel.trace_add("write", on_patient_change)

    # Refresh OptionMenu when patients list changes on disk (simple approach: re-create menu)
    def refresh_patient_dropdown():
        nonlocal dd
        for widget in top_frame.winfo_children():
            widget.destroy()
        tk.Label(top_frame, text="Select patient:", font=("Arial", 12)).pack(side="left")
        db2 = load_db()
        patients_new = list(db2["patients"].keys())
        if not patients_new:
            tk.Label(top_frame, text=" (No patients found)", fg="red").pack(side="left", padx=6)
            sel.set("")
        # recreate OptionMenu
        if patients_new:
            sel.set(patients_new[0] if sel.get() == "" else sel.get())
            dd = tk.OptionMenu(top_frame, sel, *patients_new)
            dd.pack(side="left", padx=8)
        else:
            sel.set("")
            dd = tk.Label(top_frame, text="--")
            dd.pack(side="left", padx=8)
        # Re-add a refresh button
        tk.Button(top_frame, text="Refresh Patients", command=refresh_patient_dropdown).pack(side="right", padx=6)

    # Place a small refresh patients button initially
    tk.Button(top_frame, text="Refresh Patients", command=refresh_patient_dropdown).pack(side="right", padx=6)

    # --- Periodic refresh to pick up external changes and keep chat updated ---
    def periodic_refresh():
        try:
            # keep UI elements in sync
            load_messages_into_display()
            load_custom_for_sets()
            refresh_custom_exercises_list()
            refresh_progress_display()
            # Also update rep entries for patient in case assignments changed externally
            load_patient_custom()
        except Exception:
            pass
        win.after(3000, periodic_refresh)

    periodic_refresh()

    # Logout button and close behavior
    def logout():
        win.destroy()
        try:
            import login
            login.main()
        except Exception:
            pass

    tk.Button(win, text="Logout", fg="white", bg="red", command=logout).pack(side="bottom", pady=4)

    # Initial population
    on_patient_change()
    load_messages_into_display()
    win.mainloop()

# If run directly, open a simple login wrapper for quick testing
if __name__ == "__main__":
    # create example DB with a sample patient for testing if none exists
    db0 = load_db()
    if not db0.get("patients"):
        db0["patients"] = {"alice": {}}
        save_db(db0)
    # call therapist_window with a dummy login_window = None
    therapist_window("therapist_demo", None)
