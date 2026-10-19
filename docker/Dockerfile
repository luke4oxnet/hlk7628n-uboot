# Build environment for the HLK-7628N (MT7628) Ralink SDK U-Boot 1.1.3.
#
# The Ralink SDK toolchain (buildroot-gcc342, GCC 3.4.2) ships as 32-bit x86
# Linux binaries, so the image is 32-bit Debian. The toolchain itself is not
# baked in; docker/build.sh fetches it and mounts it at /opt/buildroot-gcc342.
FROM --platform=linux/386 i386/debian:bullseye

# bullseye is EOL -> use the archive mirror.
RUN set -eux; \
    printf 'deb http://archive.debian.org/debian bullseye main\n' > /etc/apt/sources.list; \
    printf 'deb http://archive.debian.org/debian-security bullseye-security main\n' >> /etc/apt/sources.list; \
    apt-get -o Acquire::Check-Valid-Until=false update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        build-essential \
        bzip2 \
        file \
        bc \
        xxd \
        gawk \
        make \
        zlib1g-dev; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /work
COPY container-build.sh /usr/local/bin/container-build.sh
RUN chmod +x /usr/local/bin/container-build.sh
ENTRYPOINT ["/usr/local/bin/container-build.sh"]
