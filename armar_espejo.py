#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EL ESPEJO — el mes de cada cliente como va a salir, para mirarlo ANTES de subirlo.

    python3 armar_espejo.py "~/Desktop/PROGRAMAR 14-30 septiembre"

Lee una carpeta de entrega con la forma de siempre:

    PROGRAMAR 14-30 septiembre/
      1 THUNDER/
        16 MIERCOLES/
          1 - happy hour happy thunder hour todos los dias de.jpg
          2 - reservas reserva tu mesa (LINK).jpg
          NO SUBIR — 3 - horarios (horario viejo).jpg

...achica cada placa a una miniatura y deja todo en  espejo/<mes>/  para que el
dashboard lo muestre. NO toca los originales: sólo lee.

Se puede correr las veces que haga falta: rehace únicamente las miniaturas que
faltan o que cambiaron. Al final dice qué falta pushear.
"""

import argparse, json, os, re, subprocess, sys, unicodedata
from datetime import date

AQUI = os.path.dirname(os.path.abspath(__file__))

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
NOMBRE_DIA = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]

# Cómo se llama en la carpeta  ->  cómo se llama el cliente en el dashboard.
# Si una marca no está acá, se usa el nombre de la carpeta tal cual.
ALIAS = {
    "thunder": "Thunder",
    "bodegon": "Bodegón Co",
    "pasta co": "Pasta Co",
    "mar y vino": "Pasta Mar & Vino",
    "parrilla": "Parrilla Co",
    "chinita": "Chinita",
    "ap": "AP",
    "aurelia": "Aurelia",
    "clinica": "Clínica de Fracturas",
    "cantina": "Cantina Bernardo",
    "vialmaq": "Vialmaq",
    "solgast": "Solgast",
    "canntek": "Canntek",
    "degennaro": "De Gennaro Giaccone",
}

# El Excel de Franco: las solapas se llaman "THUNDER SEPTIEMBRE", "BODE SEPTIEMBRE"...
# y adentro de cada día él escribe los feeds como  FEED COMIDA / FEED VIDEO JODA.
DIAS_SEMANA = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
MARCAS_EXCEL = {
    "CHINITA": "Chinita", "THUNDER": "Thunder", "PASTA": "Pasta Co", "PASTAS": "Pasta Co",
    "BODE": "Bodegón Co", "BODEGON": "Bodegón Co", "PARRILLA": "Parrilla Co",
    "MAR": "Pasta Mar & Vino", "MARYVINO": "Pasta Mar & Vino",
}
# y así se llaman las marcas en el JSON ya parseado (franco_<mes>.json)
SLUG_EXCEL = {
    "chinita": "Chinita", "thunder": "Thunder", "pasta-co": "Pasta Co",
    "bodegon-co": "Bodegón Co", "parrilla-co": "Parrilla Co",
    "pasta-mar-y-vino": "Pasta Mar & Vino",
}

ANCHO_MINIATURA = 700      # px del lado largo: alcanza para LEER un precio adentro de la placa
CALIDAD = 58               # 0-100, cuanto más bajo más liviana


def pelar(s):
    """minúsculas, sin tildes, sin nada raro — para comparar nombres."""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", pelar(s)).strip("-") or "sin-nombre"


def nombre_cliente(carpeta):
    """'2 BODEGON' -> 'Bodegón Co'"""
    crudo = re.sub(r"^\d+\s+", "", carpeta).strip()
    crudo = re.sub(r"\s+\d+$", "", crudo).strip()     # las carpetas '... 2' partidas
    p = pelar(crudo)
    for clave, lindo in ALIAS.items():
        if p == clave or p.startswith(clave) or clave in p:
            return lindo
    return crudo.title()


def leer_placa(archivo):
    """Del nombre del archivo saca: orden, copy, si lleva link, si no se sube y por qué."""
    base = os.path.splitext(archivo)[0]
    no_sube, motivo = False, ""
    m = re.match(r"^NO SUBIR\s*[—-]\s*(.*)$", base)
    if m:
        no_sube, base = True, m.group(1)

    m = re.match(r"^(\d+)\s*-\s*(.*)$", base)
    orden, texto = (int(m.group(1)), m.group(2)) if m else (999, base)

    link = "(LINK)" in texto.upper()
    texto = re.sub(r"\(LINK\)", "", texto, flags=re.I)

    # lo que queda entre paréntesis al final es una aclaración nuestra, no el copy
    notas = re.findall(r"\(([^)]+)\)", texto)
    texto = re.sub(r"\([^)]*\)", "", texto)
    if notas and not motivo:
        motivo = notas[-1].strip()

    return orden, " ".join(texto.split()), link, no_sube, motivo


def miniatura(origen, destino, rehacer=False):
    """Achica con sips, que ya viene en la Mac. Devuelve False si no pudo."""
    if not rehacer and os.path.exists(destino) and os.path.getmtime(destino) >= os.path.getmtime(origen):
        return True
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    r = subprocess.run(
        ["sips", "-Z", str(ANCHO_MINIATURA), "-s", "format", "jpeg",
         "-s", "formatOptions", str(CALIDAD), origen, "--out", destino],
        capture_output=True)
    return r.returncode == 0 and os.path.exists(destino)


def _es_fila_dias(fila):
    vals = [pelar(c) for c in fila if c is not None and str(c).strip()]
    return len(vals) >= 5 and sum(1 for v in vals if v in DIAS_SEMANA) >= 5


def _parsear_solapa(ws, anio, num_mes):
    """La grilla de Franco: una fila con los días, abajo los números, abajo los items."""
    filas = [[c.value for c in f] for f in ws.iter_rows()]
    dias, i = {}, 0
    while i < len(filas):
        if not _es_fila_dias(filas[i]):
            i += 1
            continue
        col_fecha = {}
        for col, v in enumerate(filas[i + 1] if i + 1 < len(filas) else []):
            txt = str(v or "").strip()
            if re.fullmatch(r"\d{1,2}(\.0)?", txt):
                col_fecha[col] = int(float(txt))
        if not col_fecha:
            i += 1
            continue
        j = i + 2
        while j < len(filas) and not _es_fila_dias(filas[j]):
            for col, v in enumerate(filas[j]):
                txt = str(v or "").strip()
                if txt and col in col_fecha:
                    dias.setdefault("%04d-%02d-%02d" % (anio, num_mes, col_fecha[col]), []).append(txt)
            j += 1
        i = j
    return dias


def leer_feeds(ruta, anio, num_mes):
    """Devuelve {nombre_cliente: {fecha: [texto del feed, ...]}} leyendo el Excel de
    Franco (.xlsx) o el JSON que ya dejó parse_franco.py."""
    ruta = os.path.abspath(os.path.expanduser(ruta))
    crudo = {}
    if ruta.lower().endswith(".json"):
        with open(ruta, encoding="utf-8") as f:
            data = json.load(f)
        for slug, v in data.items():
            if slug.startswith("_"):
                continue
            nombre = SLUG_EXCEL.get(slug, slug.replace("-", " ").title())
            crudo[nombre] = v.get("dias", {})
    else:
        import openpyxl
        wb = openpyxl.load_workbook(ruta, data_only=True)
        mes_txt = pelar(MESES[num_mes - 1]).upper()
        for ws in wb:
            t = pelar(ws.title).upper()
            if mes_txt not in t:
                continue
            marca = MARCAS_EXCEL.get(ws.title.split()[0].upper())
            if not marca:
                continue
            crudo.setdefault(marca, {}).update(_parsear_solapa(ws, anio, num_mes))

    feeds = {}
    for nombre, dias in crudo.items():
        for fecha, items in dias.items():
            for it in items:
                if re.match(r"^\s*feed\b", str(it), re.I):
                    txt = re.sub(r"^\s*feed\s*", "", str(it), flags=re.I).strip() or "feed"
                    feeds.setdefault(nombre, {}).setdefault(fecha, []).append(txt)
    return feeds


def dias_de(carpeta_marca):
    """Las subcarpetas '16 MIERCOLES' ordenadas por número de día."""
    salida = []
    for d in sorted(os.listdir(carpeta_marca)):
        ruta = os.path.join(carpeta_marca, d)
        if not os.path.isdir(ruta) or d.startswith("."):
            continue
        m = re.match(r"^(\d+)\s+(.+)$", d)
        if not m:
            continue
        salida.append((int(m.group(1)), m.group(2).strip().lower(), ruta))
    return sorted(salida)


def main():
    ap = argparse.ArgumentParser(description="Arma el espejo del mes para el dashboard.")
    ap.add_argument("entrega", help="la carpeta de entrega (la de PROGRAMAR...)")
    ap.add_argument("--mes", help="mes en formato 2026-09 (si no, se adivina del nombre)")
    ap.add_argument("--salida", default=os.path.join(AQUI, "espejo"),
                    help="dónde dejar el paquete (por defecto: espejo/ al lado del dashboard)")
    ap.add_argument("--rehacer", action="store_true",
                    help="rehace todas las miniaturas aunque ya existan")
    ap.add_argument("--guardar", type=int, default=0, metavar="N",
                    help="deja sólo los últimos N meses en espejo/ y borra los más viejos")
    ap.add_argument("--franco", metavar="ARCHIVO",
                    help="el Excel de Franco (.xlsx) o el franco_<mes>.json ya parseado, "
                         "para traer los FEED de cada día")
    args = ap.parse_args()

    entrega = os.path.abspath(os.path.expanduser(args.entrega))
    if not os.path.isdir(entrega):
        sys.exit("No encuentro esa carpeta: " + entrega)

    # el mes: del argumento, o del nombre de la carpeta ('...septiembre' -> 2026-09)
    mes = args.mes
    if not mes:
        p = pelar(os.path.basename(entrega))
        for i, nombre in enumerate(MESES):
            if pelar(nombre) in p:
                anio = re.search(r"\b(20\d\d)\b", p)
                mes = "%s-%02d" % (anio.group(1) if anio else date.today().year, i + 1)
                break
    if not mes or not re.match(r"^\d{4}-\d{2}$", mes):
        sys.exit("No pude adivinar el mes. Pasalo a mano con  --mes 2026-09")

    anio, num_mes = int(mes[:4]), int(mes[5:7])
    destino_mes = os.path.join(args.salida, mes)
    os.makedirs(destino_mes, exist_ok=True)

    feeds_por_cliente = {}
    if args.franco:
        try:
            feeds_por_cliente = leer_feeds(args.franco, anio, num_mes)
            n = sum(len(v) for d in feeds_por_cliente.values() for v in d.values())
            print("  📰 %d feeds del Excel de Franco, en %d marcas" % (n, len(feeds_por_cliente)))
        except Exception as e:
            print("  ⚠️  no pude leer los feeds (%s). Sigo sin ellos." % e)

    clientes, total, con_link, no_suben = [], 0, 0, 0

    for marca_dir in sorted(os.listdir(entrega)):
        ruta_marca = os.path.join(entrega, marca_dir)
        if not os.path.isdir(ruta_marca) or marca_dir.startswith("."):
            continue
        dias = dias_de(ruta_marca)
        if not dias:
            continue                      # las carpetas partidas que quedaron vacías

        nombre = nombre_cliente(marca_dir)
        s = slug(nombre)
        cliente = {"nombre": nombre, "slug": s, "carpeta": marca_dir, "dias": []}

        for numero, nombre_dia, ruta_dia in dias:
            placas = []
            for archivo in sorted(os.listdir(ruta_dia)):
                if not archivo.lower().endswith((".jpg", ".jpeg", ".png")) or archivo.startswith("."):
                    continue
                orden, texto, link, no_sube, motivo = leer_placa(archivo)
                rel = "%s/%02d-%02d.jpg" % (s, numero, orden)
                if not miniatura(os.path.join(ruta_dia, archivo), os.path.join(destino_mes, rel), args.rehacer):
                    print("  ⚠️  no pude achicar:", archivo)
                    continue
                placas.append({"n": orden, "txt": texto, "link": link,
                               "no": no_sube, "motivo": motivo, "img": rel,
                               "archivo": archivo})
                total += 1
                con_link += 1 if link else 0
                no_suben += 1 if no_sube else 0
            if placas:
                placas.sort(key=lambda x: x["n"])
                cliente["dias"].append({
                    "dia": numero,
                    "nombre": nombre_dia,
                    "fecha": "%04d-%02d-%02d" % (anio, num_mes, numero),
                    "placas": placas,
                })

        # los feeds que anotó Franco para esta marca, aunque caigan en un día sin placas
        mis_feeds = feeds_por_cliente.get(nombre, {})
        por_dia = {d["dia"]: d for d in cliente["dias"]}
        for fecha, textos in sorted(mis_feeds.items()):
            numero = int(fecha[8:10])
            d = por_dia.get(numero)
            if not d:
                nombre_dia = NOMBRE_DIA[date(anio, num_mes, numero).weekday()]
                d = {"dia": numero, "nombre": nombre_dia, "fecha": fecha, "placas": [], "feeds": []}
                por_dia[numero] = d
                cliente["dias"].append(d)
            d.setdefault("feeds", []).extend(textos)
        cliente["dias"].sort(key=lambda d: d["dia"])
        total_feeds = sum(len(d.get("feeds", [])) for d in cliente["dias"])

        if cliente["dias"]:
            clientes.append(cliente)
            print("  %-22s %3d placas en %2d días%s" % (
                nombre, sum(len(d["placas"]) for d in cliente["dias"]), len(cliente["dias"]),
                (" · %d feeds" % total_feeds) if total_feeds else ""))

    if not clientes:
        sys.exit("No encontré ninguna placa adentro de esa carpeta.")

    # mezclar: si ya hay clientes en el espejo que no salen de esta carpeta
    # (por ejemplo los que trae espejo_notion.js), se respetan.
    archivo = os.path.join(destino_mes, "datos.json")
    datos = {"mes": mes, "titulo": "%s %d" % (MESES[num_mes - 1], anio), "clientes": []}
    if os.path.exists(archivo):
        with open(archivo, encoding="utf-8") as f:
            datos = json.load(f)
    mios = {c["slug"] for c in clientes}
    otros = [c for c in datos.get("clientes", []) if c["slug"] not in mios]
    datos["clientes"] = sorted(clientes + otros,
                               key=lambda c: (1 if c.get("origen") == "notion" else 0, c["nombre"]))
    datos["mes"] = mes
    datos["titulo"] = "%s %d" % (MESES[num_mes - 1], anio)
    datos["origen"] = os.path.basename(entrega)
    datos["armado"] = date.today().isoformat()
    cuenta = lambda f: sum(f(d) for c in datos["clientes"] for d in c["dias"])
    datos["total"]    = cuenta(lambda d: len(d["placas"]))
    datos["con_link"] = cuenta(lambda d: sum(1 for p in d["placas"] if p.get("link")))
    datos["no_suben"] = cuenta(lambda d: sum(1 for p in d["placas"] if p.get("no")))
    datos["feeds"]    = cuenta(lambda d: len(d.get("feeds", [])))
    if otros:
        print("  🔗 respeté %d clientes que ya estaban en el espejo (%s)" %
              (len(otros), ", ".join(c["nombre"] for c in otros)))
    with open(archivo, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, separators=(",", ":"))

    # podar meses viejos, si lo pidieron
    if args.guardar > 0:
        import shutil
        viejos = sorted(d for d in os.listdir(args.salida) if re.match(r"^\d{4}-\d{2}$", d))[:-args.guardar]
        for v in viejos:
            shutil.rmtree(os.path.join(args.salida, v))
            print("   🧹 borré el espejo de", v)

    # el índice de meses disponibles, para las flechitas del dashboard
    meses = sorted(d for d in os.listdir(args.salida)
                   if re.match(r"^\d{4}-\d{2}$", d)
                   and os.path.exists(os.path.join(args.salida, d, "datos.json")))
    with open(os.path.join(args.salida, "indice.json"), "w", encoding="utf-8") as f:
        json.dump({"meses": meses}, f, ensure_ascii=False)

    peso = sum(os.path.getsize(os.path.join(r, a))
               for r, _, aa in os.walk(destino_mes) for a in aa) / 1e6
    print("\n✅ Espejo de %s: %d placas · %d con link · %d marcadas NO SUBIR · %d feeds · %.1f MB" %
          (datos["titulo"], total, con_link, no_suben, datos["feeds"], peso))
    print("   Quedó en: %s" % destino_mes)
    print("   Para que lo vean todos:  cd %s && git add espejo && git commit -m 'espejo %s' && git push" % (AQUI, mes))


if __name__ == "__main__":
    main()
