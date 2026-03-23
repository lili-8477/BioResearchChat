FROM r-base:4.3

RUN apt-get update && apt-get install -y --no-install-recommends \
    libcurl4-openssl-dev libssl-dev libxml2-dev libfontconfig1-dev \
    libharfbuzz-dev libfribidi-dev libfreetype6-dev libpng-dev \
    libtiff5-dev libjpeg-dev && \
    rm -rf /var/lib/apt/lists/*

RUN R -e "install.packages('BiocManager', repos='https://cran.r-project.org')" && \
    R -e "BiocManager::install(c('DESeq2', 'edgeR', 'EnhancedVolcano'), ask=FALSE)" && \
    R -e "install.packages(c('ggplot2', 'pheatmap', 'tidyverse'), repos='https://cran.r-project.org')"

WORKDIR /workspace
