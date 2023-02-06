#!/bin/bash

workdir=$(cd $(dirname $0); pwd)
source ${workdir}/egs_config.sh

format=egsinp

echo "Function:${1}"
echo "Input: ${2}"
echo "Pegs4: ${3}"
command="${1} -i ${2} -p ${3}"
echo "Command: ${command}"

#cd /home/uih/EGSnrc/egs_home/${1}
#cd "${EGS_HOME_DIR}\egs_home\${1}"
${EGS_HOME_DIR}/HEN_HOUSE/scripts/bin/egs-parallel --batch cpu -n${CPU_NUMBER} -v -f -c "${command}"
