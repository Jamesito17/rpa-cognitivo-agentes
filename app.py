import streamlit as st
import pytesseract
from PIL import Image, ImageOps, ImageFilter
import re
import os
import datetime
import pandas as pd
from io import BytesIO

if os.name == 'nt':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

RE_MONTO = re.compile(r'\d{1,3}(?:,\d{3})+\.\d{2}|\d+[.,]\d{2}(?!\d)')


def a_float(txt):
    """Convierte '163,56' / '1,234.50' / '90.00' a float. 0.0 si falla."""
    if txt in (None, "", "No detectado"):
        return 0.0
    t = str(txt).strip()
    t = t.replace(",", "") if ("," in t and "." in t) else t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return 0.0


# ==========================================
# AGENTE 1: VISIÓN
# ==========================================
class AgenteVisionOCR:
    def __init__(self):
        self.nombre = "Agente de Visión (OCR)"

    def _preprocesar(self, imagen):
        img = ImageOps.exif_transpose(imagen).convert('L')   # corrige rotación de fotos de celular
        w, h = img.size
        if w < 2000:                                          # agrandar imágenes pequeñas
            f = 2000 / w
            img = img.resize((int(w * f), int(h * f)), Image.LANCZOS)
        img = ImageOps.autocontrast(img, cutoff=1)            # suave, no destruye el trazo
        img = img.filter(ImageFilter.SHARPEN)
        return img

    def extraer_textos(self, imagen):
        """Devuelve una lista de textos (uno por modo PSM) para que el auditor elija el mejor."""
        try:
            img = self._preprocesar(imagen)
            textos = []
            for psm in (6, 4, 11):
                textos.append(pytesseract.image_to_string(img, config=f'--oem 3 --psm {psm}'))
            return textos
        except Exception as e:
            return [f"Error OCR: {e}"]


# ==========================================
# AGENTE 2: AUDITOR MATEMÁTICO
# ==========================================
class AgenteAuditorMatematico:
    def __init__(self):
        self.nombre = "Agente Lógico-Matemático"
        self.et_propina = [r'PROPINA']

        self.patrones_fecha = [
            r'EMISI[OÓ0]N[^\d]{0,25}(\d{2}[/-]\d{2}[/-]\d{4}|\d{4}[/-]\d{2}[/-]\d{2})',
            r'FECHA[^\d]{0,30}(\d{2}[/-]\d{2}[/-]\d{4}|\d{4}[/-]\d{2}[/-]\d{2})',
            r'(\d{2}[/-]\d{2}[/-]\d{4}|\d{4}[/-]\d{2}[/-]\d{2})',
        ]

        # Etiquetas tolerantes a errores de OCR (se evalúan LÍNEA por LÍNEA)
        self.et_subtotal = [r'OP\.?\s*GRAVAD', r'VALOR\s*VENTA', r'SUB\s*[\.\-]?\s*TOTAL']
        self.et_igv = [r'(?<![A-Za-z])[I1Il|]\s*\.?\s*[GC6]\s*\.?\s*[VY](?![A-Za-z])']
        self.et_total = [r'[Il1|]MPORTE\s*TOT', r'TOTAL\s*A\s*PAGAR',
                         r'(?<!SUB)(?<!SUB )(?<!SUB\.)(?<!SUB-)TOTAL(?!\s*(?:DE|VENTAS))']

    # ---------- utilidades ----------
    def _buscar_ruc(self, texto):
        m = re.search(r'R\.?\s*U\.?\s*C\.?[^\d\n]{0,15}(\d{11})', texto, re.I)
        if m:
            return m.group(1)
        m = re.search(r'(?<!\d)((?:10|15|16|17|20)\d{9})(?!\d)', texto)
        return m.group(1) if m else "No detectado"

    def _buscar_fecha(self, texto):
        for p in self.patrones_fecha:
            m = re.search(p, texto, re.I)
            if m:
                return m.group(1)
        return "No detectado"

    def _por_etiqueta(self, lineas, patrones):
        for patron in patrones:
            for i, linea in enumerate(lineas):
                if re.search(patron, linea, re.I):
                    montos = RE_MONTO.findall(linea)
                    if not montos and i + 1 < len(lineas):      # monto en la línea siguiente
                        montos = RE_MONTO.findall(lineas[i + 1])
                    if montos:
                        return a_float(montos[-1])              # el monto es lo último de la línea
        return 0.0

    def _buscar_terna(self, texto):
        """Busca (total, subtotal, igv) coherentes con IGV = 18% entre TODOS los montos del texto."""
        vals = sorted({round(a_float(m), 2) for m in RE_MONTO.findall(texto) if a_float(m) > 0})
        mejor = None
        for igv in vals:
            for sub in vals:
                if sub <= igv or abs(sub * 0.18 - igv) > 0.03:
                    continue
                base = round(sub + igv, 2)
                for t in vals:
                    if t < base - 0.02:
                        continue
                    extra = round(t - base, 2)
                    # total exacto, o diferencia explicada por otro monto (ej. propina)
                    if extra <= 0.02 or (extra <= base * 0.25 and any(abs(extra - v) <= 0.02 for v in vals)):
                        if mejor is None or t > mejor[0]:
                            mejor = (t, sub, igv)
        return mejor

    # ---------- análisis de un texto ----------
    def _analizar(self, texto):
        lineas = [l for l in texto.splitlines() if l.strip()]
        datos = {"RUC": self._buscar_ruc(texto), "Fecha": self._buscar_fecha(texto)}

        sub_l = self._por_etiqueta(lineas, self.et_subtotal)
        igv_l = self._por_etiqueta(lineas, self.et_igv)
        tot_l = self._por_etiqueta(lineas, self.et_total)
        terna = self._buscar_terna(texto)

        propina = self._por_etiqueta(lineas, self.et_propina)

        directo = (sub_l and igv_l and tot_l
                   and abs(sub_l * 0.18 - igv_l) <= 0.03
                   and abs(sub_l + igv_l + propina - tot_l) <= 0.02)

        if directo:
            total, sub, igv = tot_l, sub_l, igv_l
            datos["Metodología"] = "🤖 Extracción OCR Directa"
            datos["Estado"] = "Aprobado"
            puntaje = 10
        elif terna:
            total, sub, igv = terna
            datos["Metodología"] = "✅ Validación cruzada (IGV 18%)"
            datos["Estado"] = "Aprobado"
            puntaje = 8
        elif tot_l and not igv_l:
            sub = round(tot_l / 1.18, 2)
            igv = round(tot_l - sub, 2)
            total = tot_l
            datos["Metodología"] = "⚠️ Triangulación (IGV no leído)"
            datos["Estado"] = "🚨 Alerta HITL"
            puntaje = 3
        else:
            total, sub, igv = tot_l, sub_l, igv_l
            datos["Metodología"] = "⚠️ Montos inconsistentes"
            datos["Estado"] = "🚨 Alerta HITL"
            puntaje = 1 if total else 0

        fmt = lambda v: f"{v:.2f}" if v else "No detectado"
        datos["Subtotal"], datos["IGV"], datos["Total"] = fmt(sub), fmt(igv), fmt(total)

        if datos["RUC"] != "No detectado":
            puntaje += 2
        if datos["Fecha"] != "No detectado":
            puntaje += 1
        if datos["Total"] == "No detectado" or datos["RUC"] == "No detectado":
            datos["Estado"] = "🚨 Alerta HITL"
        datos["Texto OCR"] = texto
        return puntaje, datos

    def procesar_datos(self, textos):
        """Analiza cada pasada de OCR y se queda con la más coherente."""
        if isinstance(textos, str):
            textos = [textos]
        resultados = [self._analizar(t) for t in textos]
        return max(resultados, key=lambda r: r[0])[1]


# ==========================================
# AGENTE 3: CUMPLIMIENTO
# ==========================================
class AgenteAnalistaCumplimiento:
    def __init__(self):
        self.nombre = "Agente de Cumplimiento Tributario"

    def evaluar_riesgo(self, datos):
        obs = []
        if datos["Total"] != "No detectado" and a_float(datos["Total"]) >= 2000:
            obs.append("⚠️ Requiere Bancarización")

        fecha = datos.get("Fecha", "")
        if fecha != "No detectado" and str(datetime.date.today().year) not in fecha:
            obs.append("📅 Revisar periodo fiscal")

        if datos.get("Estado") != "Aprobado":
            obs.append("🔎 Datos no verificados")

        datos["Alerta Tributaria"] = " | ".join(obs) if obs else "✅ Conforme (Sin riesgo)"
        return datos


def convertir_df_a_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Reporte_Facturas')
    return output.getvalue()


# ==========================================
# INTERFAZ
# ==========================================
def main():
    st.set_page_config(page_title="RPA Multiagente UNFV", page_icon="🤖", layout="wide")
    st.title("🧠 Motor RPA Cognitivo Multiagente")
    st.markdown("**Universidad Nacional Federico Villarreal** - Despliegue en la Nube")
    st.markdown("---")

    agente_vision = AgenteVisionOCR()
    agente_auditor = AgenteAuditorMatematico()
    agente_cumplimiento = AgenteAnalistaCumplimiento()

    archivos = st.file_uploader("Sube tus facturas (JPG, JPEG, PNG)",
                                type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

    if archivos:
        st.info(f"Se han cargado {len(archivos)} documento(s).")

        if st.button("▶️ Ejecutar Procesamiento por Lotes", type="primary"):
            resultados, barra = [], st.progress(0)

            for i, archivo in enumerate(archivos):
                with st.spinner(f"Procesando {archivo.name}..."):
                    imagen = Image.open(archivo)
                    textos = agente_vision.extraer_textos(imagen)
                    datos = agente_auditor.procesar_datos(textos)
                    datos = agente_cumplimiento.evaluar_riesgo(datos)
                    datos["Archivo Origen"] = archivo.name
                    resultados.append(datos)
                barra.progress((i + 1) / len(archivos))

            st.success("✅ Flujo Multiagente por lotes completado.")
            st.markdown("### 📊 Consolidado de Extracción")

            df = pd.DataFrame(resultados)
            orden = ["Archivo Origen", "RUC", "Fecha", "Subtotal", "IGV", "Total",
                     "Metodología", "Alerta Tributaria", "Estado"]
            st.dataframe(df[orden], use_container_width=True)

            n_alertas = (df["Estado"] != "Aprobado").sum()
            if n_alertas:
                st.error(f"⚠️ {n_alertas} documento(s) requieren revisión manual (HITL).")

            st.markdown("---")
            st.markdown("### 💾 Exportar Resultados")
            st.download_button("📥 Descargar Reporte en Excel",
                               data=convertir_df_a_excel(df[orden]),
                               file_name="Reporte_Facturas_RPA_Agentes.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

            with st.expander("🧾 Texto OCR leído (para depurar)"):
                for r in resultados:
                    st.markdown(f"**{r['Archivo Origen']}**")
                    st.code(r["Texto OCR"])

            with st.expander("🔍 Ver Documentos Originales Procesados"):
                cols = st.columns(3)
                for i, archivo in enumerate(archivos):
                    with cols[i % 3]:
                        st.image(Image.open(archivo), caption=archivo.name, use_container_width=True)


if __name__ == "__main__":
    main()
