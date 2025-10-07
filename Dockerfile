# Usamos una imagen base oficial de Python.
FROM python:3.9-slim

# Establecemos el directorio de trabajo dentro del contenedor.
WORKDIR /app

# Copiamos TODOS los archivos del directorio actual al directorio de trabajo del contenedor.
# El '.' significa "el directorio actual", por lo que copiará main.py, config.py, etc.
COPY . .

# Cuando el contenedor se inicie, ejecutará el nuevo script principal.
# Usamos "unbuffered" (-u) para que los print() aparezcan inmediatamente.
CMD ["python3", "-u", "main.py"]