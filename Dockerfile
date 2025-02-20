## -*- docker-image-name: "libmatch" -*-
FROM angr/angr
MAINTAINER edg@cs.ucsb.edu
USER root
RUN apt-get update && apt-get install -y sudo automake python3-pip python3-dev  build-essential libxml2-dev \
                        libxslt1-dev git libffi-dev cmake libreadline-dev libtool debootstrap debian-archive-keyring \
                        libglib2.0-dev libpixman-1-dev screen binutils-multiarch nasm vim libssl-dev 
USER angr
RUN bash -c "python3 -m venv /home/angr/venv"
RUN bash -c "echo source /home/angr/venv/bin/activate >> ~/.bashrc"

RUN git clone https://github.com/dhulliger/autoblob /home/angr/angr-dev/autoblob
RUN bash -c "source /home/angr/venv/bin/activate && cd /home/angr/angr-dev/autoblob && pip install -e ."
RUN bash -c "source /home/angr/venv/bin/activate && pip install angr"

COPY --chown=angr . /home/angr/angr-dev/libmatch
RUN bash -c "source /home/angr/venv/bin/activate && cd /home/angr/angr-dev/libmatch && pip install -e ."




WORKDIR /home/angr/angr-dev/libmatch


