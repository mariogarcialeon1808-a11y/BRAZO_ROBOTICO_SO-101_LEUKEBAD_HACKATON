"""Contenedor para reutilizar pantallas dentro de una única ventana Tk."""
from tkinter import ttk


class MarcoVentana(ttk.Frame):
    def __init__(self,parent):
        super().__init__(parent);self.pack(fill='both',expand=True)
    def title(self,*args):pass
    def geometry(self,*args):pass
    def minsize(self,*args):pass
    def protocol(self,*args):pass
    def withdraw(self):pass
    def deiconify(self):pass
    def mainloop(self,*args):pass


def ventana(parent=None):
    if parent is not None:return MarcoVentana(parent)
    import tkinter as tk
    return tk.Tk()
