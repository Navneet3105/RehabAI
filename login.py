# login.py
import tkinter as tk
from tkinter import messagebox
import json
from patient_page import patient_window
from therapist_page import therapist_window

DB = "database.json"

def load_db():
    with open(DB, "r") as f:
        return json.load(f)

def main():
    root = tk.Tk()
    root.title("RehabAI - Login")
    root.geometry("360x260")

    tk.Label(root, text="RehabAI Login", font=("Arial", 18)).pack(pady=10)
    tk.Label(root, text="Username").pack()
    user_ent = tk.Entry(root)
    user_ent.pack()
    tk.Label(root, text="Password").pack()
    pass_ent = tk.Entry(root, show="*")
    pass_ent.pack()

    def do_login():
        db = load_db()
        u = user_ent.get().strip()
        p = pass_ent.get().strip()
        if u in db.get("therapists", {}) and db["therapists"][u]["password"] == p:
            therapist_window(u, root)
            return
        if u in db.get("patients", {}) and db["patients"][u]["password"] == p:
            patient_window(u, root)
            return
        messagebox.showerror("Login failed", "Invalid username or password")

    tk.Button(root, text="Login", width=18, command=do_login).pack(pady=12)

    root.mainloop()

if __name__ == "__main__":
    main()
