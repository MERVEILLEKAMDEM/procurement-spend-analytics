"""Analyse des dépenses achats (spend analysis) sur des données fictives.

Produit : classification ABC des fournisseurs, concentration (indice HHI),
achats hors contrat (maverick buying), écarts de prix sur un même article,
potentiel d'économies et un classeur Excel de synthèse.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RACINE = Path(__file__).resolve().parents[1]
DATA, RES = RACINE / "data", RACINE / "results"
FIG = RES / "figures"
BLEU, ORANGE, GRIS = "#1f4e79", "#e67e22", "#bdc3c7"

CATEGORIES = {
    "Informatique": ["Ordinateur portable", "Écran 27 pouces", "Licence logicielle", "Serveur"],
    "Fournitures": ["Ramette papier", "Cartouche toner", "Mobilier bureau"],
    "Prestations IT": ["Jour consultant data", "Maintenance applicative", "Support N2"],
    "Logistique": ["Transport palette", "Stockage mensuel"],
    "Énergie": ["Électricité MWh", "Gaz MWh"],
    "Marketing": ["Campagne digitale", "Impression catalogue"],
}
PRIX_REF = {
    "Ordinateur portable": 1100, "Écran 27 pouces": 260, "Licence logicielle": 480, "Serveur": 6500,
    "Ramette papier": 4.5, "Cartouche toner": 85, "Mobilier bureau": 420,
    "Jour consultant data": 650, "Maintenance applicative": 2200, "Support N2": 900,
    "Transport palette": 140, "Stockage mensuel": 1800, "Électricité MWh": 180, "Gaz MWh": 95,
    "Campagne digitale": 12000, "Impression catalogue": 7500,
}


def generer(n=12000, seed=7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    fournisseurs = [f"FRN-{i:03d}" for i in range(1, 121)]
    # Quelques gros fournisseurs concentrent la dépense (loi de Zipf)
    poids = 1 / np.arange(1, 121) ** 1.1
    poids /= poids.sum()
    articles = [a for v in CATEGORIES.values() for a in v]
    cat_de = {a: c for c, v in CATEGORIES.items() for a in v}
    art = rng.choice(articles, n)
    frn = rng.choice(fournisseurs, n, p=poids)
    # Chaque fournisseur a son propre niveau de prix (+/- 25 %)
    niveau = dict(zip(fournisseurs, rng.uniform(0.85, 1.25, len(fournisseurs))))
    prix = np.array([PRIX_REF[a] * niveau[f] * rng.normal(1, 0.05) for a, f in zip(art, frn)])
    qte = np.maximum(1, rng.poisson([3 if PRIX_REF[a] > 1000 else 25 for a in art]))
    sous_contrat = set(fournisseurs[:35])
    df = pd.DataFrame({
        "id_commande": [f"PO{i:06d}" for i in range(n)],
        "date": pd.Timestamp("2025-01-01") + pd.to_timedelta(rng.integers(0, 365, n), "D"),
        "fournisseur": frn,
        "categorie": [cat_de[a] for a in art],
        "article": art,
        "quantite": qte,
        "prix_unitaire": prix.round(2),
        "entite": rng.choice(["Siège", "Région Nord", "Région Sud", "Région Ouest"], n),
    })
    df["montant"] = (df["quantite"] * df["prix_unitaire"]).round(2)
    df["sous_contrat"] = df["fournisseur"].isin(sous_contrat)
    return df


def abc(df):
    s = df.groupby("fournisseur")["montant"].sum().sort_values(ascending=False).to_frame()
    s["part"] = s["montant"] / s["montant"].sum()
    s["cumul"] = s["part"].cumsum()
    s["classe"] = np.where(s["cumul"] <= 0.80, "A", np.where(s["cumul"] <= 0.95, "B", "C"))
    return s


def hhi(df):
    """Indice Herfindahl-Hirschman par catégorie (0-10 000)."""
    p = df.groupby(["categorie", "fournisseur"])["montant"].sum()
    parts = p / p.groupby(level=0).transform("sum") * 100
    return (parts ** 2).groupby(level=0).sum().round(0).sort_values(ascending=False)


def ecarts_prix(df):
    """Pour chaque article : économie si tout était acheté au prix du 1er quartile."""
    q1 = df.groupby("article")["prix_unitaire"].transform(lambda s: s.quantile(0.25))
    df = df.assign(cible=q1, economie=np.maximum(0, (df["prix_unitaire"] - q1) * df["quantite"]))
    t = df.groupby(["categorie", "article"]).agg(
        depense=("montant", "sum"), prix_min=("prix_unitaire", "min"),
        prix_max=("prix_unitaire", "max"), economie=("economie", "sum"))
    t["ecart_prix_%"] = ((t["prix_max"] / t["prix_min"] - 1) * 100).round(1)
    return t.sort_values("economie", ascending=False)


def main():
    FIG.mkdir(parents=True, exist_ok=True); DATA.mkdir(exist_ok=True)
    df = generer()
    df.to_csv(DATA / "commandes.csv", index=False)

    total = df["montant"].sum()
    a = abc(df)
    h = hhi(df)
    e = ecarts_prix(df)
    hors = df[~df["sous_contrat"]]
    mensuel = df.set_index("date").resample("MS")["montant"].sum()

    kpi = pd.Series({
        "Dépense totale (€)": round(total),
        "Nombre de fournisseurs": df["fournisseur"].nunique(),
        "Fournisseurs classe A": int((a["classe"] == "A").sum()),
        "Part de la dépense en classe A": f"{a.loc[a.classe == 'A', 'part'].sum():.1%}",
        "Dépense hors contrat (€)": round(hors["montant"].sum()),
        "Taux hors contrat": f"{hors['montant'].sum() / total:.1%}",
        "Économie potentielle prix (€)": round(e["economie"].sum()),
        "Économie potentielle (% dépense)": f"{e['economie'].sum() / total:.1%}",
    })

    # ---- Graphiques ----------------------------------------------------------
    fig, ax = plt.subplots(figsize=(9, 4))
    x = np.arange(1, len(a) + 1)
    ax.bar(x, a["montant"] / 1e6, color=[{"A": BLEU, "B": ORANGE, "C": GRIS}[c] for c in a["classe"]])
    ax2 = ax.twinx(); ax2.plot(x, a["cumul"] * 100, color="black", lw=1.5)
    ax2.axhline(80, ls="--", color="grey", lw=.8); ax2.set_ylim(0, 105); ax2.set_ylabel("% cumulé")
    ax.set_xlabel("Fournisseurs (triés par dépense)"); ax.set_ylabel("Dépense (M€)")
    ax.set_title("Pareto fournisseurs – classes A (bleu), B (orange), C (gris)")
    fig.tight_layout(); fig.savefig(FIG / "pareto_abc.png", dpi=150); plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.plot(mensuel.index, mensuel / 1e6, marker="o", color=BLEU)
    ax.set_title("Dépense mensuelle (M€)"); ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig(FIG / "depense_mensuelle.png", dpi=150); plt.close(fig)

    top = e.head(8).reset_index()
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.barh(top["article"][::-1], top["economie"][::-1] / 1e3, color=ORANGE)
    ax.set_xlabel("k€"); ax.set_title("Top 8 des leviers d'économies (alignement sur le 1er quartile de prix)")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig(FIG / "leviers_economies.png", dpi=150); plt.close(fig)

    # ---- Classeur Excel ------------------------------------------------------
    with pd.ExcelWriter(RES / "spend_analysis.xlsx") as xw:
        kpi.to_frame("valeur").to_excel(xw, sheet_name="KPI")
        a.to_excel(xw, sheet_name="ABC fournisseurs")
        h.to_frame("HHI").to_excel(xw, sheet_name="Concentration")
        e.to_excel(xw, sheet_name="Écarts de prix")
        hors.groupby("fournisseur")["montant"].sum().sort_values(ascending=False) \
            .to_frame("depense_hors_contrat").to_excel(xw, sheet_name="Hors contrat")
    print(kpi.to_string())
    print("\nHHI par catégorie :\n", h.to_string())
    return kpi, h, e


if __name__ == "__main__":
    main()
