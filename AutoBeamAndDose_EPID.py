#!/home/uih/anaconda3/bin/python


# -*- coding: utf-8 -*-
"""
Created on 2021-08-04

@author: fuwei.zhao
"""
import os
import re
import sys
import subprocess
from subprocess import check_call, CalledProcessError
import time
from datetime import datetime
import functools
import numpy as np
from pathlib import Path
import ReadPhsp
import logging
import platform
from multiprocessing import cpu_count, Pool
from functools import partial

# Config
# only used in windows
git_bash_path = R"D:\Program\Git\bin\bash.exe"

# used in both system
move2path = R"/home/uih/Data/Res" # move to where
EGS_rename = "EGS" # rename the output file
is_phsp_overwrite = True # if True, delete the previous exist phsp file

global_pegs4_path = "521icru"
# shell_dir = os.path.join(os.getcwd(), 'bash') #
shell_dir = os.path.join(sys.path[0], 'bash')

# beam_single_run = os.path.join(shell_dir, "beam_exb_single.sh")
beam_single_run = os.path.join(shell_dir, "egs_parallel.sh")
addphsp_single = os.path.join(shell_dir, "addphsp_single_v2.sh")
# dose_single_run = os.path.join(shell_dir, "dose_exb_single.sh")
dose_single_run = os.path.join(shell_dir, "egs_parallel_dosxyznrc.sh")
sort_single = os.path.join(shell_dir, "sort_single_v2.0.sh")
remove_single = os.path.join(shell_dir, "remove_single.sh")


if not Path(move2path).is_dir():
    os.mkdir(move2path)

sys_platform = platform.system()
if sys_platform.lower() == "windows":
    print("Working in the Windows.")
    os.system('color')
    beam_single_run = git_bash_path + " " + beam_single_run
    addphsp_single = git_bash_path + " " + addphsp_single
    dose_single_run = git_bash_path + " " + dose_single_run
    sort_single = git_bash_path + " " + sort_single
    remove_single = git_bash_path + " " + remove_single
elif sys_platform.lower() == "linux":
    print("Working in the Linux.")
else:
    print("Unknow System!")


PI = np.pi

# Basic length unit is mm
mm = 1
cm = 10
m = 1000

# Basic angle unit is rad
rad = np.pi
deg = np.pi/180

# Computation Sets
PRECISION = 1e-6
DPRECISION = 1e-12

def InitialEGSConfigure(egs_home=None, egs_config=None):
    if egs_home is None:
        egs_home = os.environ.get('EGS_HOME')
    if egs_config is None:
        egs_config = os.environ.get('EGS_CONFIG')
    if egs_home is not None and egs_config is not None:
        egs_home = Path(egs_home)
        egs_config = Path(egs_config)
        egs_home_dir = egs_config.parent.parent.parent
        config_template_file = Path(shell_dir).joinpath('egs_config_template.sh')
        config_file = Path(shell_dir).joinpath('egs_config.sh')
        cpu_number = cpu_count()
        with open(config_template_file, 'r') as conf:
            text = conf.read()

        def replace_match(match, rep_str='') -> str:
            name = match.group().split('=')[0]
            new_line = str(name + '=' + str(rep_str) + '\n')
            return new_line

        def mark_off(match) -> str:
            line = match.group()
            line = str(line).strip()
            if line[0] == "#":
                return line[1:]
            else:
                return line

        text = re.sub(r'export EGS_HOME_DIR=.+?\n', partial(replace_match, rep_str=egs_home_dir.as_posix()), text)
        text = re.sub(r'export EGS_HOME=.+?\n', partial(replace_match, rep_str=egs_home.as_posix() + "/"), text)
        text = re.sub(r'export EGS_CONFIG=.+?\n', partial(replace_match, rep_str=egs_config.as_posix()), text)
        text = re.sub(r'export CPU_NUMBER=.+?\n', partial(replace_match, rep_str=cpu_number), text)
        if sys_platform.lower() == "linux":
            bashrc_line = re.search(r"[^#]source .+?egsnrc_bashrc_additions.+?$\n", text)
            if bashrc_line is None:
                if re.search(r"#source .+?egsnrc_bashrc_additions.+?\n", text):
                    text = re.sub(r"#source .+?egsnrc_bashrc_additions.+?\n", mark_off, text)
                else:
                    text += 'source "${EGS_HOME_DIR}/HEN_HOUSE/scripts/egsnrc_bashrc_additions"\n'
        with open(config_file, 'w') as conf:
            conf.write(text)


colormap = {'black': 30, 'red': 31, 'green': 32, 'yellow': 33, 'blue': 34, 'magenta': 35, 'cyan':36, 'white': 37}
# colormap_background = {'black': 40, 'red': 41, 'green': 42, 'yellow': 43, 'blue': 44, 'magenta': 45, 'cyan': 46, 'white': 47}

def hlprint(*messgae, color='White', **kw):
    color = color.lower()
    if color not in colormap:
        hlprint("No desired color, reset to white. ", color='Red')
        color='White'
    msg = "".join(str(m) for m in messgae)
    print("\x1b[1;%dm%s\x1b[0m" % (colormap[color], msg), **kw)


class Log(object):
    def __init__(self):
        logging_file = os.path.join(os.getcwd(), 'EGSnrc.log')
        if not os.path.isdir(os.path.split(logging_file)[0]):
            os.makedirs(os.path.split(logging_file)[0])
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
            filename=logging_file,
            filemode='w',
        )

    def __call__(self, message, level=0):
        if level == 0:
            logging.info(message)
            hlprint(message, color='White')
        elif level == 1:
            logging.debug(message)
            hlprint(message, color='Green')
        elif level == 2:
            logging.critical(message)
            hlprint(message, color='Blue')
        elif level == 3:
            logging.warning(message)
            hlprint(message, color='Yellow')
        elif level == 4:
            logging.error(message)
            hlprint(message, color='Red')


log = Log()


def GetLocalTime():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def CallTiming(func):
    @functools.wraps(func)
    def wrapper(*args, **kw):
        # hlprint("Start call: %s in %s" % (func.__name__, GetLocalTime()), color='Green')
        log("Start call: %s in %s" % (func.__qualname__, GetLocalTime()), 1)
        start_time = datetime.now()
        res = func(*args, **kw)
        stop_time = datetime.now()
        # hlprint("Stop  call: %s in %s, Total %.2f seconds." % (func.__name__, GetLocalTime(), (stop_time - start_time).total_seconds()), color='Green')
        log("Stop  call: %s in %s, Total %.2f seconds." % (func.__qualname__, GetLocalTime(), (stop_time - start_time).total_seconds()), 1)
        return res
    return wrapper


def SearchByKey(key, string):
    # search = re.findall(r'%s[-]*\d+\.?\d*' % key, string)
    search = re.findall(r'(?<=%s)[-]*\d+\.?\d*' % key, string)
    if search is not None:
        result = [float(x) for x in search]
        return result
    else:
        return None


# @CallTiming
# def ReadPhspCpp(file_list):
#     assert isinstance(file_list, list) and len(file_list) > 0
#     command = [PHSPCPP] + file_list
#     results = run(command, shell=False)
#     print(results.stdout)
#     print(results.stderr)
#     print(results.returncode)


def FileName(path):
    # assert os.path.isfile(path)
    return os.path.splitext(os.path.split(path)[-1])[0]


# @CallTiming
# def AddPhsp(input_file):
#     input_dir = os.path.split(input_file)[0]
#     input_name = FileName(input_file)
#     startTime = datetime.now()
#     time.sleep(10)
#     while not os.path.isfile(os.path.join(input_dir, input_name + '.egslog')) and not os.path.isfile(
#             os.path.join(input_dir, input_name + '.egslst')) and os.path.isfile(
#         os.path.join(input_dir, input_name + '.lock')):
#         time.sleep(10)
#         stopTime = datetime.now()
#         hlprint("\rTime waited: %8.1f seconds..." % (stopTime - startTime).seconds, color='Blue', end='', flush=True)
#     stopTime = datetime.now()
#     hlprint("Time waited: %8.1f seconds..." % (stopTime - startTime).seconds, color='Blue', end='')
#     print('\n')
#     is_sort_succeed = False
#     is_add_succeed = False
#     is_rm_succeed = False
#     try:
#         if not os.path.isdir(move2path):
#             os.makedirs(move2path)
#         check_call([sort_single, input_file, move2path])
#         is_sort_succeed = True
#     except subprocess.CalledProcessError:
#         print("Bash call sort_single failed. Continue next.")
#     if is_sort_succeed:
#         try:
#             if is_phsp_overwrite and os.path.isfile(os.path.join(move2path, input_name, EGS_rename + ".egsphsp1")):
#                 os.remove(os.path.join(move2path, input_name, EGS_rename + ".egsphsp1"))
#             check_call([addphsp_single, os.path.join(move2path, input_name, EGS_rename + ".egsinp")])
#             if os.path.isfile(os.path.join(move2path, input_name, EGS_rename + ".egsphsp1")):
#                 is_add_succeed = True
#         except subprocess.CalledProcessError:
#             print("Bash call addphsp_single failed. Continue next.")
#     if is_add_succeed:
#         try:
#             # check_call([remove_single, os.path.join(input_dir, input_name, input_name+".egsinp")])
#             check_call([remove_single, os.path.join(move2path, input_name, EGS_rename + ".egsinp")])
#             is_rm_succeed = True
#         except subprocess.CalledProcessError:
#             print("Bash call remove_single failed. Continue next.")
#     try:
#         assert os.path.isfile(os.path.join(move2path, input_name, EGS_rename + ".egsphsp1"))
#     except AssertionError:
#         hlprint('Failed to add up the phsp files.', color='Red')
#
#     return os.path.join(move2path, input_name, EGS_rename + ".egsphsp1")


@CallTiming
def SortPhspFile(input_file):
    input_name = FileName(input_file)
    input_file = Path(input_file)
    score_num = 1
    with open(input_file.as_posix(), 'rt') as fid:
        for line in fid:
            print(line, end="")
            if re.search(r"SCORING INPUT", line):
                score_num = int(line.split(', ')[0])
                print("Score Plane Number:", score_num)
                break
    assert score_num > 0
    for plane_idx in range(score_num):
        plane_num = plane_idx + 1
        empty_phsp_list = []
        valid_phsp_list = []
        for file in input_file.parent.iterdir():
            if not file.is_file():
                continue
            if re.match(r'^%s_w\d+.egsphsp%d' % (input_name, plane_num), file.name):
                phsp_num = int(re.findall(r'(?<=%s_w)\d+' % (input_name,), file.name)[0])
                # print("NO.%2d: %s" % (phsp_num, file.as_posix()))
                if os.path.getsize(file.as_posix()) > 28:
                    valid_phsp_list.append(file.as_posix())
                else:
                    empty_phsp_list.append(file.as_posix())
        if len(empty_phsp_list) > 0:
            for item in empty_phsp_list:
                if os.path.isfile(item):
                    os.remove(item)
        phsp_file_list = sorted(valid_phsp_list, key=lambda x: os.path.getsize(x), reverse=True)
        new_phsp_list = []
        for idx, phsp in enumerate(phsp_file_list):
            phsp = Path(phsp)
            new_phsp = phsp.with_name('temp_w%d.egsphsp%d' % (idx + 1, plane_num))
            os.rename(phsp.as_posix(), new_phsp.as_posix())
            new_phsp_list.append(new_phsp.as_posix())
        for idx, phsp in enumerate(new_phsp_list):
            phsp = Path(phsp)
            new_phsp = phsp.with_name(phsp.name.replace('temp', input_name))
            os.rename(phsp.as_posix(), new_phsp.as_posix())


@CallTiming
def AddPhspNew(input_file):
    # input_dir = os.path.split(input_file)[0]
    input_name = FileName(input_file)
    # startTime = datetime.now()
    # time.sleep(10)
    # while not os.path.isfile(os.path.join(input_dir, input_name + '.egslog')) and not os.path.isfile(
    #         os.path.join(input_dir, input_name + '.egslst')) and os.path.isfile(os.path.join(input_dir, input_name + '.lock')):
    #     time.sleep(10)
    #     stopTime = datetime.now()
    #     hlprint("\rTime waited: %8.1f seconds..." % (stopTime-startTime).seconds, color='Blue', end='', flush=True)
    # stopTime = datetime.now()
    # hlprint("Time waited: %8.1f seconds..." % (stopTime - startTime).seconds, color='Blue', end='')
    print('\n')
    is_sort_succeed = False
    is_add_succeed = False
    # is_rm_succeed = False
    try:
        if not os.path.isdir(move2path):
            os.makedirs(move2path)
        check_call(" ".join([sort_single, str(input_file).replace(os.sep, '/'), move2path.replace(os.sep, '/')]), shell=True)
        is_sort_succeed = True
    except subprocess.CalledProcessError:
        print("Bash call sort_single failed. Continue next.")
    if is_sort_succeed:
        try:
            new_input_path = os.path.join(move2path, input_name, EGS_rename + ".egsinp")
            if is_phsp_overwrite and os.path.isfile(os.path.join(move2path, input_name, EGS_rename + ".egsphsp1")):
                os.remove(os.path.join(move2path, input_name, EGS_rename + ".egsphsp1"))
            SortPhspFile(new_input_path)
            check_call(" ".join([addphsp_single, new_input_path.replace(os.sep, '/')]), shell=True)
            if os.path.isfile(os.path.join(move2path, input_name, EGS_rename + ".egsphsp1")):
                is_add_succeed = True
        except subprocess.CalledProcessError:
            print("Bash call addphsp_single failed. Continue next.")
    if is_add_succeed:
        try:
            # check_call([remove_single, os.path.join(input_dir, input_name, input_name+".egsinp")])
            check_call(" ".join([remove_single, os.path.join(move2path, input_name, EGS_rename + ".egsinp").replace(os.sep, '/')]), shell=True)
            is_rm_succeed = True
        except subprocess.CalledProcessError:
            print("Bash call remove_single failed. Continue next.")
    try:
        assert os.path.isfile(os.path.join(move2path, input_name, EGS_rename + ".egsphsp1"))
    except AssertionError:
        hlprint('Failed to add up the phsp files.', color='Red')

    return os.path.join(move2path, input_name, EGS_rename + ".egsphsp1")


@CallTiming
def Beam(beam_function, beam_file, pegs4_path):
    for ext in ['.egslog', '.egslst', '.lock']:
        temp_file = os.path.splitext(beam_file)[0] + ext
        if os.path.isfile(temp_file):
            print("Remove previous file: ", temp_file)
            os.remove(temp_file)
    assert os.path.isfile(beam_file)
    try:
        check_call(' '.join([beam_single_run, FileName(beam_function), FileName(beam_file), pegs4_path]), shell=True)
        # check_call([beam_single_run, FileName(beam_function), FileName(beam_file), pegs4_path])
        print("Done")
    except subprocess.CalledProcessError as e:
        hlprint("Bash call beam_single_run failed. Continue next.", color='Red')
    phsp_path = AddPhspNew(beam_file)
    hlprint("BEAMnrc Finished.", color='Green')
    return phsp_path


@CallTiming
def Dose(input_file, pegs4_path=global_pegs4_path):
    assert os.path.isfile(input_file)
    for ext in ['.3ddose', '.lock']:
        temp_file = os.path.splitext(input_file)[0] + ext
        if os.path.isfile(temp_file):
            print("Remove previous file: ", temp_file)
            os.remove(temp_file)
    print("Input: ", input_file)
    # input_dir = os.path.split(input_file)[0]
    input_name = FileName(input_file)
    try:
        check_call(" ".join([dose_single_run, input_name.replace(os.sep, '/'), pegs4_path]), shell=True)
    except subprocess.CalledProcessError as err:
        hlprint('Bash call dose_single_run failed. Continue next.', color='Red')
    # startTime = datetime.now()
    # while not os.path.isfile(os.path.join(input_dir, input_name + '.3ddose')) and os.path.isfile(os.path.join(input_dir, input_name + '.lock')):
    #     time.sleep(10)
    #     stopTime = datetime.now()
    #     hlprint("\rTime waited: %8.1f seconds..." % (stopTime-startTime).seconds, color='Blue', end='', flush=True)
    # stopTime = datetime.now()
    # hlprint("\rTime waited: %8.1f seconds...\n" % (stopTime - startTime).seconds, color='Green', end='')
    print('\n')
    try:
        check_call(" ".join([sort_single, input_file.replace(os.sep, '/'), move2path.replace(os.sep, '/')]), shell=True)
    except subprocess.CalledProcessError as e:
        hlprint("Sort Failed.", color='Red')
    try:
        check_call(" ".join([remove_single, os.path.join(move2path, input_name, EGS_rename + ".egsinp").replace(os.sep, '/')]), shell=True)
    except subprocess.CalledProcessError as e:
        hlprint("Clean Failed.", color='Red')
    hlprint("DOSEnrc Finished.", color='Green')


def DoseRZ():
    pass


def Replace(line, idx, new_info):
    assert isinstance(line, str)
    new_line = line.split(',')
    assert idx < len(new_line)
    new_line[idx] = new_info
    return ','.join(new_line)


class Info(object):
    def __init__(self, line, position, info):
        self.line = line
        self.position = position
        self.info = str(info)


def ModifyFile(path, new_path, Info_list):
    with open(path, 'r') as fid:
        txt = fid.readlines()
    # Modify
    for i in Info_list:
        assert isinstance(i, Info)
        txt[i.line] = Replace(txt[i.line], i.position, i.info)
        if txt[i.line][-1] != '\n':
            txt[i.line] += '\n'
    with open(new_path, 'w') as fid:
        fid.writelines(txt)


def ListFormat(path, format_str):
    assert os.path.isdir(path)
    assert isinstance(format_str, str)
    file_list = os.listdir(path)
    file_list = list(filter(lambda x: os.path.splitext(x)[1] == format_str, file_list))
    file_list = list(map(lambda x: os.path.join(path, x), file_list))
    return file_list


def AutoProcess(path, result_list, ext):
    assert isinstance(result_list, list)
    if isinstance(path, str):
        path = Path(path)
    elif not isinstance(path, Path):
        raise TypeError('Input is not str or path...')
    if path.is_dir():
        for pt in path.iterdir():
            AutoProcess(pt, result_list, ext)
    elif path.is_file():
        if os.path.splitext(str(path))[1] == ext:
            # print(path)
            result_list.append(path)
    return result_list


@CallTiming
def AutoRun(beam_file, dose_file):
    beam_function = r"/home/uih/EGSnrc/egs_home/BEAM_High_Energy_Head"
    pegs4 = global_pegs4_path
    if beam_file == r"/home/uih/EGSnrc/egs_home/BEAM_High_Energy_Head/15MV_W1.2cm_App10cm.egsinp":
        phsp_path = r"/home/uih/EGSnrc/egs_home/BEAM_High_Energy_Head/15MV_W1.2cm_App10cm/15MV_W1.2cm_App10cm_bak.egsphsp2"
    else:
        phsp_path = Beam(beam_function, beam_file, pegs4)
    i_phsp = Info(18, 0, phsp_path)
    ModifyFile(dose_file, dose_file, [i_phsp])
    Dose(dose_file, pegs4)


@CallTiming
def AutoRun2(spectrum, source_size, source_dispersion):
    # sample_list = [r"/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/IBL_Spetrum2.9_FS5/IBL_Spetrum2.9_FS5_L3_NoDBS.egsinp",
    #                r"/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/IBL_Spetrum2.9_FS10/IBL_Spetrum2.9_FS10_L3_NoDBS.egsinp",
    #                r"/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/IBL_Spetrum2.9_FS27/IBL_Spetrum2.9_FS27_L3_NoDBS.egsinp"]
    sample_list = [r"/home/uih/CBCT3/Sample/P2.3_SL0.6_SS0.1_SD0.8_FS5_D60.egsinp",
                   r"/home/uih/CBCT3/Sample/P2.3_SL0.6_SS0.1_SD0.8_FS10_D60.egsinp",
                   r"/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/P2.30_SL0.6_F1.413_SS0.1_SD0.8_FS27_D60_NoDBS.egsinp"]
    pdd_sample_list = [r"/home/uih/EGSnrc/egs_home/dosxyznrc/IBL_PDD_Spetrum2.9_FS5/IBL_PDD_Spetrum2.9_FS5.egsinp",
                       r"/home/uih/EGSnrc/egs_home/dosxyznrc/IBL_PDD_Spetrum2.9_FS10/IBL_PDD_Spetrum2.9_FS10.egsinp",
                       r"/home/uih/EGSnrc/egs_home/dosxyznrc/IBL_PDD_Spetrum2.9_FS27/IBL_PDD_Spetrum2.9_FS27.egsinp"]

    prf_sample_list = [
        r"/home/uih/EGSnrc/egs_home/dosxyznrc/IBL_ProfileX_Spetrum2.9_FS5_D1.0/IBL_ProfileX_Spetrum2.9_FS5_D1.0.egsinp",
        r"/home/uih/EGSnrc/egs_home/dosxyznrc/IBL_ProfileX_Spetrum2.9_FS10_D1.0/IBL_ProfileX_Spetrum2.9_FS10_D1.0.egsinp",
        r"/home/uih/EGSnrc/egs_home/dosxyznrc/IBL_ProfileX_Spetrum2.9_FS27_D1.0/IBL_ProfileX_Spetrum2.9_FS27_D1.0.egsinp"]
    depth_list = [1.0, 5.0, 10.0, 20.0, 30.0]
    # depth_list = [1.0]
    half_thickness = 0.3
    beam_path = r"/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL"
    dose_path = "/home/uih/EGSnrc/egs_home/dosxyznrc"
    pegs4 = "521icru"

    spectrum_name = os.path.splitext(os.path.split(spectrum)[1])[0]
    spectrum_char = spectrum_name.split('_')
    print('Spectrum', spectrum)
    for idx, sample in enumerate(sample_list):
        if idx != 2:
            continue
        # if idx == 2:
        #     continue
        sample_name = os.path.splitext(os.path.split(sample)[1])[0]
        # sample_char = sample_name.split('_')
        # info_list = [Info(5, 2, str(source_size)), Info(5, 7, str(source_size)), Info(5, 6, str(source_dispersion)), Info(7, 0, spectrum), Info(3, 0, str(1000000000))]
        info_list = [Info(4, 2, str(source_size)), Info(4, 7, str(source_size)), Info(4, 6, str(source_dispersion)),
                     Info(6, 0, spectrum), Info(3, 0, str(10000000000))]
        # new_file_name = '_'.join([spectrum_char[0], spectrum_char[1], spectrum_char[2], spectrum_char[3], spectrum_char[4], "SS%.1f" % source_size, "SD%.1f" % source_dispersion, sample_char[-1]]) + '.egsinp'
        new_file_name = '_'.join(
            [spectrum_char[0], spectrum_char[1], "SS%.1f" % source_size, "SD%.1f" % source_dispersion,
             'FS%d' % SearchByKey('FS', sample_name)[0]]) + '.egsinp'
        new_file_path = os.path.join(beam_path, new_file_name)
        print('File:', new_file_path)
        ModifyFile(sample, new_file_path, info_list)
        phsp_path = Beam(beam_path, new_file_path, pegs4)
        # phsp_path = os.path.join(move2path, FileName(new_file_name), EGS_rename + '.egsphsp1')
        print('PHSP:', phsp_path)
        phsp_total_events = int(ReadPhsp.Phsp(phsp_path).TotalNumParticles)
        print("Total events in phsp file: ", phsp_total_events)
        # PDD
        # pdd_new_name = os.path.splitext(new_file_name)[0] + '_PDD' + ".egsinp"
        # pdd_new_path = os.path.join(dose_path, pdd_new_name)
        # info_list = [Info(19, 0, phsp_path), Info(20, 0, str(phsp_total_events))]
        # ModifyFile(pdd_sample_list[idx], pdd_new_path, info_list)
        # Dose(pdd_new_path)
        # for depth in depth_list:
        #     prf_new_name = os.path.splitext(new_file_name)[0]+"_PF%.1f" % depth + ".egsinp"
        #     prf_new_path = os.path.join(dose_path, prf_new_name)
        #     print('New File:', prf_new_name)
        #     z_top = depth - half_thickness
        #     z_bottom = depth + half_thickness
        #     info_list = [Info(10, 0, str(z_top)), Info(11, 0, str(z_bottom)), Info(17, 7, str(z_top)), Info(19, 0, str(phsp_total_events)), Info(18, 0, phsp_path)]
        #     ModifyFile(prf_sample_list[idx], prf_new_path, info_list)
        #     Dose(prf_new_path)


@CallTiming
def AutoRun3(spectrum, source_size, source_dispersion):
    pegs4 = '521icruSW'
    field_size_list = np.array([5, 10, 27, 40])
    beam_IBL_path = r"/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL"
    # beam_SW_path = r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID"
    beam_IBL_function = r"/home/uih/EGSnrc/egs_home/bin/linux64/BEAM_UIH_IBL"
    # beam_SW_function = r"/home/uih/EGSnrc/egs_home/bin/linux64/BEAM_SW_EPID"
    # dose_path = r"/home/uih/EGSnrc/egs_home/dosxyznrc"
    # dose_pegs = "521icru_AP16"
    # beam_SW_sample = r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/FS5_SW30_back.egsinp"
    # spectrum = r"/home/uih/IBL/Spe/P2.3_SL1.6_R1.2_ME2.270_FWHM3.297_DSP1.433.Spectrum"
    spectrum_name = FileName(spectrum)
    spectrum_char = spectrum_name.split('_')
    print('Spectrum', spectrum)
    # IBL_sample_list = [r"/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/IBL_Spetrum2.3_FS5.egsinp",
    #                    r"/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/IBL_Spetrum2.3_FS10.egsinp",
    #                    r"/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/IBL_Spetrum2.3_FS27.egsinp"]

    # IBL_sample_list = [r"/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/IBL_Spetrum2.3_Target0.67_FS5.egsinp",
    #                    r"/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/IBL_Spetrum2.3_Target0.67_FS10.egsinp",
    #                    r"/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/IBL_Spetrum2.3_Target0.67_FS27.egsinp"]
    # IBL_sample_list = ["/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/Sample/P2.3_SL0.6_SS0.1_SD0.8_FS5_D60.egsinp",
    #                    "/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/Sample/P2.3_SL0.6_SS0.1_SD0.8_FS10_D60.egsinp",
    #                    "/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/Sample/P2.3_SL0.6_SS0.1_SD0.8_FS27_D60.egsinp"]
    IBL_sample_list = ["/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/Sample/P2.3_SL0.6_SS0.1_SD0.8_NoDBS_FS5_D60.egsinp",
                       "/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/Sample/P2.3_SL0.6_SS0.1_SD0.8_NoDBS_FS10_D60.egsinp",
                       "/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/Sample/P2.3_SL0.6_SS0.1_SD0.8_NoDBS_FS27_D60.egsinp",
                       "/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/Sample/P2.3_SL0.6_SS0.1_SD0.8_NoDBS_FS40_D60.egsinp"]

    # SW_sample_list = [r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/sample/FS5_SW1_sample_nDBS.egsinp",
    #                   r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/sample/FS10_SW1_sample_nDBS.egsinp",
    #                   r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/sample/FS27_SW1_sample_nDBS.egsinp"]
    #
    # Air_sample_list = [r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/sample/FS5_Air_sample_nDBS.egsinp",
    #                    r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/sample/FS10_Air_sample_nDBS.egsinp",
    #                    r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/sample/FS27_Air_sample_nDBS.egsinp"]

    # SW_sample_list = [r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/FS5_SW1_sample_SIM100.egsinp",
    #                   r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/FS10_SW1_sample_SIM100.egsinp",
    #                   r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/FS27_SW1_sample_SIM100.egsinp"]
    # Air_sample_list = [r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/FS5_Air_sample_SIM100.egsinp",
    #                    r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/FS10_Air_sample_SIM100.egsinp",
    #                    r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/FS27_Air_sample_SIM100.egsinp"]
    # EPID_Model_sample = r"/home/uih/EGSnrc/egs_home/dosxyznrc/EPID_FS27_SW28/EPID_FS27_SW28.egsinp"
    # sw_thickness_list = [0, 1, 4, 8, 10, 14, 15, 18, 22, 26, 30]
    # sw_thickness_list = [0, 1, 2, 4, 6, 8, 12, 16, 20, 24, 28]
    # sw_thickness_list = [0, 1, 2, 4, 6, 8, 12, 16, 20, 24, 28]
    # sw_thickness_list = [0, 1, 5, 10, 15, 20, 25, 30]
    # sw_thickness_list = [8, 12, 16, 20, 24, 28]
    score_plane = 60
    sid = 100
    for i, ibl_sample in enumerate(IBL_sample_list):
        if i != 3:
            continue
        sample_name = FileName(ibl_sample)
        sample_char = sample_name.split('_')
        # info_list = [Info(5, 2, str(source_size)), Info(5, 7, str(source_size)), Info(5, 6, str(source_dispersion)), Info(7, 0, spectrum), Info(3, 0, str(4000000000)), Info(24, 0, 0.335)]
        # info_list = [Info(4, 2, str(source_size)), Info(4, 7, str(source_size)), Info(4, 6, str(source_dispersion)),
        #              Info(6, 0, spectrum), Info(3, 0, str(30000000000)), Info(23, 0, 0.335), Info(27, 0, 0.78)]
        info_list = [Info(4, 2, str(source_size)), Info(4, 7, str(source_size)), Info(4, 6, str(source_dispersion)),
                     Info(6, 0, spectrum), Info(3, 0, str(30000000000)), Info(23, 0, 0.335), Info(27, 0, 0.78)]
        # new_file_name = '_'.join(
        #     [spectrum_char[0], spectrum_char[1], spectrum_char[2], spectrum_char[3], spectrum_char[4], "SS%.1f" % source_size, "SD%.1f" % source_dispersion, sample_char[-1], "D60"]) + '.egsinp'
        # new_file_name = '_'.join(
        #     [spectrum_char[0], spectrum_char[1], spectrum_char[4].replace('FWHM', 'F'), "SS%.2f" % source_size, "SD%.1f" % source_dispersion, sample_char[-1], "D60"]) + '.egsinp'
        new_file_name = '_'.join(
            [spectrum_char[0], spectrum_char[1], "SS%.1f" % source_size, "SD%.1f" % source_dispersion,
             'FS%d' % SearchByKey('FS', sample_name)[0], "D%d" % score_plane]) + '.egsinp'
        new_file_path = os.path.join(beam_IBL_path, new_file_name)
        print('IBL: ', new_file_path)
        ModifyFile(ibl_sample, new_file_path, info_list)
        # if i != 0:
        #     phsp_path = Beam(beam_IBL_function, new_file_path, pegs4)
        # else:
        #     phsp_path = r"/home/uih/Disk1/CBCT20/P2.50_SL0.60_SS0.1_SD0.8_FS5_D60/EGS.egsphsp1"
        # phsp_path = r"/home/uih/Disk1/CBCT21/P2.60_SL0.60_SS0.1_SD0.8_FS%d_D60/EGS.egsphsp1" % (field_size_list[i], )
        phsp_path = Beam(beam_IBL_function, new_file_path, pegs4)
        # phsp_path = os.path.join(move2path, FileName(new_file_path), 'EGS.egsphsp1')
        print("Phsp: ", phsp_path)
        if not os.path.isfile(phsp_path):
            print("Phsp file not exists. Continue Next!")
            continue
        print('Phsp: ', phsp_path)
        phsp_total_events = int(ReadPhsp.Phsp(phsp_path).TotalNumParticles)
        print("Total events in phsp file: ", phsp_total_events)

        # try:
        #     AutoRunEPIDPDD(phsp_path)
        # except Exception as err:
        #     print(err)

        # for idx, field_size in enumerate(field_size_list):
        # if spectrum != r"/home/uih/IBL/Spe/P2.30_SL0.6_R0.6_ME2.300_FWHM1.413_DSP0.614.Spectrum":
        #     AutoRun3WT(phsp_path)
        # try:
        #     AutoRun3WT(phsp_path)
        # except Exception as err:
        #     print("Water Tank data produce failed.")
        #     print(err)
        # try:
        #     AutoRunSW(phsp_path)
        # except Exception as err:
        #     print("Solid Water data produce failed.")
        #     print(err)
        # if i == 1:
        #     continue
        # for idx, sw_thickness in enumerate(sw_thickness_list):
        #     # new_beam_name = "_".join([spectrum_char[0], spectrum_char[1], spectrum_char[2], spectrum_char[3], spectrum_char[4],"SS" + str(source_size), "FS%d" % field_size_list[i], "SW%d" % sw_thickness]) + ".egsinp"
        #     # new_beam_name = "_".join(
        #     #     [spectrum_char[0], spectrum_char[1], "SS%.1f" % source_size, "SD%.1f" % source_dispersion, sample_char[-1], "SW%d" % sw_thickness]) + ".egsinp"
        #     new_beam_name = "_".join(
        #         os.path.split(os.path.split(phsp_path)[0])[-1].split('_')[:-1] + ["SW%d.egsinp" % sw_thickness])
        #     new_beam_file = os.path.join(beam_SW_path, new_beam_name)
        #     if sw_thickness == 0:
        #         info_list = [Info(3, 0, str(phsp_total_events)), Info(5, 0, phsp_path), Info(31, 0, "79.9")]
        #         ModifyFile(Air_sample_list[i], new_beam_file, info_list)
        #     else:
        #         z_min = sid - sw_thickness / 2 - score_plane
        #         info_list = [Info(3, 0, str(phsp_total_events)), Info(5, 0, phsp_path), Info(24, 0, str(z_min)),
        #                      Info(25, 0, str(sw_thickness)), Info(31, 0, "79.9")]
        #         ModifyFile(SW_sample_list[i], new_beam_file, info_list)
        #     print("EPID: ", new_beam_file)
        #     sw_phsp_path_old = os.path.join(move2path, os.path.splitext(new_beam_name)[0], EGS_rename + ".egsphsp1")
        #     if os.path.isfile(sw_phsp_path_old):
        #         os.remove(sw_phsp_path_old)
        #     sw_phsp_path = Beam(beam_SW_function, new_beam_file, pegs4)
        #     # sw_phsp_path = os.path.join(move2path, os.path.splitext(new_beam_name)[0], EGS_rename + ".egsphsp1")
        #     print("SW phsp path: ", sw_phsp_path)
        #     # ReadPhspCpp([sw_phsp_path])
        #     # EPID Dose
        #     dose_phsp_total_events = int(ReadPhsp.Phsp(sw_phsp_path).TotalNumParticles)
        #     dose_info_list = [Info(7, 0, sw_phsp_path), Info(8, 0, dose_phsp_total_events * 10), Info(2, 0, "/home/uih/EGSnrc/egs_home/dosxyznrc/EPID_Phantom/EPID_Phantom_AP16_DimX128_DimY128_T0.04_AL0.075.egsphant")]
        #     new_dose_name = "EPID_" + new_beam_name
        #     new_dose_path = os.path.join(dose_path, new_dose_name)
        #     ModifyFile(EPID_Model_sample, new_dose_path, dose_info_list)
        #     try:
        #         Dose(new_dose_path, dose_pegs)
        #     except Exception as err:
        #         print(err)


@CallTiming
def AutoRunWT(input_phsp_path):
    pegs4 = "521icru"
    dose_path = r"/home/uih/EGSnrc/egs_home/dosxyznrc"
    pdd_sample_list = [r"/home/uih/EGSnrc/egs_home/dosxyznrc/examples/IBL_PDD_Spetrum2.9_S5.0_FS5.egsinp",
                       r"/home/uih/EGSnrc/egs_home/dosxyznrc/examples/IBL_PDD_Spetrum2.9_S5.0_FS10.egsinp",
                       r"/home/uih/EGSnrc/egs_home/dosxyznrc/examples/IBL_PDD_Spetrum2.9_S5.0_FS27.egsinp"]

    prf_sample_list = [
        r"/home/uih/EGSnrc/egs_home/dosxyznrc/IBL_ProfileX_Spetrum2.9_FS5_D1.0/IBL_ProfileX_Spetrum2.9_FS5_D1.0.egsinp",
        r"/home/uih/EGSnrc/egs_home/dosxyznrc/IBL_ProfileX_Spetrum2.9_FS10_D1.0/IBL_ProfileX_Spetrum2.9_FS10_D1.0.egsinp",
        r"/home/uih/EGSnrc/egs_home/dosxyznrc/IBL_ProfileX_Spetrum2.9_FS27_D1.0/IBL_ProfileX_Spetrum2.9_FS27_D1.0.egsinp"]
    field_size_list = [5, 10, 27, 40]
    field_size = re.search(r'FS\d+', input_phsp_path.split(os.sep)[-2])
    # field_size_idx = len(field_size_list) - 1
    field_size_idx = 1
    if field_size is not None:
        field_size = int(field_size[0][2:])
        field_size_idx = int(np.argwhere(np.array(field_size_list) == field_size)[0])
        print('Field size: ', field_size_list[field_size_idx])
    else:
        print("Field size unmatched, set to %d" % field_size_list[field_size_idx])
    # depth_list = [1, 15, 30]
    # half_thickness = 0.3
    input_phsp_dir = os.path.split(input_phsp_path)[0]
    input_phsp_events = int(ReadPhsp.Phsp(input_phsp_path).TotalNumParticles)
    print("Input phsp path: ", input_phsp_dir)
    print("Input phsp total events: ", input_phsp_events)
    new_file_name = os.path.split(input_phsp_dir)[-1].replace('_D60', '')
    pdd_new_name = new_file_name + '_PDD' + ".egsinp"
    pdd_new_path = os.path.join(dose_path, pdd_new_name)
    info_list = [Info(19, 0, input_phsp_path), Info(20, 0, str(input_phsp_events * 100))]
    ModifyFile(pdd_sample_list[field_size_idx], pdd_new_path, info_list)
    Dose(pdd_new_path)


@CallTiming
def AutoRun3WT(input_phsp_path):
    beam_function = r"/home/uih/EGSnrc/egs_home/bin/linux64/BEAM_RS"
    beam_path = r"/home/uih/EGSnrc/egs_home/BEAM_RS"
    pegs4 = "521icru"
    sample_list = [r"/home/uih/EGSnrc/egs_home/BEAM_RS/sample.egsinp"]
    # pdd_sample_list = [r"/home/uih/EGSnrc/egs_home/dosxyznrc/IBL_PDD_Spetrum2.9_FS5/IBL_PDD_Spetrum2.9_FS5.egsinp",
    #                    r"/home/uih/EGSnrc/egs_home/dosxyznrc/IBL_PDD_Spetrum2.9_FS10/IBL_PDD_Spetrum2.9_FS10.egsinp",
    #                    r"/home/uih/EGSnrc/egs_home/dosxyznrc/IBL_PDD_Spetrum2.9_FS27/IBL_PDD_Spetrum2.9_FS27.egsinp"]
    pdd_sample_list = [r"/home/uih/EGSnrc/egs_home/dosxyznrc/examples/IBL_PDD_Spetrum2.9_S5.0_FS5.egsinp",
                       r"/home/uih/EGSnrc/egs_home/dosxyznrc/examples/IBL_PDD_Spetrum2.9_S5.0_FS10.egsinp",
                       r"/home/uih/EGSnrc/egs_home/dosxyznrc/examples/IBL_PDD_Spetrum2.9_S5.0_FS27.egsinp"]

    prf_sample_list = [
        r"/home/uih/EGSnrc/egs_home/dosxyznrc/IBL_ProfileX_Spetrum2.9_FS5_D1.0/IBL_ProfileX_Spetrum2.9_FS5_D1.0.egsinp",
        r"/home/uih/EGSnrc/egs_home/dosxyznrc/IBL_ProfileX_Spetrum2.9_FS10_D1.0/IBL_ProfileX_Spetrum2.9_FS10_D1.0.egsinp",
        r"/home/uih/EGSnrc/egs_home/dosxyznrc/IBL_ProfileX_Spetrum2.9_FS27_D1.0/IBL_ProfileX_Spetrum2.9_FS27_D1.0.egsinp"]

    dose_path = r"/home/uih/EGSnrc/egs_home/dosxyznrc"
    field_size_list = [5, 10, 27]
    field_size = re.search(r'FS\d+', input_phsp_path.split(os.sep)[-2])
    # field_size_idx = len(field_size_list) - 1
    field_size_idx = 2
    if field_size is not None:
        field_size = int(field_size[0][2:])
        try:
            field_size_idx = int(np.argwhere(np.array(field_size_list) == field_size)[0])
            print('Field size: ', field_size_list[field_size_idx])
        except Exception as err:
            print(err)
    else:
        print("Field size unmatched, set to %d" % field_size_list[field_size_idx])
    # depth_list = [1, 15, 30]
    depth_list = [0, 1, 5, 10, 15, 20, 25, 30]
    half_thickness = 0.3
    input_phsp_dir = os.path.split(input_phsp_path)[0]
    input_phsp_events = int(ReadPhsp.Phsp(input_phsp_path).TotalNumParticles)
    print("Input phsp path: ", input_phsp_dir)
    print("Input phsp total events: ", input_phsp_events)
    new_file_name = os.path.split(input_phsp_dir)[-1].replace('_D60', '')

    for sample in sample_list:
        new_sample_file = os.path.join(beam_path, new_file_name + '.egsinp')
        info_list = [Info(5, 0, input_phsp_path), Info(3, 0, str(input_phsp_events))]
        ModifyFile(sample, new_sample_file, info_list)
        phsp_path = Beam(beam_function, new_sample_file, pegs4)
        phsp_total_events = int(ReadPhsp.Phsp(phsp_path).TotalNumParticles)
        # for idx, field_size in enumerate(field_size_list):
        pdd_new_name = new_file_name + '_PDD' + ".egsinp"
        pdd_new_path = os.path.join(dose_path, pdd_new_name)
        info_list = [Info(19, 0, phsp_path), Info(20, 0, str(phsp_total_events * 100))]
        ModifyFile(pdd_sample_list[field_size_idx], pdd_new_path, info_list)
        Dose(pdd_new_path)

        for depth in depth_list:
            prf_new_name = new_file_name + "_PF%.1f" % depth + ".egsinp"
            prf_new_path = os.path.join(dose_path, prf_new_name)
            print('New File:', prf_new_name)
            z_top = depth - half_thickness
            z_bottom = depth + half_thickness
            info_list = [Info(10, 0, str(z_top)), Info(11, 0, str(z_bottom)), Info(17, 7, str(z_top)),
                         Info(19, 0, str(phsp_total_events)), Info(18, 0, phsp_path)]
            ModifyFile(prf_sample_list[field_size_idx], prf_new_path, info_list)
            Dose(prf_new_path)
    return 0


@CallTiming
def AutoRun4():
    pegs4 = '521icruSW'
    field_size_list = np.array([27])
    beam_IBL_path = r"/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL_SW_EPID"
    beam_IBL_function = r"/home/uih/EGSnrc/egs_home/bin/linux64/BEAM_UIH_IBL_SW_EPID"
    spectrum = r"/home/uih/Data/IBL/Spe/P2.3_SL0.6_R0.6_ME2.300_FWHM1.413_DSP0.614.Spectrum"
    spectrum = r"/home/uih/Data/IBL/Spe/P2.3_SL0.6_R0.6_ME2.300_FWHM1.413_DSP0.614.Spectrum"
    spectrum_name = FileName(spectrum)
    spectrum_char = spectrum_name.split('_')
    IBL_sample_list = [r"/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL_SW_EPID/P2.3_SL0.6_R0.6_ME2.300_FS50_sample.egsinp",
                       r"/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL_SW_EPID/P2.3_SL0.6_R0.6_ME2.300_FS100_sample.egsinp",
                       r"/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL_SW_EPID/P2.3_SL0.6_R0.6_ME2.300_FS270_sample.egsinp"]
    events_list = [100000000, 100000000, 100000000]
    sw_thickness_list = [1, 4, 8, 10, 14, 15, 18, 22, 26, 30]
    score_plane = 0
    sid = 100
    for i, ibl_sample in enumerate(IBL_sample_list):
        for sw_thickness in sw_thickness_list:
            new_beam_name = "FS%d" % field_size_list[i] + "_SW%d" % sw_thickness + ".egsinp"
            new_beam_file = os.path.join(beam_IBL_path, new_beam_name)
            z_min = sid - sw_thickness / 2 - score_plane
            info_list = [Info(3, 0, str(events_list[i])), Info(172, 0, str(z_min)), Info(173, 0, str(sw_thickness))]
            ModifyFile(IBL_sample_list[i], new_beam_file, info_list)
            print(new_beam_file)
            Beam(beam_IBL_function, new_beam_file, pegs4)


@CallTiming
def AutoRun5():
    pegs4 = '521icruSW'
    field_size_list = np.array([27])
    beam_IBL_path = r"/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL_SW_EPID"
    beam_IBL_function = r"/home/uih/EGSnrc/egs_home/bin/linux64/BEAM_UIH_IBL_SW_EPID"
    spectrum_list = AutoProcess(Path(r"/home/uih/IBL/Spe"), [], ".Spectrum")
    Air_sample_list = [
        r"/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL_SW_EPID/P2.3_SL0.6_R0.6_ME2.300_FS270_Air_sample.egsinp"]
    IBL_sample_list = [r"/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL_SW_EPID/P2.3_SL0.6_R0.6_ME2.300_FS270_sample.egsinp"]
    events_list = [50000000]
    sw_thickness_list = [1, 2, 4, 6, 8, 12, 16, 20, 24]
    score_plane = 0
    sid = 100
    for spe in spectrum_list:
        print("Spectrum: ", spe)
        spe_char = FileName(spe).split('_')
        for i, ibl_sample in enumerate(IBL_sample_list):
            for sw_thickness in sw_thickness_list:
                new_beam_name = spe_char[1] + "_FS%d" % field_size_list[i] + "_SW%d" % sw_thickness + ".egsinp"
                new_beam_file = os.path.join(beam_IBL_path, new_beam_name)
                if sw_thickness == 0:
                    info_list = [Info(3, 0, str(events_list[i])), Info(7, 0, str(spe))]
                    ModifyFile(Air_sample_list[i], new_beam_file, info_list)
                else:
                    z_min = sid - sw_thickness / 2 - score_plane
                    info_list = [Info(3, 0, str(events_list[i])), Info(7, 0, str(spe)), Info(172, 0, str(z_min)),
                                 Info(173, 0, str(sw_thickness))]
                    ModifyFile(IBL_sample_list[i], new_beam_file, info_list)
                print(new_beam_file)
                Beam(beam_IBL_function, new_beam_file, pegs4)


def ConeRadiusCalculation(field_size):
    sid = 1000
    field_size_radius = field_size / 2
    cone_height_center = 672.5
    cone_height_field_size = field_size_radius * cone_height_center / sid
    # angle1 = np.arctan(sid / field_size_radius) * 180 / np.pi
    # res_angle1 = 90.0 - angle1
    cone_focus = 1020.0
    cone_down_height = cone_focus - sid + cone_height_center
    # angle2 = np.arctan(cone_down_height / cone_height_field_size) * 180.0 / np.pi
    # res_angle2 = 90.0 - angle2
    cone_up_height = 605.0
    up_radius = cone_height_field_size * (cone_down_height - cone_height_center + cone_up_height) / cone_down_height
    down_radius = cone_height_field_size * (cone_down_height - cone_height_center + 740) / cone_down_height
    return up_radius, down_radius


def AutoRunCone(cone_radius_list):
    beam_function = r"/home/uih/EGSnrc/egs_home/bin/linux64/BEAM_Medium_Cone"
    beam_path = r"/home/uih/EGSnrc/egs_home/BEAM_Medium_Cone"
    dose_path = r"/home/uih/EGSnrc/egs_home/dosxyznrc"
    pegs4 = global_pegs4_path
    beam_sample_list = [r"/home/uih/EGSnrc/egs_home/BEAM_Medium_Cone/Cone5_Block52_Stage0.egsinp",
                        r"/home/uih/EGSnrc/egs_home/BEAM_Medium_Cone/Cone17.5_Block52_Stage0.egsinp",
                        r"/home/uih/EGSnrc/egs_home/BEAM_Medium_Cone/Cone50_Block52_Stage0.egsinp"]

    dose_sample_list = [r"/home/uih/EGSnrc/egs_home/dosxyznrc/inputs/Cone5_Block52_stage0.egsinp",
                        r"/home/uih/EGSnrc/egs_home/dosxyznrc/inputs/Cone17.5_Block52_stage0.egsinp",
                        r"/home/uih/EGSnrc/egs_home/dosxyznrc/inputs/Cone50_Block52_stage0.egsinp"]
    # cone_radius_list = [14.5, 15, 16]
    for idx, cone_radius in enumerate(cone_radius_list):
        info_list = [Info(27, 0, str(cone_radius)), Info(3, 0, str(500000000))]
        new_beam_file = os.path.join(beam_path,
                                     FileName(beam_sample_list[idx]) + "_R%.1f.egsinp" % cone_radius_list[idx])
        ModifyFile(beam_sample_list[idx], new_beam_file, info_list)
        phsp_path = Beam(beam_function, new_beam_file, pegs4)
        phsp_total_events = int(ReadPhsp.Phsp(phsp_path).TotalNumParticles)
        pdd_info_list = [Info(22, 0, phsp_total_events)]
        new_dose_file = os.path.join(dose_path, FileName(new_beam_file) + "_PDD.egsinp")
        ModifyFile(dose_sample_list[idx], new_dose_file, pdd_info_list)
        Dose(new_dose_file, pegs4)


def AutoRunCone2(field_size, cone_radius, cone_up_radius, cone_down_radius):
    BDH_path = r"/home/uih/Data/BDH/BDH.egsphsp1"
    beam_function = r"/home/uih/EGSnrc/egs_home/bin/linux64/BEAM_Medium_Cone"
    beam_path = r"/home/uih/EGSnrc/egs_home/BEAM_Medium_Cone"
    dose_path = r"/home/uih/EGSnrc/egs_home/dosxyznrc"
    pegs4 = global_pegs4_path
    beam_sample = r"/home/uih/EGSnrc/egs_home/BEAM_Medium_Cone/sample/Cone50_Block52_Stage0.egsinp"
    dose_sample = r"/home/uih/EGSnrc/egs_home/dosxyznrc/sample/Cone50_Block52_stage0.egsinp"
    # beam_sample_list = [r"/home/uih/EGSnrc/egs_home/BEAM_Medium_Cone/Cone5_Block52_Stage0.egsinp",
    #                     r"/home/uih/EGSnrc/egs_home/BEAM_Medium_Cone/Cone17.5_Block52_Stage0.egsinp",
    #                     r"/home/uih/EGSnrc/egs_home/BEAM_Medium_Cone/Cone50_Block52_Stage0.egsinp"]

    # dose_sample_list = [r"/home/uih/EGSnrc/egs_home/dosxyznrc/inputs/Cone5_Block52_stage0.egsinp",
    #                     r"/home/uih/EGSnrc/egs_home/dosxyznrc/inputs/Cone17.5_Block52_stage0.egsinp",
    #                     r"/home/uih/EGSnrc/egs_home/dosxyznrc/inputs/Cone50_Block52_stage0.egsinp"]

    bds_radius = field_size
    phsp_events_num = ReadPhsp.Phsp(BDH_path)
    info_list = [Info(3, 0, phsp_events_num), Info(4, 0, str(bds_radius)), Info(27, 0, cone_radius),
                 Info(32, 0, str(cone_up_radius)), Info(33, 0, str(cone_down_radius)), Info(6, 0, BDH_path)]
    new_beam_file = os.path.join(beam_path, "FS%.1f_Block52_Stage0_R%.1f.egsinp" % (field_size * 10, cone_radius))
    ModifyFile(beam_sample, new_beam_file, info_list)
    # phsp_path = Beam(beam_function, new_beam_file, pegs4)
    phsp_path = os.path.join(move2path, FileName(new_beam_file), EGS_rename + ".egsphsp1")
    phsp_total_events = int(ReadPhsp.Phsp(phsp_path).TotalNumParticles)
    new_dose_file = os.path.join(dose_path, FileName(new_beam_file) + "_PRF.egsinp")

    penumbra_bin_width = 0.02
    penumbra_start = np.floor(field_size * 10 / 2 - 2) / 10
    penumbra_stop = np.ceil(field_size * 10 / 2 + 2) / 10
    penumbra_bin_num = int((penumbra_stop - penumbra_start) / penumbra_bin_width + 0.5)
    center_bin_width = 0.1
    center_bin_num = int(penumbra_start * 2 / center_bin_width + 0.5)
    outer_bin_width = 0.5
    outer_bin_num = 4
    total_size = outer_bin_num * outer_bin_width * 2 + center_bin_num * center_bin_width + penumbra_bin_num * penumbra_bin_width * 2
    total_bin_num = penumbra_bin_num * 2 + outer_bin_num * 2 + center_bin_num
    print(outer_bin_num, outer_bin_width)
    print(penumbra_bin_num, penumbra_bin_width, penumbra_start, penumbra_stop)
    print(center_bin_num, center_bin_width)
    print(total_bin_num, total_size)
    assert total_bin_num < 120

    dose_info_list = [Info(22, 0, str(phsp_total_events)), Info(19, 10, str(bds_radius)), Info(21, 0, phsp_path),
                      Info(5, 0, -total_size / 2), Info(6, 0, outer_bin_width), Info(6, 1, outer_bin_num),
                      Info(7, 0, penumbra_bin_width), Info(7, 1, penumbra_bin_num), Info(8, 0, center_bin_width),
                      Info(8, 1, center_bin_num), Info(9, 0, penumbra_bin_width), Info(9, 1, penumbra_bin_num),
                      Info(10, 0, outer_bin_width), Info(10, 1, outer_bin_num), Info(15, 1, total_bin_num)]
    # ModifyFile(dose_sample, new_dose_file, dose_info_list)
    # Dose(new_dose_file, pegs4)


@CallTiming
def AutoRunEPID():
    home_dir = r"/home/uih/Disk1/CBCT20"
    dose_path = r"/home/uih/EGSnrc/egs_home/dosxyznrc"
    # dose_pegs = "521icru+EPID"
    dose_pegs = "521icru_AP16"
    EPID_Model_sample = r"/home/uih/EGSnrc/egs_home/dosxyznrc/EPID_FS27_SW28/EPID_FS27_SW28.egsinp"
    sw_thickness_list = [0, 1, 2, 4, 6, 8, 12, 16, 20, 24, 28]
    # sw_thickness_list = [1, 2, 4, 6, 8, 12, 16]
    # sw_thickness_list = [0, 24, 28]
    for sw_thickness in sw_thickness_list:
        phsp_dir_name = "P2.50_SL0.60_SS0.1_SD0.8_FS27_SW%d" % sw_thickness
        sw_phsp_path = os.path.join(home_dir, phsp_dir_name, "EGS.egsphsp1")
        print(sw_phsp_path)
        phsp_total_events = int(ReadPhsp.Phsp(sw_phsp_path).TotalNumParticles)
        # dose_info_list = [Info(7, 0, sw_phsp_path), Info(8, 0, phsp_total_events)]
        dose_info_list = [
            Info(7, 0, sw_phsp_path), Info(8, 0, phsp_total_events),
            Info(2, 0, "/home/uih/EGSnrc/egs_home/dosxyznrc/EPID_Phantom/EPID_Phantom_AP16_DimX128_DimY128_T0.04_AL0.075.egsphant"),
            Info(21, 0, " Brems angular sampling= KM"), Info(22, 0, " Brems cross sections= NIST"),
            Info(28, 0, " Rayleigh scattering= On"), Info(29, 0, "Atomic relaxations= On"),
            Info(23, 0, " Bound Compton scattering= Norej"), Info(5, 7, '5')
        ]
        new_dose_name = "EPID_" + phsp_dir_name + ".egsinp"
        new_dose_path = os.path.join(dose_path, new_dose_name)
        ModifyFile(EPID_Model_sample, new_dose_path, dose_info_list)
        Dose(new_dose_path, dose_pegs)


@CallTiming
def AutoRunSW(phsp_path):
    pegs4 = '521icruSW'
    beam_SW_path = r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID"
    beam_SW_function = r"/home/uih/EGSnrc/egs_home/bin/linux64/BEAM_SW_EPID"
    dose_path = r"/home/uih/EGSnrc/egs_home/dosxyznrc"
    dose_pegs = "521icru_AP16"
    SW_sample_noDBS_list = [r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/sample/FS5_SW1_sample_nDBS.egsinp",
                            r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/sample/FS10_SW1_sample_nDBS.egsinp",
                            r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/sample/FS27_SW1_sample_nDBS.egsinp"]
    Air_sample_noDBS_list = [r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/sample/FS5_Air_sample_nDBS.egsinp",
                             r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/sample/FS10_Air_sample_nDBS.egsinp",
                             r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/sample/FS27_Air_sample_nDBS.egsinp"]
    # SW_sample_noDBS_list = [r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/sample/FS5_SW1_sample_nDBS_Vacuum.egsinp",
    #                         r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/sample/FS10_SW1_sample_nDBS_Vacuum.egsinp",
    #                         r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/sample/FS27_SW1_sample_nDBS_Vacuum.egsinp"]
    # Air_sample_noDBS_list = [r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/sample/FS5_Air_sample_nDBS_Vacuum.egsinp",
    #                          r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/sample/FS10_Air_sample_nDBS_Vacuum.egsinp",
    #                          r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/sample/FS27_Air_sample_nDBS_Vacuum.egsinp"]
    SW_sample_list = [r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/sample/FS5_SW1_sample_SIM100.egsinp",
                      r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/sample/FS10_SW1_sample_SIM100.egsinp",
                      r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/sample/FS27_SW1_sample_SIM100.egsinp"]
    Air_sample_list = [r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/sample/FS5_Air_sample_SIM100.egsinp",
                       r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/sample/FS10_Air_sample_SIM100.egsinp",
                       r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/sample/FS27_Air_sample_SIM100.egsinp"]
    EPID_Model_sample = r"/home/uih/EGSnrc/egs_home/dosxyznrc/EPID_FS27_SW28/EPID_FS27_SW28.egsinp"
    # sw_thickness_list = [0, 15, 30]
    sw_thickness_list = [0, 1, 5, 10, 15, 20, 25, 30]
    sim_num_list = [i for i in range(len(sw_thickness_list))]
    # sim_num_list = [10, 30, 50]
    score_plane = 60
    sid = 100
    field_size_index = 2
    # phsp_path = r"/home/uih/Disk1/CBCT22/P2.30_SL0.60_SS0.1_SD0.8_FS27_D60/EGS.egsphsp1"
    print('Phsp: ', phsp_path)
    phsp_total_events = int(ReadPhsp.Phsp(phsp_path).TotalNumParticles)
    print("Total events in phsp file: ", phsp_total_events)

    for idx, sw_thickness in enumerate(sw_thickness_list):
        new_beam_name = "_".join(
            os.path.split(os.path.split(phsp_path)[0])[-1].split('_')[:-1] + ["SW%d.egsinp" % sw_thickness])
        new_beam_file = os.path.join(beam_SW_path, new_beam_name)
        if sw_thickness == 0:
            # info_list = [Info(3, 0, str(phsp_total_events)), Info(5, 0, phsp_path), Info(31, 0, "79.9"),
            #              Info(47, 0, "Brems angular sampling= KM"), Info(48, 0, "Brems cross sections= NIST"),
            #              Info(55, 0, "Atomic relaxations= On"), Info(2, 5, str(3))]
            # ModifyFile(Air_sample_noDBS_list[field_size_index], new_beam_file, info_list)
            info_list = [Info(3, 0, str(phsp_total_events)), Info(6, 0, phsp_path), Info(32, 0, "79.9"),
                         Info(48, 0, "Brems angular sampling= KM"), Info(49, 0, "Brems cross sections= NIST"),
                         Info(56, 0, "Atomic relaxations= On"), Info(2, 5, str(3)), Info(4, 0, sim_num_list[idx]), Info(22, 0, 20)]
            ModifyFile(Air_sample_list[field_size_index], new_beam_file, info_list)
        # elif sw_thickness < 0:
        #     z_min = sid - sw_thickness / 2 - score_plane
        #     info_list = [Info(3, 0, str(phsp_total_events)), Info(5, 0, phsp_path), Info(24, 0, str(z_min)),
        #                  Info(25, 0, str(sw_thickness)), Info(31, 0, "79.9"), Info(47, 0, "Brems angular sampling= KM"),
        #                  Info(48, 0, "Brems cross sections= NIST"), Info(55, 0, "Atomic relaxations= On"), Info(2, 5, str(3))]
        #     ModifyFile(SW_sample_noDBS_list[field_size_index], new_beam_file, info_list)
        else:
            z_min = sid - sw_thickness / 2 - score_plane
            info_list = [Info(3, 0, str(phsp_total_events)), Info(6, 0, phsp_path), Info(25, 0, str(z_min)),
                         Info(26, 0, str(sw_thickness)), Info(32, 0, "79.9"), Info(48, 0, "Brems angular sampling= KM"),
                         Info(49, 0, "Brems cross sections= NIST"), Info(56, 0, "Atomic relaxations= On"),
                         Info(4, 0, sim_num_list[idx]), Info(22, 0, 20)]
            ModifyFile(SW_sample_list[field_size_index], new_beam_file, info_list)
        print("EPID: ", new_beam_file)
        sw_phsp_path_old = os.path.join(move2path, os.path.splitext(new_beam_name)[0], EGS_rename + ".egsphsp1")
        if os.path.isfile(sw_phsp_path_old):
            os.remove(sw_phsp_path_old)
        sw_phsp_path = Beam(beam_SW_function, new_beam_file, pegs4)
        # sw_phsp_path = os.path.join(move2path, os.path.splitext(new_beam_name)[0], EGS_rename + ".egsphsp1")
        print("SW phsp path: ", sw_phsp_path)
        # ReadPhspCpp([sw_phsp_path])
        # EPID Dose
        dose_phsp_total_events = int(ReadPhsp.Phsp(sw_phsp_path).TotalNumParticles)
        dose_info_list = [Info(7, 0, sw_phsp_path),
                          Info(8, 0, dose_phsp_total_events * 100),
                          Info(2, 0,
                               "/home/uih/EGSnrc/egs_home/dosxyznrc/EPID_Phantom/EPID_Phantom_AP16_DimX128_DimY128_T0.04_AL0.075.egsphant"),
                          Info(21, 0, " Brems angular sampling= KM"), Info(22, 0, " Brems cross sections= NIST"),
                          Info(28, 0, " Rayleigh scattering= On"), Info(29, 0, "Atomic relaxations= On"),
                          Info(23, 0, " Bound Compton scattering= Norej")]
        new_dose_name = "EPID_" + new_beam_name
        new_dose_path = os.path.join(dose_path, new_dose_name)
        ModifyFile(EPID_Model_sample, new_dose_path, dose_info_list)
        try:
            Dose(new_dose_path, dose_pegs)
        except Exception as err:
            print(err)

def Test():
    pegs = "521icru"
    spectrum = r"D:\Program\EGSnrc\egs_home\BEAM_UIH_IBL\sample\P2.3_SL0.6_R0.6_ME2.300_FWHM1.413_DSP0.614.Spectrum"
    # field_size_list = np.array([5, 10, 27]) * cm
    field_size_list = np.array([5, 10, 27]) * cm
    beam_path = r"D:\Program\EGSnrc\egs_home\BEAM_UIH_IBL"
    beam_function = r"D:\Program\EGSnrc\egs_home\bin\win3264\BEAM_UIH_IBL.exe"
    beam_sample_list = [r"D:\Program\EGSnrc\egs_home\BEAM_UIH_IBL\sample\P2.3_SL0.6_R0.6_ME2.300_FS50_sample.egsinp",
                        r"D:\Program\EGSnrc\egs_home\BEAM_UIH_IBL\sample\P2.3_SL0.6_R0.6_ME2.300_FS100_sample.egsinp",
                        r"D:\Program\EGSnrc\egs_home\BEAM_UIH_IBL\sample\P2.3_SL0.6_R0.6_ME2.300_FS270_sample.egsinp"]

    for idx, bs in enumerate(beam_sample_list):
        new_beam_name = '_'.join(FileName(spectrum).split('_')[:4] + ['FS%d' % field_size_list[idx]]) + '.egsinp'
        new_beam_path = os.path.join(beam_path, new_beam_name)
        info_list = [Info(3, 0, str(300000)), Info(7, 0, spectrum)]
        ModifyFile(bs, new_beam_path, info_list)
        print("Beam input: ", new_beam_path)
        phsp_path = Beam(beam_function, new_beam_path, pegs)
        phsp_total_events = ReadPhsp.Phsp(phsp_path).TotalNumParticles
        print(phsp_total_events)


def TestDose():
    pegs4 = "521icru+EPID"
    # Max energy: 7.5 MeV
    energy_list = [(i + 1) / 1 for i in range(3)] + [i / 1 for i in range(3, 7)]
    sample_input = r"D:\Program\EGSnrc\egs_home\dosxyznrc\EPID_Response_E0.5.egsinp"
    phantom_path = r"F:\Data\EGSnrc\EPID_Phantom\EPID_Phantom_DimX99_DimY99_T0.12.egsphant"
    events_num = 1000000
    for energy in energy_list:
        info_list = [Info(2, 0, phantom_path), Info(7, 0, energy), Info(8, 0, events_num)]
        new_file_name = r"D:\Program\EGSnrc\egs_home\dosxyznrc\EPID_Response_E%.2f.egsinp" % energy
        ModifyFile(sample_input, new_file_name, info_list)
        Dose(new_file_name, pegs4)


@CallTiming
def AutoRunEPIDPDD(input_phsp_path):
    # input
    beam_function = r"/home/uih/EGSnrc/egs_home/bin/linux64/BEAM_RS"
    beam_path = r"/home/uih/EGSnrc/egs_home/BEAM_RS"
    pegs4 = "521icru"
    sample_list = [r"/home/uih/EGSnrc/egs_home/BEAM_RS/sample.egsinp"]
    input_phsp_dir = os.path.split(input_phsp_path)[0]
    new_file_name = os.path.split(input_phsp_dir)[-1].replace('_D60', '')
    new_sample_file = os.path.join(beam_path, new_file_name + '.egsinp')
    input_phsp_events = int(ReadPhsp.Phsp(input_phsp_path).TotalNumParticles)
    info_list = [Info(5, 0, input_phsp_path), Info(3, 0, str(input_phsp_events))]
    ModifyFile(sample_list[0], new_sample_file, info_list)
    phsp_path = Beam(beam_function, new_sample_file, pegs4)

    pegs = '521icruSW'
    egs_input = r"/home/uih/EGSnrc/egs_home/dosxyznrc/IBL_SW_PDD.egsinp"
    phsp_path = r"/home/uih/Disk2/CBCT30/P2.50_SL0.60_SS0.1_SD0.8_FS10/EGS.egsphsp1"
    phsp_events_num = ReadPhsp.Phsp(phsp_path).TotalNumParticles
    Info_list = [Info(19, 0, phsp_events_num), Info(18, 0, phsp_path)]
    new_path = r"/home/uih/EGSnrc/egs_home/dosxyznrc/IBL_SW_PDD_new.egsinp"
    ModifyFile(egs_input, new_path, Info_list)
    Dose(new_path, pegs)

def AutoRunMonoEnergy(energy, source_size, source_dispersion):
    pegs4 = '521icruSW'
    field_size_list = np.array([27])
    beam_IBL_path = r"/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL"
    beam_SW_path = r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID"
    beam_IBL_function = r"/home/uih/EGSnrc/egs_home/bin/linux64/BEAM_UIH_IBL"
    beam_SW_function = r"/home/uih/EGSnrc/egs_home/bin/linux64/BEAM_SW_EPID"
    dose_path = r"/home/uih/EGSnrc/egs_home/dosxyznrc"
    dose_pegs = "521icru_AP16"

    IBL_sample_list = ["/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/Sample/MonoEnergy2.3_SS0.1_SD0.8_NoDBS_FS27_D60.egsinp"]

    SW_sample_list = [r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/sample/FS27_SW1_sample_nDBS.egsinp"]

    Air_sample_list = [r"/home/uih/EGSnrc/egs_home/BEAM_SW_EPID/sample/FS27_Air_sample_nDBS.egsinp"]

    EPID_Model_sample = r"/home/uih/EGSnrc/egs_home/dosxyznrc/EPID_FS27_SW28/EPID_FS27_SW28.egsinp"
    sw_thickness_list = [0, 1, 5, 10, 15, 20, 25, 30]
    score_plane = 60
    sid = 100
    for i, ibl_sample in enumerate(IBL_sample_list):
        # sample_name = FileName(ibl_sample)
        # sample_char = sample_name.split('_')
        # info_list = [Info(4, 2, str(source_size)), Info(4, 7, str(source_size)), Info(4, 6, str(source_dispersion)),
        #              Info(6, 0, energy), Info(3, 0, str(30000000000)), Info(22, 0, 0.335), Info(26, 0, 0.78)]
        # new_file_name = '_'.join(
        #     [spectrum_char[0], spectrum_char[1], spectrum_char[2], spectrum_char[3], spectrum_char[4], "SS%.1f" % source_size, "SD%.1f" % source_dispersion, sample_char[-1], "D60"]) + '.egsinp'
        # new_file_name = '_'.join(
        #     [spectrum_char[0], spectrum_char[1], spectrum_char[4].replace('FWHM', 'F'), "SS%.2f" % source_size, "SD%.1f" % source_dispersion, sample_char[-1], "D60"]) + '.egsinp'
        # new_file_name = '_'.join(
        #     ["MonoEnergy%.2f" % energy, "SS%.1f" % source_size, "SD%.1f" % source_dispersion,
        #      'FS%d' % SearchByKey('FS', sample_name)[0], "D%d" % score_plane]) + '.egsinp'
        # new_file_path = os.path.join(beam_IBL_path, new_file_name)
        # print('IBL: ', new_file_path)
        # ModifyFile(ibl_sample, new_file_path, info_list)
        phsp_path = "/home/uih/Disk2/Test/MonoEnergy%.2f_SS0.1_SD0.8_FS27_D60/EGS.egsphsp1" % energy
        # phsp_path = Beam(beam_IBL_function, new_file_path, pegs4)
        if not os.path.isfile(phsp_path):
            print("Phsp file not exists. Continue Next!")
            continue
        print('Phsp: ', phsp_path)
        phsp_total_events = int(ReadPhsp.Phsp(phsp_path).TotalNumParticles)
        print("Total events in phsp file: ", phsp_total_events)
        # try:
        #     AutoRun3WT(phsp_path)
        # except Exception as err:
        #     print("Water Tank data produce failed.")
        #     print(err)
        try:
            AutoRunSW(phsp_path)
        except Exception as err:
            print("Solid Water data produce failed.")


@CallTiming
def MonoEnergyMain():
    energy_list = [0.5 + i * 0.5 for i in range(6)]
    # energy_list = [3.0]
    source_size = 0.1
    source_dispersion = 0.8
    for energy in energy_list:
        AutoRunMonoEnergy(energy, source_size, source_dispersion)


@CallTiming
def Main():
    # spe_dir = Path(R"/home/uih/Data/IBL/Spe")
    spe = r"/home/uih/Data/IBL/Spe/P2.60_SL0.60_R0.60_ME2.600_FWHM1.413_DSP0.543.Spectrum"
    source_size = 0.1
    source_dispersion = 0.8
    AutoRun3(spe, source_size, source_dispersion)
    # AutoRunSW()
    # for spe in spe_dir.iterdir():
    #     if spe.is_file() and spe.suffix == ".Spectrum":
    #         AutoRun3(spe.as_posix(), source_size, source_dispersion)

@CallTiming
def AutoTBL(sample_file):
    pegs = '521icru'
    beam_exec = R"/home/uih/EGSnrc/egs_home/bin/linux64/BEAM_UIH_6MV"
    spe = R"/home/uih/EGSnrc/egs_home/BEAM_UIH_6MV/Peak6.8ES1111.Spectrum"
    events_number = 6000000000
    sample_file = Path(sample_file)
    # samplt_file = R"/home/uih/EGSnrc/egs_home/BEAM_UIH_6MV/FF_JAW14x20_MLC3.5_3.0_Sample.egsinp"
    info_list = [Info(7, 0, spe), Info(3, 0, str(events_number))]
    # info_list = [Info(6, 0, spe), Info(3, 0, str(events_number))]
    new_file =  sample_file.with_name("MTP_" + sample_file.name)
    ModifyFile(sample_file, new_file, info_list)
    phsp =  Beam(beam_exec, new_file, pegs)
    print(phsp)
    "/home/uih/Disk2/TBL/TBL_Head_Score20/EGS_w1_EnergyNorm.egsphsp1"


@CallTiming
def AutoTBLEPID(sw_phsp_path):
    pegs = '521icru_AP16'
    EPID_Model_sample = r"/home/uih/EGSnrc/egs_home/dosxyznrc/TBL_AP16_Jaw14x20_MLC1.egsinp"
    dose_path = r"/home/uih/EGSnrc/egs_home/dosxyznrc"
    # sw_phsp_path = R"/home/uih/Disk2/TBL/TBL_test/EGS.egsphsp1"
    sw_phsp_path = Path(sw_phsp_path)

    phsp_total_events = int(os.path.getsize(sw_phsp_path.as_posix()) / 28 -1) * 100

    dose_info_list = [
        Info(7, 0, sw_phsp_path.as_posix()), Info(8, 0, phsp_total_events),
        Info(2, 0,
             "/home/uih/EGSnrc/egs_home/dosxyznrc/EPID_Phantom/EPID100_Phantom_AP16_DimX128_DimY128_T0.08_AL0.075.egsphant"),
        Info(5, 7, '5'),
        Info(5, 4, '95'),
        # Info(21, 0, " Brems angular sampling= KM"), Info(22, 0, " Brems cross sections= NIST"),
        # Info(28, 0, " Rayleigh scattering= On"), Info(29, 0, "Atomic relaxations= On"),
        # Info(23, 0, " Bound Compton scattering= Norej")
    ]
    new_name = sw_phsp_path.parent.name
    new_file_name = os.path.join(dose_path, "EPID_" + new_name + ".egsinp")
    print("New Name: ", new_file_name)
    ModifyFile(EPID_Model_sample, new_file_name, dose_info_list)
    Dose(new_file_name, pegs)


@CallTiming
def AutoTBL2():
    pegs = '521icru'
    beam_exec = R"/home/uih/EGSnrc/egs_home/bin/linux64/BEAM_UIH_6MV"
    spe = R"/home/uih/EGSnrc/egs_home/BEAM_UIH_6MV/Peak6.8ES1111.Spectrum"
    events_number = 40000000000
    sample_file = R"/home/uih/EGSnrc/egs_home/BEAM_UIH_6MV/TBL_FF_JAW20x20_MLC48_SSD95.egsinp"
    # info_list = [Info(3, 0, str(events_number))]
    info_list = [Info(6, 0, spe), Info(3, 0, str(events_number))]
    new_file =  Path(sample_file).with_name("MT_TBL_FF_JAW20x20_MLC48_SSD95.egsinp")
    ModifyFile(sample_file, new_file, info_list)
    phsp =  Beam(beam_exec, new_file, pegs)
    print(phsp)


@CallTiming
def AutoTBL3(phsp_file):
    pegs = '521icru'
    beam_exec = R"/home/uih/EGSnrc/egs_home/bin/linux64/BEAM_UIH_6MV"
    phsp_file = Path(phsp_file)
    # spe = R"/home/uih/EGSnrc/egs_home/BEAM_UIH_6MV/Peak6.8ES1111.Spectrum"
    # phsp_file = R"/home/uih/Disk2/TBL/TBL_Head_Score20/EGS_EnergyNorm.egsphsp1"
    phsp_events = int(os.path.getsize(phsp_file.as_posix()) / 28 -1) * 20
    # phsp_events = 10000000
    # events_number = 600000000
    sample_file = R"/home/uih/EGSnrc/egs_home/BEAM_UIH_6MV/SSD20_Jaw14x20_MLC2.0.egsinp"
    new_file = Path(sample_file).with_name(phsp_file.parent.name + "_" + phsp_file.with_suffix('').name + ".egsinp")
    print("New Name:", new_file)
    info_list = [Info(3, 0, str(phsp_events)), Info(5, 0, phsp_file)]
    # info_list = [Info(6, 0, spe), Info(3, 0, str(events_number))]
    # new_file =  Path(samplt_file).with_name("MeanEnergyNorm3.egsinp")
    ModifyFile(sample_file, new_file, info_list)
    phsp =  Beam(beam_exec, new_file, pegs)
    print(phsp)


def AutoRunSourceToScore():
    pegs = '521icru'
    beam_exec = R"/home/uih/EGSnrc/egs_home/bin/linux64/BEAM_SourceToScore"
    # spe = R"/home/uih/EGSnrc/egs_home/BEAM_UIH_6MV/Peak6.8ES1111.Spectrum"
    events_number = 1_500_000_000
    sample_file = R"/home/uih/EGSnrc/egs_home/BEAM_SourceToScore/PointSourceToScore20cm.egsinp"
    info_list = [Info(3, 0, str(events_number))]
    # info_list = [Info(6, 0, spe), Info(3, 0, str(events_number))]
    new_file = Path(sample_file).with_name("MT_PointSourceToScore20cm.egsinp")
    ModifyFile(sample_file, new_file, info_list)
    phsp = Beam(beam_exec, new_file, pegs)
    print(phsp)


def Auto_TBL_FFF():
    pegs = '521icru'
    beam_exec = R"/home/uih/EGSnrc/egs_home/bin/linux64/BEAM_UIH_6MV"
    spe = R"/home/uih/EGSnrc/egs_home/BEAM_UIH_6MV/Peak6.8ES1111.Spectrum"
    events_number = 100000000
    # sample_file = R"/home/uih/EGSnrc/egs_home/BEAM_UIH_6MV/TBL_FFF6101_JAW40_MLC40_SSD95_E6.8S1.9A0.4.egsinp"
    sample_file = R"/home/uih/EGSnrc/egs_home/BEAM_UIH_6MV/TBL_FF_JAW2x2_sample.egsinp"
    #
    info_list = [Info(3, 0, str(events_number)), Info(7, 0, spe)]
    # info_list = [Info(6, 0, spe), Info(3, 0, str(events_number))]
    new_file = Path(sample_file).with_name("TBL_FF_JAW2x2_SSD95.egsinp")
    ModifyFile(sample_file, new_file, info_list)
    phsp = Beam(beam_exec, new_file, pegs)
    print(phsp)


def AutoRunEPIDResponse():
    pegs4 = "521icru_AP16"
    # Max energy: 7.5 MeV
    # energy_list = [(i + 1) * 0.01 for i in range(0, 50)] + [i/10 for i in range(30, 100)]
    energy_list = np.concatenate((np.arange(0.01, 0.5, 0.01), np.arange(0.5, 3.0, 0.1), np.arange(3.0, 12.5, 0.5)))
    angle_list = np.arange(0, 61, 5)
    # angle_list = [0]
    print("Energy Number", len(energy_list))
    print("Angle Number: ", len(angle_list))
    sample_input = r"/home/uih/EGSnrc/egs_home/dosxyznrc/EPID_Response_Ele_E0.5_Sample.egsinp"
    phantom_path_list = [
        R"/home/uih/EGSnrc/egs_home/dosxyznrc/EPID_Phantom/EPID_Phantom_AP16_DimX101_DimY101_T0.04_AL0.075.egsphant",
        R"/home/uih/EGSnrc/egs_home/dosxyznrc/EPID_Phantom/EPID_Phantom_AP16_DimX101_DimY101_T0.04_AL0.075.egsphant"
        ]
    events_num = 100000
    particle_list = [0, -1]
    for ip, particle in enumerate(particle_list):
        if 0 == ip:
            continue
        phantom_path = phantom_path_list[ip]
        for energy in energy_list:
            # if energy < 0.599:
            #     continue
            for angle in angle_list:
                info_list = [Info(2, 0, phantom_path), Info(5, 0, particle), Info(5, 5, 180 - angle), Info(7, 0, energy), Info(8, 0, events_num)]
                new_file_name = R"/home/uih/EGSnrc/egs_home/dosxyznrc/EPID_C%d_E%.2f_A%d.egsinp" % (particle, energy, angle)
                print(new_file_name)
                ModifyFile(sample_input, new_file_name, info_list)
                Dose(new_file_name, pegs4)

@CallTiming
def AutoDose():
    dose_path = R"/home/uih/EGSnrc/egs_home/dosxyznrc/TBL_FF_Profile25x25_D0.2mm_sample.egsinp"
    phsp_path = R"/home/uih/Disk2/TBL/Tra5/EGS.egsphsp1"
    events = int(os.path.getsize(phsp_path) / 28 -1)
    # events = 10000
    pegs = "521icru"
    depth_list = [1.5, 5, 20]
    # depth_list = [1.5]
    circle_num = 10
    for depth in depth_list:
        dose_new_file = R"/home/uih/EGSnrc/egs_home/dosxyznrc/TBL_FF_Profile25x25_D0.2mm_Depth%.1f.egsinp" % depth
        info_list = [
            Info(17, 0, phsp_path),
            Info(18, 0, events * circle_num),
            Info(9, 0, depth - 0.2),
            Info(10, 0, depth + 0.2),
            Info(16, 7, depth - 0.2),
            Info(18, 11, circle_num),
            Info(18, 14, 5)
        ]
        ModifyFile(dose_path, dose_new_file, info_list)
        Dose(dose_new_file, pegs)

def AutoDose2():
    dose_path = R"/home/uih/EGSnrc/egs_home/dosxyznrc/TBL_FF_Profile25x25_D0.2mm_sample_libhead.egsinp"
    # phsp_path = R"/home/uih/Disk2/TBL/MT_TBL_FF_JAW20x20_MLC48_SSD95/EGS.egsphsp1"
    # events = int(os.path.getsize(phsp_path) / 28 -1)
    events = 100000000
    pegs = "521icru"
    depth_list = [1.5, 5, 20]
    # depth_list = [1.5]
    # circle_num = 10
    for depth in depth_list:
        dose_new_file = R"/home/uih/EGSnrc/egs_home/dosxyznrc/TBL_FF_Profile25x25_D0.2mm_Depth%.1f.egsinp" % depth
        info_list = [
            Info(9, 0, depth - 0.2),
            Info(10, 0, depth + 0.2),
            Info(16, 7, depth - 0.2),
            Info(18, 0, events),
            # Info(18, 11, circle_num),
            Info(18, 14, 5)
        ]
        ModifyFile(dose_path, dose_new_file, info_list)
        Dose(dose_new_file, pegs)

def Transport():
    pegs = '521icru_AP16'
    beam_exec = R"/home/uih/EGSnrc/egs_home/bin/linux64/BEAM_Transport"
    phsp_path = R"/home/uih/Disk2/TBL/MT_TBL_FF_JAW20x20_MLC48_SSD95/EGS.egsphsp1"
    events_number = int(os.path.getsize(phsp_path) / 28 - 1)
    sample_file = R"/home/uih/EGSnrc/egs_home/BEAM_Transport/Transport5cm.egsinp"
    #
    info_list = [Info(3, 0, str(events_number)), Info(5, 0, phsp_path)]
    # info_list = [Info(6, 0, spe), Info(3, 0, str(events_number))]
    new_file = Path(sample_file).with_name("Tra5.egsinp")
    ModifyFile(sample_file, new_file, info_list)
    phsp = Beam(beam_exec, new_file, pegs)
    print(phsp)
    return str(phsp)


def MRL_MLC():
    field_list = [5, 10, 20]
    pegs='521icru'
    beam_exec = R"/home/uih/EGSnrc/egs_home/bin/linux64/BEAM_UIH_MRL"
    # sample_input = R"/home/uih/EGSnrc/egs_home/BEAM_UIH_MRL/MLC_Test.egsinp"
    sample_input = R"/home/uih/EGSnrc/egs_home/BEAM_UIH_MRL/MLC_Test_Thickness9cm.egsinp"
    events = 10000000000
    for field in field_list:
        field_value = 362 * field / 1435
        info_list = [Info(3, 0, events), Info(190, 0, "%.2f" % (-field_value, )), Info(190, 1, "%.2f" % (field_value, ))]
        new_input = R"/home/uih/EGSnrc/egs_home/BEAM_UIH_MRL/MLC9cm_OPT_FD%.1f.egsinp" % field
        ModifyFile(sample_input, new_input, info_list)
        phsp = Beam(beam_exec, new_input, pegs)
        # phsp = R"/home/uih/Disk2/TBL/MLC_OPT_FD%.1f/EGS.egsphsp1" % field
        if not os.path.isfile(phsp):
            print("Phsp File doesn't not exist: %s" % phsp)
            continue
        phsp_events = int(os.path.getsize(phsp) / 28 - 1)
        dose_sample_input = R"/home/uih/EGSnrc/egs_home/dosxyznrc/MRL_ProfileX_D1.5cm.egsinp"
        new_dose_input = R"/home/uih/EGSnrc/egs_home/dosxyznrc/MRL9cm_ProfileX_FD%.1f_D1.5cm.egsinp" % field
        circle_num = 10
        dose_info_list = [Info(18, 0, phsp_events * circle_num), Info(17, 0, phsp)]
        ModifyFile(dose_sample_input, new_dose_input, dose_info_list)
        Dose(new_dose_input, pegs)


def MRL_MLC8cm():
    field_list = [5, 10, 20, 40]
    pegs='521icru'
    beam_exec = R"/home/uih/EGSnrc/egs_home/bin/linux64/BEAM_UIH_MRL"
    # sample_input = R"/home/uih/EGSnrc/egs_home/BEAM_UIH_MRL/MLC_Test.egsinp"
    sample_input = R"/home/uih/EGSnrc/egs_home/BEAM_UIH_MRL/MLC_Test_Thickness9cm.egsinp"
    events = 20000000000
    for field in field_list:
        # field_value = 362 * field / 1435
        # info_list = [Info(3, 0, events), Info(190, 0, "%.2f" % (-field_value, )), Info(190, 1, "%.2f" % (field_value, ))]
        # new_input = R"/home/uih/EGSnrc/egs_home/BEAM_UIH_MRL/MLC9cm_OPT_FD%.1f.egsinp" % field
        # ModifyFile(sample_input, new_input, info_list)
        # phsp = Beam(beam_exec, new_input, pegs)
        phsp = R"/home/uih/Disk2/TBL/MLC_OPT_FD%.1f/EGS.egsphsp1" % field
        if not os.path.isfile(phsp):
            print("Phsp File doesn't not exist: %s" % phsp)
            continue
        phsp_events = int(os.path.getsize(phsp) / 28 - 1)
        dose_sample_input = R"/home/uih/EGSnrc/egs_home/dosxyznrc/MRL_ProfileX_D1.5cm.egsinp"
        new_dose_input = R"/home/uih/EGSnrc/egs_home/dosxyznrc/MRL_ProfileX_FD%.1f_D1.5cm.egsinp" % field
        circle_num = 10
        dose_info_list = [Info(18, 0, phsp_events * circle_num), Info(17, 0, phsp)]
        ModifyFile(dose_sample_input, new_dose_input, dose_info_list)
        Dose(new_dose_input, pegs)

def MLC_Scatter():
    pegs = '521icru'
    beam_exec = R"/home/uih/EGSnrc/egs_home/bin/linux64/BEAM_UIH_6MV"
    spe = R"/home/uih/EGSnrc/egs_home/BEAM_UIH_6MV/Peak6.8ES1111.Spectrum"
    events_number = 1000000000
    sample_file_list = [
        R"/home/uih/EGSnrc/egs_home/BEAM_UIH_6MV/TBL_FFF_MLC5x5_sample.egsinp",
        R"/home/uih/EGSnrc/egs_home/BEAM_UIH_6MV/TBL_FFF_MLC5x5_Finger_sample.egsinp"
    ]
    for sample_file in sample_file_list:
        sample_file = Path(sample_file)
        # info_list = [Info(3, 0, str(events_number))]
        info_list = [Info(7, 0, spe), Info(3, 0, str(events_number))]
        new_file = sample_file.with_name('MT_' + sample_file.name.replace('_sample', ''))
        ModifyFile(sample_file, new_file, info_list)
        print(new_file)
        phsp = Beam(beam_exec, new_file, pegs)
        print(phsp)
        
        
@CallTiming
def AutoRun6(spectrum, source_size, source_dispersion, target_thickness=0.78):
    pegs4 = '521icruSW'
    field_size_list = np.array([5, 10, 27, 40])
    beam_IBL_path = r"/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL"
    beam_IBL_function = r"/home/uih/EGSnrc/egs_home/bin/linux64/BEAM_UIH_IBL"
    spectrum_name = FileName(spectrum)
    spectrum_char = spectrum_name.split('_')
    print('Spectrum', spectrum)
    # IBL_sample_list = [r"/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/IBL_Spetrum2.3_FS5.egsinp",
    #                    r"/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/IBL_Spetrum2.3_FS10.egsinp",
    #                    r"/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/IBL_Spetrum2.3_FS27.egsinp"]

    # IBL_sample_list = [r"/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/IBL_Spetrum2.3_Target0.67_FS5.egsinp",
    #                    r"/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/IBL_Spetrum2.3_Target0.67_FS10.egsinp",
    #                    r"/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/IBL_Spetrum2.3_Target0.67_FS27.egsinp"]
    # IBL_sample_list = ["/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/Sample/P2.3_SL0.6_SS0.1_SD0.8_FS5_D60.egsinp",
    #                    "/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/Sample/P2.3_SL0.6_SS0.1_SD0.8_FS10_D60.egsinp",
    #                    "/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/Sample/P2.3_SL0.6_SS0.1_SD0.8_FS27_D60.egsinp"]
    IBL_sample_list = ["/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/Sample/P2.3_SL0.6_SS0.1_SD0.8_NoDBS_FS5_D60.egsinp",
                       "/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/Sample/P2.3_SL0.6_SS0.1_SD0.8_NoDBS_FS10_D60.egsinp",
                       "/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/Sample/P2.3_SL0.6_SS0.1_SD0.8_NoDBS_FS27_D60.egsinp",
                       "/home/uih/EGSnrc/egs_home/BEAM_UIH_IBL/Sample/P2.3_SL0.6_SS0.1_SD0.8_NoDBS_FS40_D60.egsinp"]

    score_plane = 60
    sid = 100
    beam_RS_path = R"/home/uih/EGSnrc/egs_home/BEAM_RS"
    beam_RS_function = R"/home/uih/EGSnrc/egs_home/bin/linux64/BEAM_RS"
    pegs4_RS = "521icru"
    sample_RS_list = [R"/home/uih/EGSnrc/egs_home/BEAM_RS/sample.egsinp"]
    for i, ibl_sample in enumerate(IBL_sample_list):
        if i != 1:
            continue
        sample_name = FileName(ibl_sample)
        # sample_char = sample_name.split('_')
        info_list = [Info(4, 2, str(source_size)), Info(4, 7, str(source_size)), Info(4, 6, str(source_dispersion)),
                     Info(6, 0, spectrum), Info(3, 0, str(10000000000)), Info(23, 0, 0.335), Info(27, 0, target_thickness)]
        # new_file_name = '_'.join(
        #     [spectrum_char[0], spectrum_char[1], "SS%.1f" % source_size, "SD%.1f" % source_dispersion,"Ta%.2f"%target_thickness,
        #      'FS%d' % SearchByKey('FS', sample_name)[0], "D%d" % score_plane]) + '.egsinp'
        new_file_name = FileName(spectrum) + "_SS%.1f_SD%.1f_Ta%.2f_FS%d_D%d.egsinp" % (source_size, source_dispersion, target_thickness, SearchByKey('FS', sample_name)[0], score_plane)
        new_file_path = os.path.join(beam_IBL_path, new_file_name)
        print('IBL: ', new_file_path)
        ModifyFile(ibl_sample, new_file_path, info_list)
        phsp_path = Beam(beam_IBL_function, new_file_path, pegs4)
        # phsp_path = os.path.join(move2path, FileName(new_file_path), 'EGS.egsphsp1')
        print("Phsp: ", phsp_path)
        if not os.path.isfile(phsp_path):
            print("Phsp file not exists. Continue Next!")
            continue
        print('Phsp: ', phsp_path)
        phsp_total_events = int(ReadPhsp.Phsp(phsp_path).TotalNumParticles)
        print("Total events in phsp file: ", phsp_total_events)
        input_phsp_path = phsp_path
        new_RS_sample_file = os.path.join(beam_RS_path, new_file_name.replace("_D60", ""))
        info_list = [Info(5, 0, input_phsp_path), Info(3, 0, str(phsp_total_events))]
        ModifyFile(sample_RS_list[0], new_RS_sample_file, info_list)
        RS_phsp_path = Beam(beam_RS_function, new_RS_sample_file, pegs4_RS)
        AutoRunWT(RS_phsp_path)


def MRL_IBL_PDD():
    source_size = 0.1
    source_dispersion = 0.8
    spetrum_home = R"/home/uih/Data/MRL/IBL_Spectrum/ME%.1fMeV.spectrum"
    energy_list = [1.5, 1.7, 1.9, 2.1, 2.3, 2.5]
    for energy in energy_list:
        spectrum_path = spetrum_home % energy
        if not os.path.isfile(spectrum_path):
            print("Nonexisted File: ", spectrum_path)
            continue
        for target_thickness in [0.38, 0.48, 0.58, 0.68, 0.78]:
            AutoRun6(spectrum_path, source_size, source_dispersion, target_thickness)


if __name__ == "__main__":
    AutoRunEPIDResponse()
   