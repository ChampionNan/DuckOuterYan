FROM debian:11.0 as duckdb14

RUN apt-get clean && apt-get update && \
    apt-get install -y sudo ca-certificates lsb-release wget

RUN wget https://apache.jfrog.io/artifactory/arrow/debian/apache-arrow-apt-source-latest-bullseye.deb && \
    apt install -y -V ./apache-arrow-apt-source-latest-bullseye.deb && \
    rm apache-arrow-apt-source-latest-bullseye.deb

RUN apt-get update

RUN apt-get install -y -V \
    libarrow-dev \
    libarrow-glib-dev \
    libarrow-dataset-dev \
    libarrow-dataset-glib-dev \
    libarrow-acero-dev \
    libarrow-flight-dev \
    libarrow-flight-glib-dev \
    libarrow-flight-sql-dev \
    libarrow-flight-sql-glib-dev \
    libgandiva-dev \
    libgandiva-glib-dev \
    libparquet-dev \
    libparquet-glib-dev

RUN apt-get update && apt-get install -y cmake g++ vim git tmux ninja-build libssl-dev libcurl4-openssl-dev

RUN cmake --version && which cmake && whereis cmake && which g++ && which c++

CMD [ "/bin/bash" ]

