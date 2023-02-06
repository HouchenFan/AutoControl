#!/bin/bash
shopt -s expand_aliases
shopt expand_aliases
export EGS_HOME_DIR=D:/Program/EGSnrc
export EGS_CONFIG=${EGS_HOME_DIR}/HEN_HOUSE/specs/win3264.conf
export HEN_HOUSE=${EGS_HOME_DIR}/HEN_HOUSE/
export EGS_HOME=${EGS_HOME_DIR}/egs_home/
export CPU_NUMBER=4
#source "${EGS_HOME_DIR}/HEN_HOUSE/scripts/egsnrc_bashrc_additions" # turn this on if in linux
#export EGS_CONFIG=/home/uih/EGSnrc/HEN_HOUSE/specs/linux64.conf
#export EGS_HOME=/home/uih/EGSnrc/egs_home/
echo "EGS_HOME=${EGS_HOME}"
echo "EGS_CONFIG=${EGS_CONFIG}"
echo "HEN_HOUSE=${HEN_HOUSE}"

#workdir=$(cd $(dirname $0); pwd)
#echo ${workdir}
