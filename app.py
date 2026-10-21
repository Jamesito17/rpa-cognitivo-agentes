import streamlit as st
import pytesseract
from PIL import Image
import re
import os
import pandas as pd
from io import BytesIO

# ==========================================
# CONFIGURACIÓN DINÁMICA DE TESSERACT
# ==========================================
if os.name == 'nt':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# ==========================================
# CUMPLIENDO REGLA 4: ARQUITECTURA MULTIAGENTE (POO)
# ==========================================

class AgenteVisionOCR:
    """Agente 1: Especialista en visión computacional y extracción bruta"""
    def __init__(self):
        self.nombre = "Agente de Visión (OCR)"

    def extraer_texto(self, imagen):
        try:
            return pytesseract.image_to_string(imagen)
        except Exception as e:
            return f"Error OCR: {e}"

class AgenteAuditorMatematico:
    """Agente 2: Especialista en reglas de negocio, RegEx y triangulación de impuestos"""
    def __init__(self):
        self.nombre = "Agente Lógico-Matemático"
        self.patrones_ruc = [r'RUC[^\d]*(\d{11})']
        self.patrones_fecha = [
            r'EMISI(?:O|Ó|0)N.{0,20}?(\d{4}[/-]\d{2}[/-]\d{2}|\d{2}[/-]\d{2}[/-]\d{4})',
            r'FECHA.{0,30}?(\d{4}[/-]\d{2}[/-]\d{2}|\d{2}[/-]\d{2}[/-]\d{4})',
            r'(\d{4}[/-]\d{2}[/-]\d{2}|\d{2}[/-]\d{2}[/-]\d{4})'
        ]
        self.patrones_subtotal = [r'OP\.\s*GRAVADAS.{0,20}?(\d+[\.,]\d{2})', r'SUB[\.\s]?TOTAL.{0,20}?(\d+[\.,]\d{2})']
        self.patrones_igv = [r'IGV.{0,20}?(\d+[\.,]\d{2})']
        self.patrones_total = [
            r'TOTAL A PAGAR.{0,20}?(\d+[\.,]\d{2})',
            r'IMPORTE TOTAL.{0,50}?(?:[S5s\$]\s*[/\|]\s*)?(\d+[\.,]\d{2})',
            r'TOTAL.{0,20}?(\d+[\.,]\d{2})'
        ]

    def _buscar_regex(self, texto, patrones):
        for patron in patrones:
            match = re.search(patron, texto, re.IGNORECASE | re.DOTALL)
            if match: return match.group(1).strip()
        return "No detectado"

    def procesar_datos(self, texto_bruto):
        datos = {
            "RUC": self._buscar_regex(texto_bruto, self.patrones_ruc),
            "Fecha": self._buscar_regex(texto_bruto, self.patrones_fecha),
            "Subtotal": self._buscar_regex(texto_bruto, self.patrones_subtotal),
            "IGV": self._buscar_regex(texto_bruto, self.patrones_igv),
            "Total": self._buscar_regex(texto_bruto, self.patrones_total)
        }
        return self._reconciliacion_matematica(datos)

    def _reconciliacion_matematica(self, datos):
        def a_numero(texto):
            try:
                if texto == "No detectado": return 0.0
                return float(texto.replace(',', '.'))
            except: return 0.0

        total_num = a_numero(datos["Total"])
        subtotal_num = a_numero(datos["Subtotal"])
        igv_num = a_numero(datos["IGV"])

        if total_num > 0 and (igv_num == 0 or igv_num >= total_num or subtotal_num == 0):
            subtotal_calc = round(total_num / 1.18, 2)
            igv_calc = round(total_num - subtotal_calc, 2)
            datos["Subtotal"] = f"{subtotal_calc:.2f}"
            datos["IGV"] = f"{igv_calc:.2f}"
            datos["Metodología"] = "🤖 Triangulación Matemática"
            datos["Estado"] = "Aprobado"
        else:
            datos["Metodología"] = "🤖 Extracción OCR Directa"
            datos["Estado"] = "Aprobado"
        
        if datos["Total"] == "No detectado" or datos["RUC"] == "No detectado":
            datos["Estado"] = "🚨 Alerta HITL"
            datos["Metodología"] = "Fallo de Agentes"

        return datos
class AgenteAnalistaCumplimiento:
    """Agente 3: Especialista en normativas tributarias y prevención de riesgos fiscales"""
    def __init__(self):
        self.nombre = "Agente de Cumplimiento Tributario"

    def evaluar_riesgo(self, datos):
        observaciones = []
        
        # Regla 1: Ley de Bancarización en Perú (Montos mayores a S/ 2000)
        try:
            total_float = float(datos.get("Total", "0").replace(',', '.'))
            if total_float >= 2000:
                observaciones.append("⚠️ Requiere Bancarización")
        except:
            pass

        # Regla 2: Antigüedad del documento
        fecha = datos.get("Fecha", "")
        if fecha != "No detectado" and "2026" not in fecha:
            # Si tiene un año distinto al actual 
            observaciones.append("📅 Revisar periodo fiscal")

        # Asignar la alerta final al diccionario
        if observaciones:
            datos["Alerta Tributaria"] = " | ".join(observaciones)
        else:
            datos["Alerta Tributaria"] = "✅ Conforme (Sin riesgo)"

        return datos        

# ==========================================
# FUNCIONES AUXILIARES PARA EXPORTACIÓN
# ==========================================
def convertir_df_a_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Reporte_Facturas')
    procesado_data = output.getvalue()
    return procesado_data

# ==========================================
# INTERFAZ WEB (FRONTEND STREAMLIT)
# ==========================================

def main():
    st.set_page_config(page_title="RPA Multiagente UNFV", page_icon="🤖", layout="wide")
    
    st.title("🧠 Motor RPA Cognitivo Multiagente")
    st.markdown("**Universidad Nacional Federico Villarreal** - Despliegue en la Nube")
    st.markdown("---")

    agente_vision = AgenteVisionOCR()
    agente_auditor = AgenteAuditorMatematico()
    agente_cumplimiento = AgenteAnalistaCumplimiento()

    #CARGA MASIVA DE ARCHIVOS (accept_multiple_files=True)
    archivos_subidos = st.file_uploader("Sube tus facturas (JPG, JPEG, PNG)", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

    if archivos_subidos:
        st.info(f"Se han cargado {len(archivos_subidos)} documento(s).")
        
        if st.button("▶️ Ejecutar Procesamiento por Lotes", type="primary"):
            
            # Lista para consolidar los resultados de todas las facturas
            resultados_lote = []
            
            # Barra de progreso
            barra_progreso = st.progress(0)
            
            for i, archivo in enumerate(archivos_subidos):
                imagen = Image.open(archivo)
                nombre_archivo = archivo.name
                
                with st.spinner(f"Procesando {nombre_archivo}..."):
                    # Flujo Multiagente por cada archivo
                    texto_bruto = agente_vision.extraer_texto(imagen)
                    datos_estructurados = agente_auditor.procesar_datos(texto_bruto)
                    
                    # Añadimos el nombre del archivo al diccionario
                    datos_estructurados["Archivo Origen"] = nombre_archivo
                    resultados_lote.append(datos_estructurados)
                
                # Actualizar barra de progreso
                barra_progreso.progress((i + 1) / len(archivos_subidos))
            
            st.success("✅ Flujo Multiagente por lotes completado.")
            
            st.markdown("### 📊 Consolidado de Extracción")
            
            # Crear un Dataframe de Pandas con los resultados
            df_resultados = pd.DataFrame(resultados_lote)
            
            # Reordenar las columnas para una mejor presentación
            columnas_orden = ["Archivo Origen", "RUC", "Fecha", "Subtotal", "IGV", "Total", "Metodología", "Estado"]
            df_resultados = df_resultados[columnas_orden]
            
            # Mostrar tabla interactiva en Streamlit
            st.dataframe(df_resultados, use_container_width=True)
            
            # Contar alertas HITL
            alertas = df_resultados[df_resultados['Estado'] == '🚨 Alerta HITL'].shape[0]
            if alertas > 0:
                st.error(f"⚠️ Se detectaron {alertas} documento(s) con alertas HITL. Por favor, revise los documentos marcados en rojo en la tabla de exportación.")
            
            # Botón de Descarga Excel
            st.markdown("---")
            st.markdown("### 💾 Exportar Resultados")
            excel_data = convertir_df_a_excel(df_resultados)
            
            st.download_button(
                label="📥 Descargar Reporte en Excel",
                data=excel_data,
                file_name="Reporte_Facturas_RPA_Agentes.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
            # Mostrar imágenes originales para revisión (Opcional, útil para HITL)
            with st.expander("🔍 Ver Documentos Originales Procesados"):
                cols = st.columns(3)
                for i, archivo in enumerate(archivos_subidos):
                    with cols[i % 3]:
                        img = Image.open(archivo)
                        st.image(img, caption=archivo.name, use_container_width=True) # Corregida la advertencia

if __name__ == "__main__":
    main()
