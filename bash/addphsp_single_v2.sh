#!/bin/bash

workdir=$(cd $(dirname $0); pwd)
source ${workdir}/egs_config.sh

function size()
{
stat -c %s $1 | tr -d '\n'
}

#workdir=$(cd $(dirname $0); pwd)
workdir=${1%/*}
file=${1##*/}
filename=${file%.*}
format=.egsinp
echo "Directory: ${workdir}"
echo "Input: ${filename}"
cd ${workdir}
#nphs_lnum=$(grep "SCORING INPUT" $workdir/${filename}.egsinp)
#nphs_lnum=${nphs_lnum%%,*}
nphs=$(grep "SCORING INPUT" $workdir/${filename}${format})
#nphs=$(sed -n ${nphs_lnum}p ${workdir}/${filename}$format)
nphs=${nphs%%,*}
echo "Score Plane Num: ${nphs}"
for ((nph=1;nph<=$((nphs));nph++))
do
	nps=0
	phsps=$(ls $workdir/${filename}_w*.egsphsp${nph})
	phsps=(${phsps})
	phsps_num=${#phsps[@]}
	echo "Total File Number: ${phsps_num}"
	for p in ${phsps[@]}
	do
		psize=$(size $p)
		if [ ${psize} -ge 56 ];then
			((nps++))
		fi
	done
	echo "Phsp${nph} Num:$nps"
	addphsp $workdir/${filename} $workdir/${filename} ${nps} 1 ${nph}
done

