import tkinter as tk
from tkinter import messagebox
import os
import ctypes
from modulos.vision_ui import ejecutar_vision

def iniciar_sistema():
    usuario = entry_usuario.get()
    password = entry_password.get()

    if not usuario or not password:
        messagebox.showwarning("Error", "Ingrese credenciales")
        return

    os.environ["CAM_USER"] = usuario
    os.environ["CAM_PASS"] = password
    
    ventana.destroy()
    ejecutar_vision()

def verificar_mayusculas(event=None):
    try:
        # 0x14 es Caps Lock en Windows
        if ctypes.WinDLL("User32.dll").GetKeyState(0x14) & 1:
            lbl_caps_warning.config(text="¡Bloq Mayús Activado!")
        else:
            lbl_caps_warning.config(text="")
    except: pass

def bloquear_accion(event):
    return "break"

ventana = tk.Tk()
ventana.title("ACCELERA - PTZ")
ventana.geometry("400x350")
ventana.configure(bg="#1E1E2E")
ventana.resizable(False, False)

tk.Label(ventana, text="ACCELERA - PTZ", font=("Helvetica", 18, "bold"), bg="#1E1E2E", fg="#89B4FA").pack(pady=20)

frame = tk.Frame(ventana, bg="#1E1E2E")
frame.pack(pady=10)

tk.Label(frame, text="Usuario:", bg="#1E1E2E", fg="#CDD6F4").pack(anchor="w")
entry_usuario = tk.Entry(frame, bg="#313244", fg="#CDD6F4", insertbackground="white", width=30, relief="flat")
entry_usuario.pack(pady=5, ipady=5)

tk.Label(frame, text="Contraseña:", bg="#1E1E2E", fg="#CDD6F4").pack(anchor="w")
entry_password = tk.Entry(frame, bg="#313244", fg="#CDD6F4", insertbackground="white", show="•", width=30, relief="flat")
entry_password.pack(pady=5, ipady=5)

# Seguridad
entry_password.bind("<<Paste>>", bloquear_accion)
entry_password.bind("<<Copy>>", bloquear_accion)
entry_password.bind("<Button-3>", bloquear_accion)

lbl_caps_warning = tk.Label(ventana, text="", font=("Helvetica", 8, "bold"), bg="#1E1E2E", fg="#F38BA8")
lbl_caps_warning.pack()

btn = tk.Button(ventana, text="INICIAR SESIÓN", command=iniciar_sistema, bg="#89B4FA", fg="#1E1E2E", 
               font=("Helvetica", 10, "bold"), width=25, cursor="hand2", relief="flat")
btn.pack(pady=20)

ventana.bind("<KeyRelease>", verificar_mayusculas)
verificar_mayusculas()

ventana.mainloop()