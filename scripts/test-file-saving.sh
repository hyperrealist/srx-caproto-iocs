#!/bin/bash

# shellcheck source=/dev/null
. /etc/profile.d/epics.sh

data_dir="/tmp/test/$(date +%Y/%m/%d)"

if [ ! -d "${data_dir}" ]; then
	mkdir -v -p "${data_dir}"
fi

caput "BASE:{Dev:Save1}:write_dir" "${data_dir}"
caput "BASE:{Dev:Save1}:file_name" "saveme_{num:06d}_{uid}.h5"
caput "BASE:{Dev:Save1}:stage" 1
for i in $(seq 50); do
    echo "$i"
    sleep 0.1
    caput "BASE:{Dev:Save1}:acquire" 1
done

caput "BASE:{Dev:Save1}:stage" 0