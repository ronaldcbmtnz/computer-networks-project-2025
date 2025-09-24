# Usamos una imagen base oficial de Python.
FROM python:3.9-slim

# Establecemos el directorio de trabajo dentro del contenedor.
WORKDIR /app

# Copiamos el script de nuestra aplicación al directorio de trabajo del contenedor.
COPY link_chat.py .

# Cuando el contenedor se inicie, ejecutará este comando.
# Usamos "unbuffered" (-u) para que los print() aparezcan inmediatamente.
CMD ["python3", "-u", "link_chat.py"]