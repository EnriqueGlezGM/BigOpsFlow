# Spark oficial + Python 3.13 con micromamba (sin ToS de Anaconda)
FROM spark:4.0.1

USER root
ARG MAMBA_ROOT_PREFIX=/opt/conda
ENV MAMBA_ROOT_PREFIX=${MAMBA_ROOT_PREFIX}
SHELL ["/bin/bash","-lc"]

# Instala micromamba binaria
RUN apt-get update && apt-get install -y curl bzip2 ca-certificates && rm -rf /var/lib/apt/lists/* \
 && curl -Ls https://micro.mamba.pm/api/micromamba/linux-$(uname -m)/latest | tar -xvj -C /usr/local/bin --strip-components=1 bin/micromamba

# Crea el entorno en /opt/conda e instala Python 3.13 + deps
RUN micromamba install -y -p ${MAMBA_ROOT_PREFIX} -c conda-forge \
    python=3.13 pyspark==4.0.1 pandas pyarrow \
 && micromamba clean -ay

# Exporta rutas para PySpark
ENV PATH=${MAMBA_ROOT_PREFIX}/bin:$PATH \
    PYSPARK_PYTHON=${MAMBA_ROOT_PREFIX}/bin/python \
    PYSPARK_DRIVER_PYTHON=${MAMBA_ROOT_PREFIX}/bin/python

# Vuelve al usuario por defecto de la imagen de Spark
USER 185