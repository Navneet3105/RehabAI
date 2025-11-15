# patient_page.py
import tkinter as tk
from tkinter import messagebox, scrolledtext, simpledialog
import json
from exercise_tracker import start_exercise, OPTIMAL_RANGES, load_custom_exercises
from datetime import datetime
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

def patient_window(username, login_window):
    try:
        login_window.destroy()
    except:
        pass

    win = tk.Tk()
    win.title(f"Patient - {username}")
    win.geometry("760x820")

    tk.Label(win, text=f"Patient: {username}", font=("Arial", 16)).pack(pady=8)
    tk.Label(win, text="Your assigned exercises:", font=("Arial", 12)).pack()

    built_in = ["squat", "pushup", "curl", "raise"]

    box_outer = tk.Frame(win)
    box_outer.pack(pady=6, fill="x")

    box_canvas = tk.Canvas(box_outer, height=120)
    box_canvas.pack(side="left", fill="both", expand=True)

    vsb = tk.Scrollbar(box_outer, orient="vertical", command=box_canvas.yview)
    vsb.pack(side="right", fill="y")
    box_canvas.configure(yscrollcommand=vsb.set)

    box_frame = tk.Frame(box_canvas)
    box_canvas.create_window((0,0), window=box_frame, anchor='nw')

    def on_mousewheel(event):
        box_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    box_canvas.bind_all("<MouseWheel>", on_mousewheel)

    def refresh_assigned():
        db = load_db()
        _ensure_patient_structure(db, username)
        assigned = db["patients"][username].get("assigned", {})
        custom_opt = db["patients"][username].get("custom_optimal", {})
        assigned_sets = db["patients"][username].get("assigned_sets", {})
        sets_completed = db["patients"][username].get("sets_completed", {})
        # load custom exercises file to show exercise-level defaults & optimal ranges
        ex_file = load_exercises_file()
        custom_exs = ex_file.get("custom_exercises", {})
        for w in list(box_frame.winfo_children()):
            w.destroy()

        for ex in built_in:
            assigned_count = assigned.get(ex, 0)
            c = custom_opt.get(ex)
            if c and isinstance(c, list) and len(c) == 2:
                opt_min, opt_max = c
            else:
                opt_min, opt_max = OPTIMAL_RANGES.get(ex, (0,0))
            tk.Label(box_frame, text=f"{ex.capitalize()}: Assigned {assigned_count} reps   Optimal angle range: {opt_min}° - {opt_max}°").pack(anchor="w")

        if custom_exs:
            tk.Label(box_frame, text="").pack()
            tk.Label(box_frame, text="Custom Exercises available:").pack(anchor="w")
            for name, meta in custom_exs.items():
                joints = meta.get("joints", {})
                s = ", ".join([f"{j}:{lim[0]}-{lim[1]}" for j,lim in joints.items()])
                exercise_default_sets = meta.get("default_sets", 0)
                # patient-level override if therapist separately assigned sets is preferred
                assigned_for_patient = assigned_sets.get(name, None)
                display_sets = assigned_for_patient if assigned_for_patient is not None else exercise_default_sets
                sets_done = sets_completed.get(name, 0)
                optimal = meta.get("optimal_range")
                opt_txt = f"{optimal['joint']}:{optimal['min']}-{optimal['max']}" if optimal else "none"
                tk.Label(box_frame, text=f"{name} | Default sets: {exercise_default_sets} | Assigned (patient): {assigned_for_patient} | Doing: {display_sets} sets | Done: {sets_done} | Optimal: {opt_txt} | Joints: {s}").pack(anchor="w")

        box_frame.update_idletasks()
        box_canvas.configure(scrollregion=box_canvas.bbox("all"))

    refresh_assigned()

    def launch(ex):
        db = load_db()
        _ensure_patient_structure(db, username)
        if ex in built_in:
            assigned = db["patients"][username].get("assigned", {})
            target = assigned.get(ex, 0)
            if target == 0:
                messagebox.showwarning("Not assigned", f"{ex.capitalize()} is not assigned by your therapist.")
                return
            reps_input = target
        else:
           # patient picks reps per set
            '''target_str = simpledialog.askstring("Target Reps (per set)", f"Enter target reps for this set of '{ex}':", parent=win)
            if not target_str or not target_str.isdigit():
                messagebox.showwarning("Invalid", "Enter a valid positive integer for target reps.")
                return'''
            #reps_input = int(target_str)
            reps_input = 10  # default for custom exercises

        db2 = load_db()
        _ensure_patient_structure(db2, username)
        # determine opt_range precedence:
        # 1) per-patient custom_optimal for exercise name if exists
        # 2) exercise's stored optimal_range (exercise-level) if exists
        # 3) built-in fallback
        per_patient_custom = db2["patients"][username].get("custom_optimal", {}).get(ex)
        ex_file = load_exercises_file()
        ex_meta = ex_file.get("custom_exercises", {}).get(ex, {})
        ex_opt = ex_meta.get("optimal_range")
        opt_range = None
        if per_patient_custom and isinstance(per_patient_custom, list) and len(per_patient_custom) == 2:
            opt_range = tuple(per_patient_custom)
        elif ex_opt and isinstance(ex_opt, dict) and "min" in ex_opt and "max" in ex_opt:
            opt_range = (float(ex_opt["min"]), float(ex_opt["max"]))
        else:
            if ex in OPTIMAL_RANGES:
                opt_range = OPTIMAL_RANGES.get(ex, (0,0))
            else:
                opt_range = (None, None)

        stats = start_exercise(ex, target_reps=reps_input, opt_range=opt_range)

        db3 = load_db()
        _ensure_patient_structure(db3, username)

        comp = db3["patients"][username].setdefault("completed", {})
        comp[ex] = comp.get(ex, 0) + int(stats.get('reps', 0))

        if ex not in built_in:
            db3["patients"][username].setdefault("sets_completed", {})
            db3["patients"][username]["sets_completed"][ex] = db3["patients"][username]["sets_completed"].get(ex, 0) + 1

        ag = db3["patients"][username].setdefault("angle_stats", {})
        ex_hist = ag.setdefault(ex, [])

        # snapshot current assigned/sets info
        patient_assigned_reps = None
        patient_assigned_sets = db3["patients"][username].get("assigned_sets", {}).get(ex, None)
        exercise_default_sets = ex_meta.get("default_sets", None)
        sets_done = db3["patients"][username].get("sets_completed", {}).get(ex, 0)

        ex_hist.append({
            "timestamp": stats.get('timestamp'),
            "reps": int(stats.get('reps', 0)),
            "rep_averages": stats.get('rep_averages', []),
            "overall_avg": stats.get('overall_avg', 0.0),
            "angle_min": stats.get('angle_min', 0.0),
            "angle_max": stats.get('angle_max', 0.0),
            "range_avg_low": stats.get('range_avg_low', 0.0),
            "range_avg_high": stats.get('range_avg_high', 0.0),
            "rep_min": stats.get('rep_min', 0.0),
            "rep_max": stats.get('rep_max', 0.0),
            "rep_range": stats.get('rep_range', 0.0),
            "opt_range": stats.get('opt_range', (0,0)),
            "deviation_percent": stats.get('deviation_percent', 0.0),
            "assigned_reps_snapshot": patient_assigned_reps,
            "assigned_sets_snapshot": patient_assigned_sets,
            "exercise_default_sets_snapshot": exercise_default_sets,
            "sets_completed_snapshot": sets_done
        })

        save_db(db3)

        deviation = stats.get('deviation_percent', 0.0)
        guidance = "No optimal range set."
        opt_min, opt_max = stats.get('opt_range', (None, None))
        if opt_min is not None and opt_max is not None and opt_min < opt_max:
            rep_min = stats.get('rep_min', 0.0)
            rep_max = stats.get('rep_max', 0.0)
            if rep_max < opt_min:
                guidance = "Try raising higher next time."
            elif rep_min > opt_max:
                guidance = "Try lowering your range next time."
            else:
                if deviation < 15:
                    guidance = "Good and consistent motion!"
                elif deviation < 50:
                    guidance = "Some inconsistency — try to control range more."
                else:
                    guidance = "High inconsistency — slow down and control your reps."

        assigned_sets_for_ex = db3["patients"][username].get("assigned_sets", {}).get(ex, None)
        exercise_default = ex_meta.get("default_sets", None)
        sets_done = db3["patients"][username].get("sets_completed", {}).get(ex, 0)
        sets_message = ""
        if assigned_sets_for_ex is not None:
            remaining = max(0, assigned_sets_for_ex - sets_done)
            sets_message = f"\nSets completed: {sets_done}/{assigned_sets_for_ex}. Sets remaining: {remaining}."
        elif exercise_default is not None:
            remaining = max(0, exercise_default - sets_done)
            sets_message = f"\nSets completed: {sets_done}/{exercise_default} (exercise default). Sets remaining: {remaining}."

        messagebox.showinfo("Saved", f"You completed {stats.get('reps',0)} reps for {ex.capitalize()}.\n"
                                     f"Working range (avg low - avg high): {stats.get('range_avg_low',0.0)}° - {stats.get('range_avg_high',0.0)}°\n"
                                     f"Rep-range: {stats.get('rep_min',0.0)}° - {stats.get('rep_max',0.0)}° (spread {stats.get('rep_range',0.0)}°)\n"
                                     f"Overall avg: {stats.get('overall_avg',0.0)}°\n"
                                     f"Deviation (rep consistency): {stats.get('deviation_percent',0.0)}%\n\n"
                                     f"{guidance}{sets_message}")
        refresh_assigned()
        load_messages_into_display()

    btn_frame = tk.Frame(win)
    btn_frame.pack(pady=6)

    for ex in built_in:
        tk.Button(btn_frame, text=ex.capitalize(), width=30, command=lambda e=ex: launch(e)).pack(pady=6)

    def add_custom_buttons():
        custom_panel = tk.LabelFrame(win, text="Custom Exercises", padx=8, pady=8)
        custom_panel.pack(pady=8, fill="x", padx=10)
        ex_file = load_exercises_file()
        custom_exs = ex_file.get("custom_exercises", {})
        if not custom_exs:
            tk.Label(custom_panel, text="No custom exercises available.").pack(anchor="w")
            return
        for name, meta in custom_exs.items():
            tk.Button(custom_panel, text=name, width=36, command=lambda n=name: launch(n)).pack(pady=4)

    add_custom_buttons()

    # Messaging UI
    msg_frame = tk.LabelFrame(win, text="Messages", padx=8, pady=8)
    msg_frame.pack(padx=10, pady=10, fill="both", expand=False)

    chat_display = scrolledtext.ScrolledText(msg_frame, wrap=tk.WORD, width=80, height=12, state='disabled')
    chat_display.pack(padx=6, pady=6)

    send_frame = tk.Frame(msg_frame)
    send_frame.pack(fill="x", padx=6, pady=(0,6))
    tk.Label(send_frame, text="Ask your therapist:").pack(anchor="w")
    patient_msg_ent = tk.Entry(send_frame, width=80)
    patient_msg_ent.pack(side="left", padx=(0,6), expand=True, fill="x")

    def load_messages_into_display():
        chat_display.configure(state='normal')
        chat_display.delete('1.0', tk.END)
        db = load_db()
        _ensure_patient_structure(db, username)
        msgs_t = db["patients"][username]["messages"].get("from_therapist", [])
        msgs_p = db["patients"][username]["messages"].get("from_patient", [])
        combined = []
        for m in msgs_t:
            combined.append(("Therapist", m.get("timestamp", ""), m.get("text", "")))
        for m in msgs_p:
            combined.append(("You", m.get("timestamp", ""), m.get("text", "")))
        combined.sort(key=lambda x: x[1])
        for who, ts, text in combined:
            chat_display.insert(tk.END, f"{who} [{ts}]: {text}\n")
        chat_display.see(tk.END)
        chat_display.configure(state='disabled')

    load_messages_into_display()

    def send_patient_message():
        text = patient_msg_ent.get().strip()
        if not text:
            return
        db = load_db()
        _ensure_patient_structure(db, username)
        entry = {"timestamp": datetime.utcnow().isoformat(), "text": text}
        db["patients"][username]["messages"]["from_patient"].append(entry)
        save_db(db)
        patient_msg_ent.delete(0, tk.END)
        load_messages_into_display()
        messagebox.showinfo("Sent", "Your message was sent to your therapist.")

    tk.Button(send_frame, text="Send", command=send_patient_message).pack(side="right", padx=(6,0))

    def popup_view_messages():
        db = load_db()
        _ensure_patient_structure(db, username)
        msgs_t = db["patients"][username]["messages"].get("from_therapist", [])
        msgs_p = db["patients"][username]["messages"].get("from_patient", [])
        top = tk.Toplevel(win)
        top.title("All Messages (popup)")
        top.geometry("640x420")
        st = scrolledtext.ScrolledText(top, wrap=tk.WORD, width=80, height=20, state='normal')
        combined = []
        for m in msgs_t:
            combined.append(("Therapist", m.get("timestamp",""), m.get("text","")))
        for m in msgs_p:
            combined.append(("You", m.get("timestamp",""), m.get("text","")))
        combined.sort(key=lambda x: x[1])
        for who, ts, t in combined:
            st.insert(tk.END, f"{who} [{ts}]: {t}\n")
        st.configure(state='disabled')
        st.pack(fill="both", expand=True, padx=8, pady=8)
        tk.Button(top, text="Close", command=top.destroy).pack(pady=6)

    tk.Button(msg_frame, text="View Messages (Popup)", command=popup_view_messages).pack(pady=(0,8))

    def view_my_progress():
        db = load_db()
        _ensure_patient_structure(db, username)
        comp = db["patients"][username].get("completed", {})
        assigned = db["patients"][username].get("assigned", {})
        assigned_sets = db["patients"][username].get("assigned_sets", {})
        sets_completed = db["patients"][username].get("sets_completed", {})
        text = ""
        for ex in built_in:
            text += f"{ex.capitalize()}: Completed reps={comp.get(ex,0)} Assigned reps={assigned.get(ex,0)}\n"
            hist = db["patients"][username].get("angle_stats", {}).get(ex, [])
            if hist:
                last = hist[-1]
                ts = last.get('timestamp', '')
                dev = last.get('deviation_percent', 0.0)
                text += f"  Last ({ts}): reps={last.get('reps',0)}, deviation={dev}%\n"
            else:
                text += "  No sessions recorded yet.\n"

        ex_file = load_exercises_file()
        custom_exs = ex_file.get("custom_exercises", {})
        if custom_exs:
            text += "\nCustom Exercises:\n"
            for name, meta in custom_exs.items():
                a_sets = assigned_sets.get(name, meta.get("default_sets", 0))
                s_done = sets_completed.get(name, 0)
                text += f"{name}: Sets completed={s_done} Assigned sets={db['patients'][username].get('assigned_sets', {}).get(name, 'none')} Default sets={meta.get('default_sets', 0)}\n"
                hist = db["patients"][username].get("angle_stats", {}).get(name, [])
                if hist:
                    last = hist[-1]
                    ts = last.get('timestamp', '')
                    dev = last.get('deviation_percent', 0.0)
                    reps = last.get('reps', 0)
                    text += f"  Last set ({ts}): reps={reps}, deviation={dev}%, assigned_sets_snapshot={last.get('assigned_sets_snapshot')}, sets_completed_snapshot={last.get('sets_completed_snapshot')}\n"
                else:
                    text += "  No sets recorded yet.\n"
        messagebox.showinfo("Your Progress", text)

    tk.Button(win, text="View My Progress", width=30, command=view_my_progress).pack(pady=8)

    def logout():
        win.destroy()
        import login
        login.main()

    def periodic_refresh():
        try:
            load_messages_into_display()
        except Exception:
            pass
        win.after(3000, periodic_refresh)

    periodic_refresh()

    tk.Button(win, text="Logout", fg="white", bg="red", command=logout).pack(side="bottom", pady=12)
    win.mainloop()
