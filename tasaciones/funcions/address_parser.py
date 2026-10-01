# -*- coding: utf-8 -*-
import re
import unicodedata
from typing import Dict, List, Optional, Tuple, Any

# -------------------------------
# LÍMITES DE COLUMNAS
# -------------------------------
DOMICILIO_MAX = 50
EXT_MAX = 8
INT_MAX = 8
REF_MAX = 25
UBIC_MAX = 30

# -------------------------------
# CONFIG
# -------------------------------
DOMICILIO_WITH_PREFIX = False
TIPO_BONUS = {'AVENIDA': 2, 'JIRON': 1, 'CALLE': 0}
ALLOW_NUMBERS_VIA_2_3 = True
MIN_SECOND_SEG_LEN = 8

# -------------------------------
# UTILIDADES
# -------------------------------
def strip_accents(s: str) -> str:
    if not isinstance(s, str):
        return ""
    return ''.join(c for c in unicodedata.normalize('NFD', s)
                   if unicodedata.category(c) != 'Mn')

def norm_spaces(s: str) -> str:
    s = s if isinstance(s, str) else ""
    return re.sub(r'\s+', ' ', s).strip()

def upper(s: str) -> str: return (s or "").upper()
def limit(s: str, n: int) -> str: return (s or "")[:n]

def default_sn(s: str) -> str:
    s = (s or "").strip()
    return s if s else "SN"

def uniq_preserve(seq: List[Any]) -> List[Any]:
    out, seen = [], set()
    for x in seq:
        if x not in seen:
            out.append(x); seen.add(x)
    return out

def only_numbers_like(s: str) -> bool:
    return bool(s) and re.fullmatch(r'[0-9\.\-\s]+', s.strip()) is not None

def only_digits(s: str) -> str:
    return re.sub(r'[^0-9]', '', s or '')

def has_two_words(s: str) -> bool:
    return len([w for w in s.split() if w]) >= 2

def truncate_by_components(s: str, max_len: int, sep: str = "/") -> str:
    s = s or ""
    s = norm_spaces(s).strip(sep)
    if len(s) <= max_len:
        return s
    parts = [p for p in s.split(sep) if p]
    out = ""
    for p in parts:
        cand = (out + (sep if out else "") + p)
        if len(cand) <= max_len:
            out = cand
        else:
            break
    return out

def _canon_text(s: str) -> str:
    s = upper(strip_accents(norm_spaces(s or "")))
    s = re.sub(r'[^A-Z0-9 ]', ' ', s)
    s = norm_spaces(s)
    return s

def _norm_ref_token(tok: str) -> str:
    tok = upper((tok or "").strip())
    tok = re.sub(r'\s+', '', tok)
    tok = tok.strip('-')
    return tok

def is_ref_token_valid(tok: str, allow_letter_only: bool = False) -> bool:
    tok = _norm_ref_token(tok)
    if not tok:
        return False
    if not re.fullmatch(r'[A-Z0-9]+(?:-[A-Z0-9]+)?', tok):
        return False
    if allow_letter_only:
        return True
    return bool(re.search(r'\d', tok))

def base_via_segment(seg: str) -> str:
    s = upper(norm_spaces(seg or ""))
    s = re.sub(r'\s+\d{1,6}(?:[-‐–—−]\d{1,6}){0,10}\s*$', '', s).strip()
    return s

def is_contained_base(a: str, b: str) -> bool:
    ba = _canon_text(base_via_segment(a))
    bb = _canon_text(base_via_segment(b))
    if not ba or not bb:
        return False
    if len(ba.split()) < 2 or len(bb.split()) < 2:
        return False
    return (ba in bb) or (bb in ba)

def abbreviate_series_compact(nums, max_len_allowed):
    if not nums: return ""
    nums = uniq_preserve(nums)
    if len(nums) <= 1: return nums[0]
    if max_len_allowed is None or max_len_allowed <= 0: return nums[0]
    # Simplificado para brevedad en esta integración
    res = "-".join([nums[0], nums[-1]])
    if len(res) <= max_len_allowed: return res
    return nums[0]

def extract_numbers_series(segment: str) -> Tuple[List[str], str]:
    raw_norm = re.sub(r'[‐-–—−‒﹘﹣－]', '-', segment)
    raw_norm = re.sub(r'\s*-\s*', '-', raw_norm)
    nums = re.findall(r'\d{1,6}', raw_norm)
    return nums, segment

# -------------------------------
# VÍAS + DELIMITADORES
# -------------------------------
VIA_PATTERNS = [
    (r'\bavenida\b|\bav(?:enida)?\.?(?=\s|$|[A-Za-zÁÉÍÓÚÜÑáéíóúüñ])|\bavda\.?\b', 'AVENIDA'),
    (r'\bcalle\b|\bcal\.?(?=\s|$|[A-Za-zÁÉÍÓÚÜÑáéíóúüñ])', 'CALLE'),
    (r'\bjir[oó]n\b|\bjr\.?(?=\s|$|[A-Za-zÁÉÍÓÚÜÑáéíóúüñ])', 'JIRON'),
    (r'\bpasaje\b|\bpsj(?:e)?\.?(?=\s|$)|\bpje\.?(?=\s|$)', 'PASAJE'),
    (r'\bprolongaci[oó]n\b|\bprol\.?(?=\s|$)', 'PROLONGACION'),
    (r'\bmalec[oó]n\b|\bml\.?(?=\s|$)', 'MALECON'),
    (r'\bboulevard\b|\bbvd\.?(?=\s|$)|\bbv\.?(?=\s|$)', 'BOULEVARD'),
    (r'\bcarretera\b|\bctra\.?(?=\s|$)|\bcr\.?(?=\s|$)', 'CARRETERA'),
    (r'\bcamino\b', 'CAMINO'),
    (r'\bparque\b|\bpq\.?(?=\s|$)', 'PARQUE'),
    (r'\balameda\b|\bal\.?(?=\s|$)', 'ALAMEDA'),
    (r'\bplaza\b|\bplz\.?(?=\s|$)', 'PLAZA'),
    (r'\b[óo]valo\b|\bovalo\b|\bov\.?(?=\s|$)', 'OVALO'),
    (r'\bautopista\b', 'AUTOPISTA'),
    (r'\bcallej[oó]n\b|\bcjon\.?(?=\s|$)|\bcallej\.?(?=\s|$)', 'CALLEJON'),
    (r'\btransversal\b|\btransv\.?(?=\s|$)|\btv\.?(?=\s|$)', 'TRANSVERSAL'),
    (r'\bv[ií]a\s+expresa\b', 'AVENIDA'),
    (r'\bpaseo\b|\bpas\.?(?=\s|$)', 'PASEO'),
    (r'\bpuente\b|\bpu\.?(?=\s|$)', 'PUENTE'),
    (r'\bcentro\s+comercial\b|\bcc\.?(?=\s|$)', 'CENTRO COMERCIAL'),
    (r'\bgaler[ií]a\b|\bga\.?(?=\s|$)', 'GALERIA'),
]

NUMTOK = r'(?:n°|nº|nro\.?|nros?\.?|no\.?|num\.?|n[uú]mero)'
CONNECTORS = r'\b(con|y|esquina(?:\s+con)?|esq\.?|frente\s+a|que\s+da\s+a|cerca\s+a|a\s+la\s+altura\s+de|altura\s+de|al\s+costado\s+de)\b'
DELIMITERS = (
    r'(,|;| - |/|#|' + NUMTOK + r'|\bn\.?(?=\s*\d)|\bkm\b|\bpiso\b|\btorre\b|\bedificio\b|'
    r'\bdepto\b|\bdepartamento\b|\bint\b|\binterior\b|\best(?:\.|acionamiento)?\b|'
    r'\bs[oó]tano\b|\bmanzana\b|\bmz\b|\blote\b|\blt\b|\betapa\b|\bunidad\b|\bunidad inmobiliaria\b|'
    r'\burb\.?\b|\burbanizaci[oó]n\b|\bcondominio\b|\bresidencial\b|\bproyecto\b|'
    + CONNECTORS + r'|$)'
)
ATTR_CUTOFF = r'\b(piso|torre|departamento|dep|dpto|depto|est(?:\.|acionamiento)?|s[oó]tano|manzana|mz|lote|lt|etapa|unidad(?: inmobiliaria)?|edificio|urbanizaci[oó]n|condominio|residencial|proyecto)\b'
ATTR_CUTOFF_RE = re.compile(ATTR_CUTOFF, re.I)

def find_all_vias(text: str) -> List[Dict[str, Any]]:
    base = norm_spaces(text)
    low = strip_accents(base.lower())
    vias = []
    for pat, tipo in VIA_PATTERNS:
        for m in re.finditer(pat, low):
            after = base[m.end():]
            nom = re.match(r'^\s*([A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9\-\.\' ]{1,100}?)(?=' + DELIMITERS + ')', after, re.I)
            if nom:
                raw_name = norm_spaces(nom.group(1))
                mnum = re.search(r'\s+\d{1,6}(?:\s*[-–—]\s*\d{1,6}){0,20}\s*$', raw_name)
                if mnum:
                    nombre = norm_spaces(raw_name[:mnum.start()])
                    name_end_abs = m.end() + nom.start(1) + mnum.start()
                else:
                    nombre = raw_name
                    name_end_abs = m.end() + nom.end()
            else:
                nombre = ""
                name_end_abs = m.end()
            vias.append({"tipo": tipo, "nombre": nombre, "pos": m.end(), "name_end": name_end_abs})
    return sorted(vias, key=lambda x: x["pos"])

def choose_primary_vias(vias, text, top=3):
    def has_num_after(v):
        seg = text[v["pos"]: v["pos"] + 120]
        for m in re.finditer(NUMTOK + r'\s*\d|km\s*\d|\b\d{1,6}\b', seg, re.I):
            abs_idx = v["pos"] + m.start()
            if "name_end" not in v or abs_idx >= v["name_end"]:
                return True
        return False
    return sorted(vias, key=lambda v: (not has_num_after(v), v["pos"], -TIPO_BONUS.get(v["tipo"], 0)))[:top]

def clean_via_name(name: str) -> str:
    original = name
    name = re.sub(r'\bnum\.?\b|\bn[uú]mero\b|\b(que da a|frente a|esquina(?:\s+con)?|esq\.?)\b', '', name, flags=re.I)
    name = re.sub(r'(?:' + NUMTOK + r'|n\.?(?=\s*\d)).*$', '', name, flags=re.I).strip()
    if re.search(r'[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]', name):
        name = re.sub(r'\s*\d{1,6}\s*(?:[-‐-–—−‒﹘﹣－]\s*\d{1,6})?\s*$', '', name).strip()
        name = re.sub(r'[-‐-–—−‒﹘﹣－]\s*$', '', name).strip()
    name = re.sub(r'^[\.\-_/]+\s*', '', name).strip()
    name = re.sub(r'\s+', ' ', name).strip()
    name = re.sub(r'\.+$', '', name).strip()
    if not name or len(name) <= 1:
        name = original
    o = upper(strip_accents(norm_spaces(original)))
    n = upper(strip_accents(norm_spaces(name)))
    if o.endswith("ON") and n.endswith("O") and not n.endswith("ON"):
        name = (name + "N").strip()
    return upper(name)

def extract_exterior(text: str, primary_vias: List[Dict[str, Any]]) -> Tuple[str, str]:
    seg_start = primary_vias[0]["pos"] if primary_vias else 0
    seg = text[seg_start:]
    neg_context = r'\b(torre|piso|departamento|dep|dpto|depto|est|estacionamiento|cochera|sotano|manzana|mz|lote|lt|etapa|unidad|edificio|cuadra|cdra|parcela|acumulacion)\b'
    
    def has_neg(s, idx):
        prev = s[max(0, idx-35):idx]
        return re.search(neg_context, prev, re.I) is not None

    for m in re.finditer(r'(?:\b' + NUMTOK + r'\s*)?(\d{1,6}(?:\s*[-–—]\s*\d{1,6}){0,20})\b', seg, re.I):
        if not has_neg(seg, m.start()):
            nums, raw = extract_numbers_series(m.group(1))
            if nums: return limit(upper(nums[0]), EXT_MAX), upper(raw)

    mz = re.search(r'\b(mz|manzana)\b\.?\s*([A-Z0-9\-]+)', text, re.I)
    if mz and is_ref_token_valid(mz.group(2), True):
        return limit(f"MZ {upper(mz.group(2))}", EXT_MAX), f"MZ {upper(mz.group(2))}"
    return "", ""

def extract_interior(text: str) -> str:
    patterns = [
        rf'\b(departamento|dpto|int\.?|interior|of\.?|tienda|tda\.?|stand|puesto)\b\.?\s*(?:{NUMTOK}\s*)?([A-Z0-9\-]+)',
    ]
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            val = upper(m.group(2)).strip()
            if re.search(r'\d', val) or len(val) > 3:
                return limit(val, INT_MAX)
    return ""

def extract_referencia(text: str) -> Tuple[str, str, str]:
    ref = []
    # Pisos
    m = re.search(r'\bpiso\b\s*(?:' + NUMTOK + r'\s*)?(\d{1,2})\b', text, re.I)
    if m: ref.append(f"PS{m.group(1)}")
    # MZ / LT
    mz = re.search(r'\b(mz|manzana)\b\.?\s*([A-Z0-9\-]+)', text, re.I)
    if mz: ref.append(f"MZ {upper(mz.group(2))}")
    lt = re.search(r'\b(lt|lote)\b\.?\s*([A-Z0-9\-]+)', text, re.I)
    if lt: ref.append(f"LT {upper(lt.group(2))}")
    
    res = "/".join(ref)
    return truncate_by_components(res, REF_MAX), upper(res), res

def extract_ubicacion(text: str) -> Tuple[str, str, str]:
    m = re.search(r'\b(urb\.?|urbanizaci[oó]n|condominio|residencial)\b\.?\s*([A-ZÁÉÍÓÚÜÑ0-9\' ]{3,100})', text, re.I)
    if m:
        tipo = upper(m.group(1))
        if "URB" in tipo: tipo = "URBANIZACION"
        elif "COND" in tipo: tipo = "CONDOMINIO"
        elif "RES" in tipo: tipo = "RESIDENCIAL"
        return tipo, limit(upper(m.group(2)).strip(), UBIC_MAX), upper(m.group(0))
    return "", "", ""

def extract_admin_peru(text: str) -> Dict[str, str]:
    t = upper(strip_accents(text))
    dist = re.search(r'DISTRITO(?:\s+DE)?\s+([A-Z ]+)', t)
    
    # Mejora para capturar Provincia y Departamento incluso si vienen juntos
    prov_dep_match = re.search(r'PROVINCIA\s+Y\s+DEPARTAMENTO\s+DE\s+([A-Z ]+)', t)
    if prov_dep_match:
        prov = prov_dep_match.group(1)
        dep = prov_dep_match.group(1)
    else:
        prov_match = re.search(r'PROVINCIA(?:\s+DE)?\s+([A-Z ]+)', t)
        dep_match = re.search(r'(DEPARTAMENTO|REGION)\s+DE\s+([A-Z ]+)', t)
        prov = prov_match.group(1) if prov_match else ""
        dep = dep_match.group(2) if dep_match else ""
    
    # Limpieza de distritos que capturan más de la cuenta
    dist_val = dist.group(1).split(',')[0].strip() if dist else ""
    
    return {
        "DISTRITO": default_sn(upper(dist_val)),
        "PROVINCIA": default_sn(upper(prov.split(',')[0].strip())),
        "DEPARTAMENTO": default_sn(upper(dep.split(',')[0].strip())),
    }

def build_domicilio_and_extra(vias, text, ext_val=""):
    parts = []
    chosen = choose_primary_vias(vias, text, top=2)
    for idx, v in enumerate(chosen):
        name = clean_via_name(v["nombre"])
        if name and not any(name in p for p in parts):
            if len("/".join(parts + [name])) <= DOMICILIO_MAX:
                parts.append(name)
    
    # Fallback si build_domicilio_and_extra no encuentra vías: usar la dirección extraída limpia
    dom = "/".join(parts)
    if not dom or dom == "SN":
        # Intentar extraer algo útil antes del primer "N°"
        m = re.search(r'^([^N°0-9]+)', text)
        if m:
            dom = m.group(1).strip()
            
    return default_sn(dom), []

# Mapeos oficiales según hoja DATOS de la macro bancaria
MAP_VIAS = {
    "AVENIDA": "AV.", "JIRON": "JR.", "CALLE": "CAL", "PASAJE": "PSJ",
    "ALAMEDA": "AL.", "MALECON": "ML.", "OVALO": "OV.", "PARQUE": "PQE",
    "PLAZA": "PL.", "PROLONGACION": "PR.", "PUENTE": "PU.", "CARRETERA": "CR.",
    "CENTRO COMERCIAL": "CC.", "GALERIA": "GA.", "PASEO": "PAS"
}

MAP_UBICACION = {
    "URBANIZACION": "URB", "ETAPA": "ETP", "CONDOMINIO": "URB",
    "RESIDENCIAL": "URB", "ASENTAMIENTO HUMANO": "HH", "PUEBLO JOVEN": "PJJ",
    "UNIDAD VECINAL": "U.V", "COOPERATIVA": "COV", "ZONA": "ZNA", "SECTOR": "SEC"
}

MAP_DEPARTAMENTOS = {
    "LIMA": "01", "CALLAO": "02", "AMAZONAS": "03", "ANCASH": "04",
    "APURIMAC": "05", "AREQUIPA": "06", "AYACUCHO": "07", "CAJAMARCA": "08",
    "CUSCO": "09", "HUANCAVELICA": "10", "HUANUCO": "11", "ICA": "12",
    "JUNIN": "13", "LA LIBERTAD": "14", "LAMBAYEQUE": "15", "LORETO": "16",
    "MADRE DE DIOS": "17", "MOQUEGUA": "18", "PASCO": "19", "PIURA": "20",
    "PUNO": "21", "SAN MARTIN": "22", "TACNA": "23", "TUMBES": "24", "UCAYALI": "25"
}

MAP_DISTRITOS_LIMA = {
    "LIMA": "001", "ANCON": "002", "ATE": "003", "BARRANCO": "004", "BREÑA": "005",
    "CARABAYLLO": "006", "COMAS": "007", "CHACLACAYO": "008", "CHORRILLOS": "009",
    "EL AGUSTINO": "010", "JESUS MARIA": "011", "LA MOLINA": "012", "LA VICTORIA": "013",
    "LINCE": "014", "LURIGANCHO": "015", "CHOSICA": "015", "LURIN": "016",
    "MAGDALENA DEL MAR": "017", "MIRAFLORES": "018", "PACHACAMAC": "019", "PUCUSANA": "020",
    "PUEBLO LIBRE": "021", "PUENTE PIEDRA": "022", "PUNTA NEGRA": "023", "PUNTA HERMOSA": "024",
    "RIMAC": "025", "SAN BARTOLO": "026", "SAN ISIDRO": "027", "INDEPENDENCIA": "028",
    "SAN JUAN DE MIRAFLORES": "029", "SAN LUIS": "030", "SAN MARTIN DE PORRES": "031",
    "SAN MIGUEL": "032", "SANTIAGO DE SURCO": "033", "SURCO": "033", "SURQUILLO": "034",
    "VILLA MARIA DEL TRIUNFO": "035", "SAN JUAN DE LURIGANCHO": "036", "SANTA ROSA": "037",
    "LOS OLIVOS": "038", "CIENEGUILLA": "039", "SAN BORJA": "040", "VILLA EL SALVADOR": "041",
    "SANTA ANITA": "042"
}

def get_clase_inmueble_cod(pisos):
    try:
        p = int(pisos)
        if p <= 4: return "1"
        if p <= 10: return "2"
        return "3"
    except: return "1"

def parse_direccion(d: str) -> Dict[str, str]:
    d_norm = norm_spaces(d)
    vias = find_all_vias(d_norm)
    admin = extract_admin_peru(d_norm)
    ext_val, ext_raw = extract_exterior(d_norm, choose_primary_vias(vias, d_norm))
    ref_abre, ref_raw, ref_full = extract_referencia(d_norm)
    interior = extract_interior(d_norm)
    ubic_tipo, ubic, ubic_raw = extract_ubicacion(d_norm)
    domicilio, _ = build_domicilio_and_extra(vias, d_norm, ext_val)
    
    raw_tipo_via = vias[0]["tipo"] if vias else "AVENIDA"
    tipo_inmueble_raw = "DEPARTAMENTO" if "DEPARTAMENTO" in upper(d_norm) else "CASA"
    
    distrito_nombre = upper(admin["DISTRITO"])
    
    return {
        "TIPO VIA 1": MAP_VIAS.get(upper(raw_tipo_via), "AV."),
        "DOMICILIO 1": default_sn(domicilio),
        "N. EXTERIOR": default_sn(limit(ext_val, EXT_MAX)),
        "N. INTERIOR": default_sn(limit(interior, INT_MAX)),
        "REFERENCIA": default_sn(limit(ref_abre, REF_MAX)),
        "UBICACION TIPO": MAP_UBICACION.get(upper(ubic_tipo), "") if ubic_tipo else "",
        "UBICACION 1": default_sn(limit(ubic, UBIC_MAX)),
        "DISTRITO": distrito_nombre,
        "DISTRITO_COD": MAP_DISTRITOS_LIMA.get(distrito_nombre, ""),
        "PROVINCIA": upper(admin["PROVINCIA"]),
        "PROVINCIA_COD": MAP_DEPARTAMENTOS.get(upper(admin["PROVINCIA"]), "01"),
        "DEPARTAMENTO": upper(admin["DEPARTAMENTO"]),
        "DEPARTAMENTO_COD": MAP_DEPARTAMENTOS.get(upper(admin["DEPARTAMENTO"]), "01"),
        "TIPO_INMUEBLE_TEXTO": tipo_inmueble_raw
    }
