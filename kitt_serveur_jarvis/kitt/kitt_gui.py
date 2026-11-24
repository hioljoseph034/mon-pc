"""Interface graphique de KITT : ecran noir, scanner rouge, journal, saisie,
gestion des skills et controle d'Internet.

L'interface n'execute aucune logique metier : elle appelle kitt_skills et kitt_securite,
et envoie les commandes dans la file de KITT comme le ferait le clavier.
"""
import queue
import random
import tkinter as tk
from tkinter import messagebox

import kitt_securite as sec
import kitt_skills as ks


class InterfaceKitt:
    N = 8                                       # nombre de segments du scanner
    VITESSES = {"veille": 0.25, "ecoute": 0.6, "reflexion": 0.4, "parle": 0.9}
    LIBELLES = {"veille": "EN VEILLE - dites « KITT »", "ecoute": "JE VOUS ÉCOUTE",
                "reflexion": "RÉFLEXION...", "parle": "KITT PARLE"}

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("KITT")
        self.root.configure(bg="black")
        self.root.geometry("680x520")
        self.kitt = None
        self.q = queue.Queue()                  # lignes de journal venant de KITT
        self.pos, self.sens, self.tick = 0.0, 1, 0

        tk.Label(self.root, text="K . I . T . T", fg="#ff2a2a", bg="black",
                 font=("Consolas", 22, "bold")).pack(pady=(12, 4))
        self.canvas = tk.Canvas(self.root, width=600, height=60, bg="black", highlightthickness=0)
        self.canvas.pack()
        self.rects = [self.canvas.create_rectangle(10 + i * 72, 10, 70 + i * 72, 50,
                                                   fill="#200000", outline="")
                      for i in range(self.N)]
        self.statut = tk.Label(self.root, text="", fg="#ff6a6a", bg="black", font=("Consolas", 11))
        self.statut.pack(pady=2)
        self.reseau_lbl = tk.Label(self.root, text="", fg="#884444", bg="black",
                                   font=("Consolas", 9))
        self.reseau_lbl.pack()

        self.journal = tk.Text(self.root, height=12, bg="#0b0b0b", fg="#ff5555",
                               font=("Consolas", 10), state="disabled", bd=0, wrap="word")
        self.journal.pack(fill="both", expand=True, padx=10, pady=(6, 0))

        bas = tk.Frame(self.root, bg="black")
        bas.pack(fill="x", padx=10, pady=8)
        self.entree = tk.Entry(bas, bg="#161616", fg="#ff8080", insertbackground="#ff8080",
                               font=("Consolas", 11), bd=0)
        self.entree.pack(side="left", fill="x", expand=True, ipady=4)
        self.entree.bind("<Return>", self.envoyer)
        self.entree.focus_set()
        for texte, cmd in (("Internet", self.ouvrir_reseau), ("Skills", self.ouvrir_skills),
                           ("Fichier", self.joindre)):
            tk.Button(bas, text=texte, command=cmd, bg="#2a0000", fg="#ff8080",
                      activebackground="#550000", activeforeground="#ffaaaa", bd=0,
                      font=("Consolas", 10), padx=8).pack(side="right", padx=(6, 0))

        self.root.protocol("WM_DELETE_WINDOW", self.fermer)
        self.animer()

    # ----- entrees / sorties -----
    def log(self, ligne):
        self.q.put(ligne)

    def envoyer(self, _event):
        t = self.entree.get().strip()
        self.entree.delete(0, "end")
        if t and self.kitt:
            self.kitt.texte_q.put(t)

    def joindre(self):
        from tkinter import filedialog
        chemin = filedialog.askopenfilename(title="Choisir un fichier pour KITT")
        if chemin and self.kitt:
            from pathlib import Path
            self.kitt.fichier_courant = Path(chemin)
            self.kitt.texte_q.put("quel est le fichier joint")

    def fermer(self):
        if self.kitt:
            self.kitt.actif = False
        self.root.destroy()

    # ----- fenetre Skills : installer / desinstaller / creer une recette -----
    def ouvrir_skills(self):
        fen = tk.Toplevel(self.root)
        fen.title("KITT — Skills")
        fen.configure(bg="black")
        liste = tk.Listbox(fen, width=70, height=10, bg="#0b0b0b", fg="#ff8080",
                           font=("Consolas", 10), selectbackground="#550000")
        liste.pack(padx=10, pady=10, fill="both", expand=True)

        def remplir():
            liste.delete(0, "end")
            inst = ks.installes()
            for nom, info in ks.CATALOGUE.items():
                liste.insert("end", f"[{'x' if nom in inst else ' '}] {nom} : {info['titre']}")
            for nom in sorted(inst - set(ks.CATALOGUE)):
                liste.insert("end", f"[x] {nom} : skill créé par vous")

        def selection():
            s = liste.curselection()
            if not s:
                messagebox.showinfo("KITT", "Sélectionnez un skill dans la liste.", parent=fen)
                return None
            return liste.get(s[0]).split("] ", 1)[1].split(" : ", 1)[0]

        def installer():
            nom = selection()
            if nom:
                messagebox.showinfo("KITT", ks.installer(nom), parent=fen)
                remplir()

        def desinstaller():
            nom = selection()
            if nom and messagebox.askyesno("KITT", f"Désinstaller « {nom} » ?", parent=fen):
                messagebox.showinfo("KITT", ks.desinstaller(nom), parent=fen)
                remplir()

        def nouveau():
            self.formulaire_recette(fen, remplir)

        barre = tk.Frame(fen, bg="black")
        barre.pack(fill="x", padx=10, pady=(0, 10))
        for texte, cmd in (("Installer", installer), ("Désinstaller", desinstaller),
                           ("Nouveau skill", nouveau)):
            tk.Button(barre, text=texte, command=cmd, bg="#2a0000", fg="#ff8080", bd=0,
                      font=("Consolas", 10), padx=8).pack(side="left", padx=4)
        remplir()

    def formulaire_recette(self, parent, au_succes):
        fen = tk.Toplevel(parent)
        fen.title("KITT — Nouveau skill")
        fen.configure(bg="black")
        champs = {}
        for libelle, cle, aide in (("Nom", "nom", "ex. salut_matin"),
                                   ("Déclencheurs", "decl", "séparés par des virgules : bonjour, salut"),
                                   ("Réponse", "rep", "ce que KITT dira")):
            tk.Label(fen, text=f"{libelle} ({aide})", fg="#ff6a6a", bg="black",
                     font=("Consolas", 9)).pack(anchor="w", padx=10, pady=(8, 0))
            champs[cle] = tk.Entry(fen, width=60, bg="#161616", fg="#ff8080",
                                   insertbackground="#ff8080", font=("Consolas", 10), bd=0)
            champs[cle].pack(padx=10, pady=2, fill="x")

        def valider():
            res = ks.creer_recette(champs["nom"].get(), champs["decl"].get().split(","),
                                   champs["rep"].get())
            messagebox.showinfo("KITT", res, parent=fen)
            if res.startswith("Skill"):
                au_succes()
                fen.destroy()

        tk.Button(fen, text="Créer", command=valider, bg="#2a0000", fg="#ff8080", bd=0,
                  font=("Consolas", 10), padx=12).pack(pady=10)

    # ----- fenetre Internet : chaque service se coche avec confirmation -----
    def ouvrir_reseau(self):
        fen = tk.Toplevel(self.root)
        fen.title("KITT — Accès Internet")
        fen.configure(bg="black")
        tk.Label(fen, text="Internet est coupé par défaut.\nCochez seulement les services voulus.",
                 fg="#ff6a6a", bg="black", font=("Consolas", 10)).pack(padx=10, pady=8)
        cfg = sec.charger_config()
        for service in sec.SERVICES_RESEAU:
            var = tk.BooleanVar(value=cfg["reseau"].get(service, False))

            def basculer(s=service, v=var):
                if v.get():
                    if not messagebox.askyesno(
                            "KITT", f"Autoriser KITT à contacter « {s} » sur Internet ?", parent=fen):
                        v.set(False)
                        return
                messagebox.showinfo("KITT", ks.activer_reseau(s, v.get()), parent=fen)

            tk.Checkbutton(fen, text=service, variable=var, command=basculer, bg="black",
                           fg="#ff8080", selectcolor="#2a0000", activebackground="black",
                           font=("Consolas", 11)).pack(anchor="w", padx=20, pady=2)

    def etat_reseau(self):
        actifs = [s for s in sec.SERVICES_RESEAU if sec.reseau_active(s)]
        return "INTERNET : " + ", ".join(actifs) if actifs else "HORS LIGNE (aucun service autorisé)"

    # ----- animation -----
    def animer(self):
        if self.kitt and not self.kitt.actif:
            self.root.destroy()
            return
        etat = self.kitt.etat if self.kitt else "veille"
        self.pos += self.sens * self.VITESSES.get(etat, 0.3)
        if self.pos >= self.N - 1:
            self.pos, self.sens = self.N - 1, -1
        elif self.pos <= 0:
            self.pos, self.sens = 0, 1
        for i, r in enumerate(self.rects):
            v = max(0.0, 1 - abs(i - self.pos) / 2.5)
            if etat == "parle":
                v = min(1.0, v * random.uniform(0.7, 1.25))
            self.canvas.itemconfig(r, fill=f"#{int(32 + 223 * v):02x}0000")
        self.statut.config(text=self.LIBELLES.get(etat, ""))
        self.tick += 1
        if self.tick % 60 == 1:                 # rafraichit l'etat reseau environ toutes les 2 s
            self.reseau_lbl.config(text=self.etat_reseau())
        try:
            while True:
                ligne = self.q.get_nowait()
                self.journal.config(state="normal")
                self.journal.insert("end", ligne + "\n")
                self.journal.see("end")
                self.journal.config(state="disabled")
        except queue.Empty:
            pass
        self.root.after(30, self.animer)

    def run(self):
        self.root.mainloop()
