# syntax=docker/dockerfile:1
ARG PYVER=3.11.9
ARG ALPTAG=3.21@sha256:e323a465c03a31ad04374fc7239144d0fd4e2b92da6e3e0655580476d3a84621
FROM python:${PYVER}-alpine${ALPTAG} as builder

# Add the community repo for access to patchelf binary package
ARG ALPTAG
RUN echo "https://dl-cdn.alpinelinux.org/alpine/v${ALPTAG}/community/" >> /etc/apk/repositories
RUN apk --no-cache upgrade && apk --no-cache add build-base tar musl-utils openssl-dev patchelf
# patchelf-wrapper is necessary now for cx_Freeze, but not for Curator itself.
RUN pip3 install setuptools cx_Freeze patchelf-wrapper

COPY . .
# alpine4docker.sh does some link magic necessary for cx_Freeze execution
# These files are platform dependent because the architecture is in the file name.
# This script handles it, effectively:
# ARCH=$(uname -m)
# ln -s /lib/libc.musl-${ARCH}.so.1 ldd
# ln -s /lib /lib64
RUN /bin/sh alpine4docker.sh

# Install Curator locally
RUN pip3 install .

# Build (or rather Freeze) Curator
RUN python3 setup.py build_exe

# Rename 'build/exe.{system().lower()}-{machine()}-{MAJOR}.{MINOR}' to curator_build
RUN python3 post4docker.py

### End `builder` segment

### Copy frozen binary to the container that will actually be published
ARG ALPTAG
FROM alpine:${ALPTAG}
RUN apk --no-cache upgrade && apk --no-cache add openssl-dev expat
# The path `curator_build` is from `builder` and `post4docker.py`
COPY --from=builder curator_build /curator/
RUN mkdir /.curator

USER nobody:nobody
ENV LD_LIBRARY_PATH /curator/lib:$LD_LIBRARY_PATH
ENTRYPOINT ["/curator/curator"]

