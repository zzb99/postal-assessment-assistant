#!/bin/sh
set -eu
umask 077

run_backup() {
    stamp="$(date '+%Y%m%d-%H%M%S')"
    daily_dir="/backups/daily/${stamp}"
    mkdir -p "${daily_dir}" /backups/monthly

    pg_dump --format=custom --file="${daily_dir}/assessment.dump" assessment
    pg_restore --list "${daily_dir}/assessment.dump" >/dev/null
    tar -czf "${daily_dir}/documents.tar.gz" -C /data documents
    tar -tzf "${daily_dir}/documents.tar.gz" >/dev/null

    find /backups/daily -mindepth 1 -maxdepth 1 -type d -mtime +7 -exec rm -rf -- {} +
    if [ "$(date '+%d')" = "01" ]; then
        month="$(date '+%Y-%m')"
        if [ ! -e "/backups/monthly/${month}" ]; then
            cp -a "${daily_dir}" "/backups/monthly/${month}"
        fi
    fi
    find /backups/monthly -mindepth 1 -maxdepth 1 -type d -mtime +93 -exec rm -rf -- {} +
}

while true; do
    run_backup
    sleep 86400
done
