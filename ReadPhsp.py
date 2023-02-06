# -*- coding: utf-8 -*-
"""
Created on Thu Jan 05 15:41:52 2020

@author: fuwei.zhao
"""

import struct
import math
import matplotlib.pyplot as plt
from datetime import datetime
import numpy as np
import sys
import os
import re
import scipy.interpolate as spi
from scipy import optimize
from pathlib2 import Path
from multiprocessing import Pool, cpu_count
from subprocess import check_call, CalledProcessError, Popen

def Cut(data, start, width):
    if not isinstance(data, int):
        print("Input is not int.")
        return
    cut_data = data >> start
    cut_data = cut_data % 2**width
    return cut_data


def Int2Binary(data, width):
    BASE=2
    quotient = data
    binstr=['0']*width
    for i in range(width):
        remainder = quotient%BASE
        quotient = quotient>>1
        binstr[width-i-1] = str(remainder)
    binstr=''.join(binstr)
    return binstr


class PhspVector:
    def __init__(self, PID, LATCH, Energy, X, Y, U, V, WT, ZLast=0):
        self.LATCH = LATCH
        self.PID = PID
        self.Bremsstrahlung = Cut(self.LATCH, 0, 1)
        self.InteractiveRegion = Cut(self.LATCH, 1, 23)
        self.SecondaryParticle = Cut(self.LATCH, 24, 5)
        self.Charge = Cut(self.LATCH, 29, 2)
        self.MultiScore = Cut(self.LATCH, 31, 1)
        self.ZLast = ZLast
        if Energy < 0:
            self.Energy = -Energy
        else:
            self.Energy = Energy
        self.X = X
        self.Y = Y
        self.U = U
        if not -1 <= self.U <= 1:
            print('NO.{:8d}:U is wrong:{:8.3f}'.format(self.PID, self.U))
            raise AssertionError
        self.V = V
        if not -1 <= self.V <= 1:
            print('NO.{:8d}:V is wrong:{:8.3f}'.format(self.PID, self.V))
            raise AssertionError
        self.W = math.sqrt(1 - U ** 2 - V ** 2)
        self.WT = WT
        if not 0 <= self.WT <= 1:
            print('NO.{:8d}:WT is wrong:{:8.3f}'.format(self.PID, self.WT))
            raise AssertionError
        self.R = math.sqrt(X ** 2 + Y ** 2)

    def ShowTitle(self):
        print(
            "{:^12} |{:^1}|{:^2}|{:^5}|{:^23}|{:^1}"
            "|{:^8}|{:^8}|{:^8}|{:^8}|{:^8}|{:^8}|{:^10}|".format("ParticleID", "P", "Q", "SecP",
                                                                  "Interactive Region", "B",
                                                                  "X", "Y", "U", "V", "W", "Energy", "Weight"))

    def Show(self):
        print(
            "{:>12} |{:^1}|{:^2}|{:^5}|{:^23}|{:^1}|{:>8.3f}|{:>8.3f}|{:>8.3f}|{:>8.3f}|{:>8.3f}|{:>8.3f}|{:>10.3e}|".format(self.PID, Int2Binary(self.MultiScore, 1), Int2Binary(self.Charge, 2), Int2Binary(self.SecondaryParticle, 5), Int2Binary(self.InteractiveRegion, 23), Int2Binary(self.Bremsstrahlung, 1), self.X, self.Y, self.U, self.V, self.W, self.Energy, self.WT))


class Phsp:
    def __init__(self, filename):
        self.FileName = filename
        with open(filename, 'rb') as fid:
            self.Mode = str(struct.unpack('5s', fid.read(5))[0])[2:-1]
            self.TotalNumParticles = struct.unpack('I', fid.read(4))[0]
            self.PhotonNumParticles = struct.unpack('I', fid.read(4))[0]
            self.ElectronNumber = self.TotalNumParticles - self.PhotonNumParticles
            self.MaxKineticEnergy = struct.unpack('f', fid.read(4))[0]
            self.MinKineticEnergy = struct.unpack('f', fid.read(4))[0]
            self.NumIncidentElectron = struct.unpack('f', fid.read(4))[0]
            if self.Mode == 'MODE2':
                temp = fid.read(7)
                self.offset = 32
            elif self.Mode == 'MODE0':
                temp = fid.read(3)
                self.offset = 28
        self.MAXBuffer = 1000000
        # self.PriEnergyMap = EnergyMap()
        # self.SecEnergyMap = EnergyMap()
        # self.ThiEnergyMap = EnergyMap()
        self.startTime = datetime.now()
        self.stopTime = datetime.now()

    def GetInfo(self):
        info = self.FileName + "\n"
        info += "\tIncident Electron Number: %d\n" % self.NumIncidentElectron
        info += "\tTotal Particle Number: %d\n" % self.TotalNumParticles
        info += "\tPhoton Number: %d\n" % self.PhotonNumParticles
        info += "\tElectron Number: %d\n" % self.ElectronNumber
        return info

    def Loop(self, startID=1, stopID=-1, ptype='ope+-'):
        ptypebin = []
        if 'p' in ptype:
            ptypebin.append(0)
        if 'e+-' in ptype:
            ptypebin.append(2)
            ptypebin.append(1)
        elif 'e-' in ptype:
            ptypebin.append(2)
        elif 'e+' in ptype:
            ptypebin.append(1)
        if 'o' in ptype:
            ptypebin.append(3)
        if len(ptypebin) == 0:
            print("No matched particle type.")
            return 0
        In_InteractiveRegion=[int('00000000000000000000001', 2), int('00000000000001100000001', 2), int('00000000000001000000001', 2)]
        In_SecondaryParticle=[int('00001', 2)]
        In_MultiScore=[int('0', 2)]
        In_Bremsstrahlung=[int('1', 2)]
        if stopID == -1:
            stopID = self.MAXBuffer
        phspList = []
        IDoffset = (startID - 1) * self.offset
        with open(self.FileName, 'rb') as fid:
            fid.seek(self.offset + IDoffset, 0)
            if startID > self.TotalNumParticles:
                print("Start ID excessed the max particle number.")
                return []
            for i in range(min(self.TotalNumParticles - startID + 1, self.MAXBuffer, stopID - startID + 1)):
                LATCH = struct.unpack('i', fid.read(4))[0]
                Energy, X, Y, U, V, WT = struct.unpack('6f', fid.read(24))
                if self.Mode =='MODE0':
                    p = PhspVector(i + startID, LATCH, Energy, X, Y, U, V, WT)
                elif self.Mode =='MODE2':
                    ZLast=struct.unpack('f', fid.read(4))[0]
                    p = PhspVector(i + startID, LATCH, Energy, X, Y, U, V, WT, ZLast)
                # if p.Charge in ptypebin and p.SecondaryParticle in In_SecondaryParticle and p.InteractiveRegion in In_InteractiveRegion:
                if p.Charge in ptypebin:
                    phspList.append(p)
                    # if p.InteractiveRegion == In_InteractiveRegion[0]:
                    #     self.PriEnergyMap.Deposite(p)
                    # else:
                    #     self.SecEnergyMap.Deposite(p)
                    #
                    # self.ThiEnergyMap.Deposite(p)
                    # elif p.InteractiveRegion == int('00000000000001100000001', 2):
                    #     self.SecEnergyMap.Deposite(p)
                if i+startID % 100000 == 1 or i+startID == self.TotalNumParticles:
                    self.stopTime = datetime.now()
                    percent = (i + startID) / self.TotalNumParticles
                    timedelta = (self.stopTime-self.startTime).seconds
                    print("Proceeding {:8.2%}, time used:{:4d} seconds, rest time:{:6.1f} seconds".format(percent, timedelta, (1-percent)*timedelta/percent), end='\r', flush=True)
                    if i+startID == self.TotalNumParticles:
                        print("\nDone.")
        return phspList

    def Show(self, phspList, pNum=0, printout=True):
        if len(phspList) > 0:
            phspList[0].ShowTitle()
        for i, p in enumerate(phspList):
            if printout:
                p.Show()
        return pNum

    def TotalLoop(self, ptype='ope+-'):
        LoopNum = math.ceil(self.TotalNumParticles / self.MAXBuffer)
        # self.EnergyFluence.reset()
        self.startTime = datetime.now()
        targetevents=0
        for i in range(LoopNum):
            phspList = self.Loop(i * self.MAXBuffer + 1, (i + 1) * self.MAXBuffer, ptype)
            targetevents = targetevents + len(phspList)
            #pNum = self.show(phspList, ptype, pNum, i, printout=False)
        # self.EnergyFluence.show()
        self.stopTime = datetime.now()
        # self.PriEnergyMap.Show()
        # self.SecEnergyMap.Show()
        # self.ThiEnergyMap.Show()
        print("Total target particles:{:8d}".format(targetevents))
        print("Total time: {:d} seconds".format((self.stopTime-self.startTime).seconds))


class EnergyMap:
    def __init__(self, XSize = 512, YSize = 512, XMax = 20.48, XMin = -20.48, YMax = 20.48, YMin = -20.48):
        self.XSize = XSize
        self.YSize = YSize
        self.XMax = XMax
        self.XMin = XMin
        self.YMax = YMax
        self.YMin = YMin
        self.XRes = (self.XMax - self.XMin) / self.XSize
        self.YRes = (self.YMax - self.YMin) / self.YSize
        self.Fluence = np.zeros([self.XSize, self.YSize])
        self.EnergyFluence = np.zeros([self.XSize, self.YSize])
        self.Response = np.zeros([self.XSize, self.YSize])
        self.ipo3 = 0
        self.Statistics = 0
        self.EnergyResponse(r"E:\工作文档\资料\EGS\DetectorResponse.txt")

    def Deposite(self, p):
        if not isinstance(p, PhspVector):
            print("Unexpected input type.")
            return
        if self.XMin < p.X < self.XMax and self.YMin < p.Y < self.YMax:
            xbin = math.ceil((p.X - self.XMin) / self.XRes) - 1
            ybin = math.ceil((p.Y - self.YMin) / self.YRes) - 1
            Response = self.InterPolate(p.Energy)
            self.Fluence[xbin, ybin] = self.Fluence[xbin, ybin] + p.WT
            self.EnergyFluence[xbin, ybin] = self.EnergyFluence[xbin, ybin] + p.WT*p.Energy
            self.Response[xbin, ybin] = self.Response[xbin, ybin] + p.WT*Response
            self.Statistics = self.Statistics+p.WT
            # self.Fluence[xbin, ybin] = self.Fluence[xbin, ybin] + 1
            # self.EnergyFluence[xbin, ybin] = self.EnergyFluence[xbin, ybin] + p.Energy
            # self.Response[xbin, ybin] = self.Response[xbin, ybin] + Response
            # self.Statistics = self.Statistics+1

    def EnergyResponse(self, path):
        data = np.loadtxt(path)
        self.ipo3 = spi.splrep(data[:, 0], data[:, 1], k=3)

    def InterPolate(self, x):
        y = spi.splev(x, self.ipo3)
        return y

    def Show(self):
        # plt.figure(figsize=(12, 9))
        plt.matshow(self.Fluence)
        plt.title(''.join(['Fluence Statictics: ', str(self.Statistics)]))
        plt.matshow(self.EnergyFluence)
        plt.title(''.join(['EnergyFluence Statictics: ', str(self.Statistics)]))
        plt.matshow(self.Response)
        plt.title(''.join(['Response Statictics: ', str(self.Statistics)]))

    def Save(self, path):
        with open(path+"_Fluence.dat", 'wb') as fout:
            for i in range(self.XSize):
                for j in range(self.YSize):
                    bytes=struct.pack('f', self.Fluence[i, j])
                    fout.write(bytes)
        with open(path+"_EnergyFluence.dat", 'wb') as eout:
            for i in range(self.XSize):
                for j in range(self.YSize):
                    bytes=struct.pack('f', self.EnergyFluence[i, j])
                    eout.write(bytes)
        with open(path+"_Response.dat", 'wb') as rout:
            for i in range(self.XSize):
                for j in range(self.YSize):
                    bytes=struct.pack('f', self.Response[i, j])
                    rout.write(bytes)


class EnergyFluence:
    def __init__(self, nbin, Rmax, binshape='circle'):
        self.nbin = nbin
        self.Rmax = Rmax
        self.Rstep = 0
        self.x = []
        self.y = []
        self.yfin = np.zeros(self.nbin)
        self.ynum = []
        self.reset()

    def reset(self):
        self.Rstep = self.Rmax / math.sqrt(self.nbin)
        self.x = [(math.sqrt(i + 1)) * self.Rstep for i in range(self.nbin)]
        self.y = [0 for i in range(self.nbin)]
        self.yfin = np.zeros(self.nbin)
        self.ynum = [0 for i in range(self.nbin)]

    def accumulate(self, x, y):
        if 0 < x < self.Rmax:
            xbin = math.ceil((x/self.Rstep)**2) - 1
            # xbin = math.ceil(x * self.nbin / self.Rmax) - 1
            self.y[xbin] = self.y[xbin] + y
            self.ynum[xbin] = self.ynum[xbin]+1

    def show(self):
        plt.figure(figsize=(12, 9))
        self.yfin = [self.y[i]/(math.pi * self.Rstep**2) for i in range(self.nbin)]
        plt.plot(self.x, self.yfin)
        plt.xlabel("R/cm")
        plt.ylabel("Energy Fluence")
        plt.title("Energy Fluence vs Position")
        plt.show()


def Main():
        print("args:")
        for n, arg in enumerate(sys.argv):
            print("NO.{:2d} arg: {:}".format(n, arg))
        del n, arg
        if len(sys.argv) == 2 and os.path.isfile(sys.argv[1]):
            p = Phsp(sys.argv[1])
            # P.TotalLoop()
            print(p.GetInfo())
        elif not os.path.isfile(sys.argv[1]):
            print("File doesn't exist.")


def Main3(path):
    p = Phsp(path)
    # P.TotalLoop()
    p.Show(p.Loop(1, 100))
    print(p.GetInfo())


def AutoProcess(path, result_path, ext='.npy'):
    assert isinstance(result_path, list)
    if not isinstance(path, Path):
        path = Path(path)
    if not path.exists():
        raise ValueError("No such directory or file: ", str(path))
    if path.is_dir():
        for pt in path.iterdir():
            AutoProcess(pt,result_path, ext)
    elif path.is_file():
        if path.suffix == ext:
            # print(path)
            result_path.append(path)
    return result_path


def Exp(x, p):
    return np.exp(x * p)


def Residuals(p, yf, x):
    return yf - Exp(x, p)


def FitExp(x, y):
    plsq = optimize.leastsq(Residuals, np.array([0.5]), args=(y, x))
    p = plsq[0]
    print("p: ", p)
    return p


def Main2():
    phsp_list = AutoProcess(Path(r"\\dataserver03\rt\06_PH\Temp\fuwei.zhao\Cloud\Ubuntu\Data\15MV\W_new"), [], ext='.egsphsp1')
    photon_list = {}
    for p in phsp_list:
        phsp = Phsp(str(p))
        p = Path(p)
        depth = re.search('W\d.\dcm', str(p))[0][1:-2]
        photon_list[depth] = phsp.PhotonNumParticles
    thickness_list = []
    photon_number_list = []
    for key, value in photon_list.items():
        thickness_list.append(float(key))
        photon_number_list.append(value)
        print("W%scm: %d" % (key, value))
    fig = plt.figure()
    ax = fig.subplots(1, 1)
    ax.plot(thickness_list, photon_number_list)
    x = thickness_list[1:]
    y = photon_number_list[1:]
    y_max = np.max(y)
    y = y/y_max
    p = FitExp(x, y)
    yf = list(map(lambda xf: Exp(xf, p) * y_max, x))
    ax.plot(x, yf)
    plt.show()


def Process(phsp_file):
    phsp_deposit = R"E:\Code\C++\Demo\PhspRead\x64\Release\PhspRead_Total_Deposit_GPU_v2_transport5mm.exe"
    cmd = phsp_deposit + " " + phsp_file.as_posix()
    # os.system(cmd)
    terminal_cmd = "start powershell.exe cmd /k '%s'" % cmd
    # terminal_cmd = "start cmd /k '%s'" % cmd
    print(terminal_cmd)
    # os.system(terminal_cmd)
    try:
        # res = Popen(terminal_cmd, shell=True)
        res = check_call(terminal_cmd, shell=True)
        print('res: ', res)
    except CalledProcessError as exc:
        print("returncode: ", exc.returncode)
        print("cmd: ", exc.cmd)
        print("output: ", exc.output)



def Main4():
    # home_dir = Path(R"F:\Data\EGSnrc\CBCT25")
    # phantom_thick_list = [0, 4, 12, 20, 28]
    # header = R"EGS_New_FS27_SW%d\EGS.egsphsp1"

    home_dir = Path(R"E:\Cloud\Ubuntu\CBCT21")
    # phantom_thick_list = [0, 4, 12, 20, 28]
    # phantom_thick_list = [12, 20, 28]
    phantom_thick_list = [0, 1, 2, 4, 6, 8, 12, 16, 20, 24, 28]
    header = R"P2.80_SL0.60_SS0.1_SD0.8_FS27_SW%d\EGS.egsphsp1"

    p = Pool(min(cpu_count(), len(phantom_thick_list)))
    for thick in phantom_thick_list:
        phsp_file = home_dir.joinpath(header % thick)
        if not phsp_file.is_file():
            print("File: %s doesn't exist." % phsp_file.as_posix())
            continue
        # Process(phsp_file)
        p.apply_async(Process, args=(phsp_file, ))
    p.close()
    p.join()
    print("Done!")


if __name__ == "__main__":
    # path = r"\\dataserver03\rt\06_PH\Temp\fuwei.zhao\20211111_EGS\WithMark\P2.3_SL0.6_SS0.1_SD0.8_FS5\EGS.egsphsp1"
    # Main3(path)
    Main4()
