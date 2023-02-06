#!/bin/bash
if [ "$1" != "" ]
then
	echo "Renice process contain keyword: $1"
	if [ ! -n "$2" ]
	then
		ps -ef | grep $1 | grep -v grep | grep -v /bin/bash
	else
		nice_value=$2
		if [ ${nice_value} -le 19 -a ${nice_value} -ge -20 ]
		then
			ps -ef | grep $1 | grep -v grep | grep -v /bin/bash | awk '{print $2}' | xargs renice ${nice_value}
		else
			echo "Nice value invalid: ${nice_value}"
			ps -ef | grep $1 | grep -v grep | grep -v /bin/bash
		fi
	fi
fi
