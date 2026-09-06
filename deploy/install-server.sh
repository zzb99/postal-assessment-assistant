#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "请使用root执行此脚本。" >&2
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    if command -v dnf >/dev/null 2>&1; then
        dnf install -y device-mapper-persistent-data lvm2 dnf-plugins-core git curl
        dnf config-manager --add-repo=http://mirrors.cloud.aliyuncs.com/docker-ce/linux/centos/docker-ce.repo
        dnf install -y dnf-plugin-releasever-adapter --repo alinux3-plus
        dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin --nobest
    else
        echo "此脚本仅支持Alibaba Cloud Linux 3的dnf环境。" >&2
        exit 1
    fi
fi
systemctl enable --now docker
docker compose version

swap_bytes="$(awk '/SwapTotal/ {print $2 * 1024}' /proc/meminfo)"
if [ "${swap_bytes%.*}" -lt 2147483648 ]; then
    if [ ! -e /swapfile ]; then
        fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
        chmod 600 /swapfile
        mkswap /swapfile
    fi
    swapon /swapfile || true
    grep -q '^/swapfile ' /etc/fstab || printf '/swapfile none swap sw 0 0\n' >> /etc/fstab
fi

mkdir -p /opt/postal-assessment
echo "Docker与Swap准备完成。"
