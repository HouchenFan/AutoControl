#!/bin/bash

#addphsp EGS_10_NoDBS_pri EGS_10_NoDBS_pri 12 1 0 1
workdir=$(cd $(dirname $0); pwd)
source ${workdir}/egs_config.sh
workdir=${1%/*}
filename=${1##*/}
filename=${filename%.*}
format=.egsinp
echo "Directory: ${workdir}"
echo "Input: ${filename}"
cd ${workdir}

nps=0
phsps=$(ls $workdir/${filename}_w*.IAEAphsp)
phsps=(${phsps})
phsps_num=${#phsps[@]}
echo "Total File Number: ${phsps_num}"
addphsp $workdir/${filename} $workdir/${filename} ${phsps_num} 1 0 1
