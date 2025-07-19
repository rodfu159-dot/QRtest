import streamlit as st
import qrcode
from PIL import Image, ImageEnhance
import serial
import serial.tools.list_ports
import time
import io
from datetime import datetime
import pandas as pd # Usaremos pandas para manejar el historial y exportar a CSV

# --- Configuración del Puerto COM (¡Ajusta esto!) ---
# Streamlit se ejecuta en un entorno web, la conexión a puertos COM locales es compleja.
# Para despliegues reales, necesitarías un servicio de backend que maneje la comunicación serial.
# Para pruebas locales, asegúrate de que el puerto COM esté disponible en la máquina donde corres Streamlit.
# Puedes hacer esta configuración configurable en la interfaz de Streamlit.

# Usamos st.session_state para mantener el estado entre las ejecuciones de Streamlit
if 'serial_port' not in st.session_state:
    st.session_state.serial_port = None
if 'reconnect_attempts' not in st.session_state:
    st.session_state.reconnect_attempts = 0
if 'historial_qr' not in st.session_state:
    st.session_state.historial_qr = pd.DataFrame(columns=["Fecha/Hora", "Contenido QR"])

# --- Funciones de Comunicación Serial Adaptadas para Streamlit ---

@st.cache_data
def listar_puertos_com():
    """Lista los puertos COM disponibles."""
    # En un entorno Streamlit, esta función se ejecutará en el servidor.
    # Los puertos listados serán los del servidor.
    ports = serial.tools.list_ports.comports()
    return [p.device for p in ports]

def iniciar_lectura_com(com_port, baud_rate):
    """Intenta iniciar la lectura del puerto COM."""
    if st.session_state.serial_port is not None and st.session_state.serial_port.is_open:
        st.info(f"Lector: Ya está CONECTADO a {com_port}")
        return

    try:
        ser = serial.Serial(
            port=com_port,
            baudrate=baud_rate,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=0.1 # Timeout bajo para no bloquear Streamlit
        )
        ser.flushInput()
        ser.flushOutput()
        st.session_state.serial_port = ser
        st.session_state.reconnect_attempts = 0
        st.success(f"Lector: CONECTADO a {com_port}. Escaneando...")
        return True
    except serial.SerialException as e:
        st.error(f"No se pudo conectar al puerto {com_port}: {e}. Intenta con otro puerto o verifica la configuración.")
        st.session_state.serial_port = None
        return False

def detener_lectura_com():
    """Detiene la lectura del puerto COM y cierra el puerto."""
    if st.session_state.serial_port is not None and st.session_state.serial_port.is_open:
        st.session_state.serial_port.close()
        st.session_state.serial_port = None
        st.success("Lector: DESCONECTADO.")
    else:
        st.info("Lector: No estaba activo para desconectar.")

def leer_datos_com_streamlit():
    """
    Lee datos del puerto COM de forma periódica en Streamlit.
    Esta función necesita ser llamada repetidamente por Streamlit para simular un hilo de lectura.
    """
    if st.session_state.serial_port and st.session_state.serial_port.is_open:
        try:
            # Lee todo lo disponible en el buffer hasta un salto de línea o timeout
            linea_bytes = st.session_state.serial_port.readline()
            if linea_bytes:
                linea = linea_bytes.decode('utf-8', errors='ignore').strip()
                if linea:
                    st.toast(f"QR escaneado: {linea}", icon="✅")
                    actualizar_historial_qr(linea)
                    # Forzar una re-ejecución si necesitas actualizar la UI inmediatamente
                    # Esto puede ser intensivo, úsalo con precaución
                    # st.rerun() 
            else:
                # Si no hay datos, puedes esperar un poco para evitar un ciclo muy apretado
                time.sleep(0.01) # Pequeña pausa
        except serial.SerialException as e:
            st.error(f"Error de lectura en el puerto serie: {e}. Reconectando...")
            st.session_state.serial_port.close()
            st.session_state.serial_port = None
            # Podrías agregar aquí lógica de reconexión si lo deseas, pero en Streamlit
            # es más fácil que el usuario haga clic en "Conectar" de nuevo.
        except Exception as e:
            st.error(f"Ocurrió un error inesperado al leer: {e}")
            detener_lectura_com() # Detener para evitar más errores

def actualizar_historial_qr(texto_qr):
    """Actualiza el historial de QR escaneados."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    nuevo_registro = pd.DataFrame([{"Fecha/Hora": timestamp, "Contenido QR": texto_qr}])
    st.session_state.historial_qr = pd.concat([nuevo_registro, st.session_state.historial_qr]).reset_index(drop=True)
    # Limitar el historial a los últimos 100 elementos
    if len(st.session_state.historial_qr) > 100:
        st.session_state.historial_qr = st.session_state.historial_qr.head(100)


# --- Funciones del Generador de QR ---

def generar_qr(texto):
    """Genera un código QR y devuelve la imagen en bytes."""
    if not texto:
        st.warning("Advertencia: Introduce texto o una URL para generar el QR.")
        return None

    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(texto)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
        img_resized = img.resize((250, 250), Image.Resampling.LANCZOS)
        enhancer = ImageEnhance.Contrast(img_resized)
        img_final = enhancer.enhance(1.2)

        # Guardar la imagen en un buffer de bytes
        img_byte_arr = io.BytesIO()
        img_final.save(img_byte_arr, format='PNG')
        return img_byte_arr.getvalue()

    except Exception as e:
        st.error(f"Error al generar QR: {e}")
        return None

def limpiar_historial():
    """Limpia todo el historial de QR escaneados."""
    st.session_state.historial_qr = pd.DataFrame(columns=["Fecha/Hora", "Contenido QR"])
    st.success("Historial limpiado.")

# --- Interfaz de Streamlit ---

st.set_page_config(
    page_title="App de QR (Generador y Lector)",
    page_icon="🔍",
    layout="centered"
)

st.title("Aplicación de QR (Generador y Lector)")

# Pestañas (Columnas o Expander para simular pestañas en Streamlit simple)
tab1, tab2 = st.tabs(["Generador de QR", "Lector de QR"])

with tab1:
    st.header("Generador de Códigos QR")
    
    st.write("Introduce el texto o la URL para generar tu código QR.")
    texto_generador = st.text_input("Contenido del QR", key="qr_input", placeholder="Ej: https://www.google.com o Mi texto")

    if st.button("Generar QR", type="primary"):
        qr_image_bytes = generar_qr(texto_generador)
        if qr_image_bytes:
            st.image(qr_image_bytes, caption="Código QR Generado", use_container_width=False, width=250)
            st.download_button(
                label="Descargar QR",
                data=qr_image_bytes,
                file_name="qrcode.png",
                mime="image/png"
            )
            st.success("Código QR generado y mostrado.")

with tab2:
    st.header("Lector de Códigos QR (Puerto COM)")

    st.warning("""
    **Importante:** La funcionalidad de lector de puerto COM solo funcionará si Streamlit se ejecuta en una máquina con acceso físico al lector QR y el puerto COM especificado. Para despliegues en la nube, la comunicación serial directa no es posible; se requeriría un servicio backend separado.
    """)

    # Configuración de puerto COM en la UI
    puertos_disponibles = listar_puertos_com()
    selected_com_port = st.selectbox(
        "Selecciona el Puerto COM",
        options=puertos_disponibles if puertos_disponibles else ["No se encontraron puertos COM"],
        disabled=(len(puertos_disponibles) == 0)
    )
    selected_baud_rate = st.number_input(
        "Baud Rate",
        min_value=300,
        max_value=115200,
        value=9600,
        step=100
    )

    col1_lector, col2_lector = st.columns(2)
    with col1_lector:
        if st.button("Conectar Lector", help="Inicia la conexión y lectura del puerto COM."):
            if selected_com_port and selected_com_port != "No se encontraron puertos COM":
                iniciar_lectura_com(selected_com_port, selected_baud_rate)
            else:
                st.error("Por favor, selecciona un puerto COM válido.")
    with col2_lector:
        if st.button("Desconectar Lector", help="Detiene la conexión con el puerto COM."):
            detener_lectura_com()

    st.markdown("---")
    st.subheader("Último QR Escaneado:")
    # Muestra el último elemento del historial, si existe
    if not st.session_state.historial_qr.empty:
        st.metric(label="Contenido", value=st.session_state.historial_qr.iloc[0]["Contenido QR"])
        st.caption(f"Fecha/Hora: {st.session_state.historial_qr.iloc[0]['Fecha/Hora']}")
    else:
        st.info("Esperando escaneo...")

    st.markdown("---")
    st.subheader("Historial de Escaneos")
    
    # Mostrar el historial en una tabla
    st.dataframe(st.session_state.historial_qr, use_container_width=True, hide_index=True)

    col_hist1, col_hist2 = st.columns(2)
    with col_hist1:
        if st.button("Exportar Historial a CSV", type="secondary", help="Descarga el historial actual como un archivo CSV."):
            if not st.session_state.historial_qr.empty:
                csv_data = st.session_state.historial_qr.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Descargar CSV",
                    data=csv_data,
                    file_name="historial_qr_scans.csv",
                    mime="text/csv",
                    key="download_csv_button" # Necesario para evitar errores si hay múltiples botones de descarga
                )
            else:
                st.warning("No hay datos en el historial para exportar.")
    with col_hist2:
        if st.button("Limpiar Historial", help="Elimina todos los registros del historial."):
            limpiar_historial()

    # Este es un truco para mantener la lectura activa sin hilos de forma explícita.
    # Streamlit re-ejecuta el script de arriba a abajo.
    # Con cada interacción del usuario (o cada vez que se actualiza la página),
    # intentaremos leer del puerto.
    if st.session_state.serial_port and st.session_state.serial_port.is_open:
        leer_datos_com_streamlit()
        # Si quieres una "lectura en vivo" más persistente, necesitarías:
        # 1. Un bucle `while True` en `leer_datos_com_streamlit`
        # 2. Algo para prevenir que Streamlit se bloquee (e.g., usar `st.empty` y actualizarlo,
        #    o una llamada a `st.rerun()` condicionalmente si hay datos, lo que es muy costoso)
        # 3. La forma más robusta sería un backend separado (FastAPI, Flask) que maneje el serial
        #    y exponga un endpoint que Streamlit consulte periódicamente.

st.sidebar.markdown("## Información del Lector")
st.sidebar.write("Estado actual:")
if st.session_state.serial_port and st.session_state.serial_port.is_open:
    st.sidebar.success(f"CONECTADO a {selected_com_port}")
else:
    st.sidebar.error("DESCONECTADO")

st.sidebar.markdown("""
---
**Acerca de esta app:**
Esta aplicación permite generar códigos QR y, experimentalmente, leer códigos QR desde un puerto COM.

**Consideraciones importantes para el lector de QR:**
* Asegúrate de que el **Baud Rate** y la configuración de tu lector de QR coincidan con los valores aquí.
* La comunicación con el puerto COM es local a la máquina donde se ejecuta Streamlit. Si despliegas esta aplicación en la nube, la función de lector no funcionará directamente.
* Esta implementación para Streamlit realiza una lectura "bajo demanda" o cada vez que la aplicación se re-ejecuta (por una interacción o `st.rerun()`). No es un hilo de lectura continuo en segundo plano como en Tkinter.
""")
