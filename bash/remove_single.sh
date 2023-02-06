#!/bin/bash

#workdir=$(cd $(dirname $0); pwd)
format=egsinp
inputfile=${1}
workdir=${inputfile%/*}


trash=${workdir}/Trash
if [ ! -d $trash ]
then
	mkdir $trash
fi

subname=${inputfile%.${format}}
subname=${subname##*/}
len=${#subname}
subfile=$(ls $workdir/${subname}*)
if [ -f $workdir/${subname}.egsphsp1 -o -f $workdir/$d${subname}.3ddose ]
then
	for sf in $subfile
	do
		echo $sf
		sfname=${sf%.}
		sfname=${sfname##*/}
		sfformat=${sf##*.}
		#if [[ ${#sfname} -gt $[len+2] && ${sfname:${len}:2} == '_w' && ${sfformat:0:7} == "egsphsp" ]]
		if [[ ${#sfname} -gt $[len+2] && ${sfname:${len}:2} == '_w' ]]
		then
#			mv $sf $trash/
			rm $sf
		fi
	done
fi




