import json
import os
import re
import io
import zipfile
import base64
import unicodedata
from typing import Any, Dict, List, Optional, Tuple
import fitz
import functions_framework
import requests
import pandas as pd
from flask import send_file
import address_parser

MACRO_COLUMNS = [
    'PRESTAMO', 'TIPO DE INMUEBLE', 'VALOR DEL BIEN', 'MONEDA', 'IMPORTE', 'COL_F', 
    'DIRECCION', 'DIRECCION1', 'EXTERIOR', 'INTERIOR', 'REFERENCIA', 'COL_L',
    'UBICACION', 'UBICACION1', 'MUNICIPIO', 'DIST_COD', 'COL_Q', 'PROV_COD',
    'COL_S', 'DEPT_COD', 'CLASE', 'PISOS', 'SOTANOS', 'AÑO'
]

def extract_full_data(pdf_bytes, filename):
    try:
        with fitz.open(stream=pdf_bytes, filetype='pdf') as doc:
            text = ''
            for page in doc:
                text += page.get_text()
            p = address_parser.parse_direccion(text)
            row = [''] * 24
            prestamo_match = re.search(r'\d{20}', filename)
            row[0] = prestamo_match.group(0) if prestamo_match else ''
            row[1] = p.get('TIPO_MASIVO_COD', 'C')
            row[6] = p.get('TIPO VIA 1', 'AV.')
            row[7] = p.get('DOMICILIO 1', 'SN')
            row[8] = p.get('N. EXTERIOR', 'SN')
            row[9] = p.get('N. INTERIOR', 'SN')
            row[10] = p.get('REFERENCIA', 'SN')
            row[12] = p.get('UBICACION TIPO', 'URB')
            row[13] = p.get('UBICACION 1', 'SN')
            row[14] = p.get('DISTRITO', 'LIMA')
            row[15] = p.get('DISTRITO_COD', '001')
            row[17] = p.get('PROVINCIA_COD', '01')
            row[19] = p.get('DEPARTAMENTO_COD', '01')
            row[20] = '1'
            return row
    except:
        return ['ERROR'] * 24

@functions_framework.http
def procesar_tasaciones(request):
    cors = {'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'POST', 'Access-Control-Allow-Headers': 'Content-Type'}
    if request.method == 'OPTIONS': return ('', 204, cors)

    raw_data = request.get_data()
    
    # DETECCIÓN DE FORMATO POWER AUTOMATE (Base64 wrapper)
    try:
        if request.is_json:
            payload = request.get_json()
            if isinstance(payload, dict) and '' in payload:
                raw_data = base64.b64decode(payload[''])
    except:
        pass

    # Si es un ZIP (ya sea crudo o extraído del JSON)
    if raw_data.startswith(b'PK'):
        all_rows = []
        try:
            with zipfile.ZipFile(io.BytesIO(raw_data)) as z:
                for filename in z.namelist():
                    if filename.lower().endswith('.pdf'):
                        with z.open(filename) as f:
                            all_rows.append(extract_full_data(f.read(), filename))
            
            if not all_rows: return ('No se encontraron PDFs validos', 400, cors)

            df = pd.DataFrame(all_rows, columns=MACRO_COLUMNS)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='MASIVO', index=False)
            output.seek(0)
            return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name='Para_Macro.xlsx')
        except Exception as e:
            return (f'Error ZIP: {str(e)}', 500, cors)

    # Solo si NO es un ZIP, responder con el JSON para Google Sheets
    return json.dumps({'status': 'error', 'mensaje': 'Envíe un archivo ZIP válido'}), 400, cors
