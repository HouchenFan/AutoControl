#!/bin/bash
if [ "$1" != "" ]
then
	echo "Kill process contain keyword: $1"
	if [ "$2" == "y" ]
	then
		ps -ef | grep $1 | grep -v grep | awk '{print $2}' | xargs kill -9
	else
		ps -ef | grep $1 | grep -v grep
	fi
fi

