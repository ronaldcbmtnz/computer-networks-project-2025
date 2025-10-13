# Usamos una imagen base oficial de Python.
FROM python:3.9-slim

# 1. Instalar las dependencias del sistema operativo (Tcl/Tk)
# RUN actualiza la lista de paquetes y luego instala tk-dev
RUN apt-get update && apt-get install -y tk-dev

# Establecemos el directorio de trabajo dentro del contenedor.
WORKDIR /app

# 2. Copiar PRIMERO el archivo de requerimientos.
COPY requirements.txt .

# 3. Instalar las dependencias de Python.
RUN pip install -r requirements.txt

# 4. Copiar el resto de los archivos del proyecto.
COPY . .

# Establecemos la variable de entorno para que main.py sepa que debe ejecutarse en modo CLI.
ENV RUN_MODE CLI

# Cuando el contenedor se inicie, ejecutará el nuevo script principal.
CMD ["python3", "-u", "main.py"]