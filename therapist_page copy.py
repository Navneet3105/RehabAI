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

def therapist_window(username, login_window):
    try:
        login_window.destroy()
    except:
        pass

    db = load_db()
    win = tk.Tk()
    win.title(f"Therapist - {username}")
    win.geometry("980x920")

    tk.Label(win, text=f"Therapist: {username}", font=("Arial", 16)).pack(pady=8)
    tk.Label(win, text="Select patient:", font=("Arial", 12)).pack()

    patients = list(db["patients"].keys())
    if not patients:
        tk.Label(win, text="No patients found.").pack()
        return

    sel = tk.StringVar(win)
    sel.set(patients[0])

    dd_frame = tk.Frame(win)
    dd_frame.pack()
    tk.OptionMenu(dd_frame, sel, *patients).pack(pady=6)

    # Assign reps for built-ins
    assign_frame = tk.LabelFrame(win, text="Assign Reps (built-ins)", padx=8, pady=8)
    assign_frame.pack(pady=8, fill="x", padx=10)

    exercises = ["squat", "pushup", "curl", "raise"]
    rep_entries = {}
    for ex in exercises:
        f = tk.Frame(assign_frame)
        f.pack(anchor="w", pady=4)
        tk.Label(f, text=ex.capitalize()+": ", width=12).pack(side="left")
        e = tk.Entry(f, width=8)
        e.insert(0, "0")
        e.pack(side="left")
        rep_entries[ex] = e

    def assign_reps():
        db2 = load_db()
        patient = sel.get()
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

    # Optimal ranges for built-ins
    ranges_frame = tk.LabelFrame(win, text="Patient Optimal Ranges (Default vs Custom)", padx=8, pady=8)
    ranges_frame.pack(pady=8, fill="x", padx=10)

    radio_vars = {}
    range_entries = {}
    for ex in exercises:
        row = tk.Frame(ranges_frame)
        row.pack(anchor="w", pady=6, fill="x")
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

    load_patient_custom()

    def on_patient_change(*args):
        load_patient_custom()

    sel.trace_add("write", on_patient_change)

    def save_ranges_for_patient():
        db2 = load_db()
        patient = sel.get()
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

    tk.Button(ranges_frame, text="Save Optimal Ranges for Patient", command=save_ranges_for_patient, width=36).pack(pady=10)

    # Custom exercise creation
    custom_frame = tk.LabelFrame(win, text="Custom Exercises (Create / Manage)", padx=8, pady=8)
    custom_frame.pack(pady=8, fill="x", padx=10)

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

    tk.Button(custom_frame, text="Add Custom Exercise (Record + set defaults)", command=on_add_custom, width=36).pack(pady=6)

    # Assign sets per patient (existing UI)
    sets_frame = tk.LabelFrame(win, text="Assign Sets (Custom Exercises per Patient)", padx=8, pady=4)
    sets_frame.pack(pady=8, fill="x", padx=10)

    sets_entries = {}

    def load_custom_for_sets():
        for widget in sets_frame.winfo_children():
            widget.destroy()
        tk.Label(sets_frame, text="Set how many sets the patient should perform for each custom exercise:").pack(anchor="w")
        custom_exs = load_custom_exercises()
        if not custom_exs:
            tk.Label(sets_frame, text="(No custom exercises available)").pack(anchor="w")
            return
        patient = sel.get()
        db2 = load_db()
        _ensure_patient_structure(db2, patient)
        assigned_sets = db2["patients"][patient].get("assigned_sets", {})
        for name, meta in custom_exs.items():
            row = tk.Frame(sets_frame)
            row.pack(anchor="w", pady=4, fill="x")
            tk.Label(row, text=name, width=28).pack(side="left")
            e = tk.Entry(row, width=8)
            # prefill with assigned_sets if present, otherwise prefill with exercise default_sets
            pre = assigned_sets.get(name, meta.get("default_sets", 0))
            e.insert(0, str(pre))
            e.pack(side="left")
            sets_entries[name] = e

    load_custom_for_sets()

    def save_assigned_sets():
        db2 = load_db()
        patient = sel.get()
        _ensure_patient_structure(db2, patient)
        for name, ent in sets_entries.items():
            val = ent.get().strip()
            if val == "":
                continue
            if not val.isdigit():
                messagebox.showwarning("Invalid", f"Invalid sets value for {name}. Enter a non-negative integer.")
                return
            db2["patients"][patient].setdefault("assigned_sets", {})[name] = int(val)
        save_db(db2)
        messagebox.showinfo("Saved", "Assigned sets updated for patient.")

    tk.Button(sets_frame, text="Save Assigned Sets", command=save_assigned_sets, width=28).pack(pady=6)

    # Messaging UI (unchanged)
    msg_frame = tk.LabelFrame(win, text="Messages (Patient ↔ Therapist)", padx=8, pady=4)
    msg_frame.pack(padx=10, pady=10, fill="both", expand=False)

    chat_display = scrolledtext.ScrolledText(msg_frame, wrap=tk.WORD, width=100, height=12, state='disabled')
    chat_display.pack(padx=6, pady=6)

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

    load_messages_into_display()

    def send_therapist_message():
        text = therapist_msg_ent.get().strip()
        if not text:
            return
        db = load_db()
        patient = sel.get()
        _ensure_patient_structure(db, patient)
        entry = {"timestamp": datetime.utcnow().isoformat(), "text": text}
        db["patients"][patient]["messages"]["from_therapist"].append(entry)
        save_db(db)
        therapist_msg_ent.delete(0, tk.END)
        load_messages_into_display()
        messagebox.showinfo("Sent", f"Message sent to {patient}.")

    tk.Button(send_frame, text="Send", command=send_therapist_message).pack(side="right", padx=(6,0))

    def popup_view_messages():
        db = load_db()
        patient = sel.get()
        _ensure_patient_structure(db, patient)
        msgs_t = db["patients"][patient]["messages"].get("from_therapist", [])
        msgs_p = db["patients"][patient]["messages"].get("from_patient", [])
        top = tk.Toplevel(win)
        top.title(f"All Messages - {patient} (popup)")
        top.geometry("800x480")
        st = scrolledtext.ScrolledText(top, wrap=tk.WORD, width=100, height=25, state='normal')
        combined = []
        for m in msgs_t:
            combined.append(("Therapist", m.get("timestamp",""), m.get("text","")))
        for m in msgs_p:
            combined.append(("Patient", m.get("timestamp",""), m.get("text","")))
        combined.sort(key=lambda x: x[1])
        for who, ts, t in combined:
            st.insert(tk.END, f"{who} [{ts}]: {t}\n")
        st.configure(state='disabled')
        st.pack(fill="both", expand=True, padx=8, pady=8)

        reply_frame = tk.Frame(top)
        reply_frame.pack(fill="x", padx=8, pady=(0,8))
        tk.Label(reply_frame, text="Reply:").pack(anchor="w")
        reply_ent = tk.Entry(reply_frame, width=80)
        reply_ent.pack(side="left", expand=True, fill="x", padx=(0,6))

        def reply_send():
            txt = reply_ent.get().strip()
            if not txt:
                return
            db2 = load_db()
            _ensure_patient_structure(db2, patient)
            db2["patients"][patient]["messages"]["from_therapist"].append({
                "timestamp": datetime.utcnow().isoformat(),
                "text": txt
            })
            save_db(db2)
            messagebox.showinfo("Sent", "Reply sent.")
            st.configure(state='normal')
            st.insert(tk.END, f"Therapist [{datetime.utcnow().isoformat()}]: {txt}\n")
            st.configure(state='disabled')
            load_messages_into_display()
            reply_ent.delete(0, tk.END)

        tk.Button(reply_frame, text="Send Reply", command=reply_send).pack(side="right")
        tk.Button(top, text="Close", command=top.destroy).pack(pady=4)

    tk.Button(msg_frame, text="View Messages (Popup)", command=popup_view_messages).pack(pady=(0,8))

    # View progress (shows assigned sets, default sets and optimal ranges if present)
    def view_progress():
        db3 = load_db()
        patient = sel.get()
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
                hist = db3["patients"][patient].get("angle_stats", {}).get(name, [])
                if hist:
                    last = hist[-1]
                    text += f"  Last set ({last.get('timestamp','')}): reps={last.get('reps',0)}, deviation={last.get('deviation_percent',0.0)}%, opt_range={meta.get('optimal_range')}\n"
                else:
                    text += f"  No recorded sets yet for {name}. Exercise optimal_range: {meta.get('optimal_range')}\n"

        messagebox.showinfo(f"Progress - {patient}", text)

    tk.Button(win, text="View Patient Progress", command=view_progress, width=30).pack(pady=5)

    def logout():
        win.destroy()
        import login
        login.main()

    def periodic_refresh():
        try:
            load_messages_into_display()
            load_custom_for_sets()
        except Exception:
            pass
        win.after(3000, periodic_refresh)

    periodic_refresh()

    tk.Button(win, text="Logout", fg="white", bg="red", command=logout).pack(side="bottom", pady=5)
    on_patient_change()
    load_messages_into_display()
    win.mainloop()
