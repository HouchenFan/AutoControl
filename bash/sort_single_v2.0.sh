#!/bin/bash

#workdir=$(cd $(dirname $0); pwd)
format=egsinp
inputfile=${1}
workdir=${inputfile%/*}
#movedir=/home/uih/IBL
movedir=${2}

echo -e "Input file:$inputfile"
filename=${inputfile%.*}
filename=${filename##*/}
echo "File name:$filename"
#subdir=$workdir/${filename}
subdir=${movedir}/${filename}
if [ ! -d $subdir ]
then
	mkdir $subdir
else
	echo "Dir:$subdir is already exists."
fi
subfiles=$(ls ${workdir}/${filename}*)
for subf in $subfiles
do
	if [ -d ${subf} -o ! -f ${subf} ];then
		continue
	fi
	subname=${subf%.*}
	subname=${subname##*/}
	format=${subf##*.}
#	echo $subname
	len=${#filename}
	((minlen=len+2))
	if [[ ${subname} == ${filename} ]]
	then
		
#		echo "Format:${format}"
		if [ ${format} == 'egsinp' ]
		then
#			echo "Format match"
			mv $subf $subdir/EGS.${format}
		else
#			echo "Format unmatch"
			mv $subf $subdir/EGS.${format}
		fi
	else
#		echo "Part Name"
		if [[ ${#subname} -gt $[len+2] && ${subname:${len}:2} == '_w' ]]
		then
#			echo $subf
			mv $subf $subdir/EGS${subname#${filename}}.${format}
		else
			echo "Unmatched file:${subf}"
		fi
			
	fi
done


