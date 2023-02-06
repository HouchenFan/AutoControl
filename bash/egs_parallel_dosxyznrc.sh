#!/bin/bash

workdir=$(cd $(dirname $0); pwd)
source ${workdir}/egs_config.sh

format=egsinp
echo "Work Dir: ${workdir}"
command="dosxyznrc -i ${1} -p ${2}"
echo "Command: ${command}"

${EGS_HOME_DIR}/HEN_HOUSE/scripts/bin/egs-parallel --batch cpu -n${CPU_NUMBER} -v -f -c "${command}"
