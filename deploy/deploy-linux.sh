#!/bin/sh
set -eu

repo_dir="${1:-/opt/postal-assessment}"
env_file="${2:-/etc/postal-assessment.env}"
cd "${repo_dir}"

if [ ! -f "${env_file}" ]; then
    echo "缺少私有环境文件：${env_file}" >&2
    exit 1
fi
chmod 600 "${env_file}"

docker compose --env-file "${env_file}" config --quiet
docker compose --env-file "${env_file}" build --pull
docker compose --env-file "${env_file}" up -d --remove-orphans

attempt=0
until curl --fail --silent --show-error http://127.0.0.1:8080/api/health >/dev/null; do
    attempt=$((attempt + 1))
    if [ "${attempt}" -ge 30 ]; then
        docker compose --env-file "${env_file}" ps
        exit 1
    fi
    sleep 3
done

docker compose --env-file "${env_file}" ps
echo "本机临时入口已通过健康检查：http://127.0.0.1:8080"
