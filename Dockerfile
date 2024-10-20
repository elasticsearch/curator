# syntax=docker/dockerfile:1@sha256:865e5dd094beca432e8c0a1d5e1c465db5f998dca4e439981029b3b81fb39ed5
ARG PYVER=3.11.9
ARG ALPTAG=3.20@sha256:0a4eaa0eecf5f8c050e5bba433f58c052be7587ee8af3e8b3910ef9ab5fbe9f5
FROM python:latest@sha256:a31cbb4db18c6f09e3300fa85b77f6d56702501fcb9bdb8792ec702a39ba6200:${PYVER}-alpine${ALPTAG} as builder

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
FROM alpine:latest@sha256:beefdbd8a1da6d2915566fde36db9db0b524eb737fc57cd1367effd16dc0d06d:${ALPTAG}
RUN apk --no-cache upgrade && apk --no-cache add openssl-dev expat
# The path `curator_build` is from `builder` and `post4docker.py`
COPY --from=builder curator_build /curator/
RUN mkdir /.curator

USER nobody:nobody
ENV LD_LIBRARY_PATH /curator/lib:$LD_LIBRARY_PATH
ENTRYPOINT ["/curator/curator"]

