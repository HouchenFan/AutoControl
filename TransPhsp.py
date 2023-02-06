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
import scipy.interpolate as spi
import binascii


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
        binstr[width-i-1]=str(remainder)
    binstr=''.join(binstr)
    return binstr

class PhspVector:
    def __init__(self, PID, LATCH, Energy, X, Y, U, V, WT, particle_type, ZLast=0,):
        self.LATCH = LATCH
        self.PID = PID
        self.Bremsstrahlung = Cut(self.LATCH, 0, 1)
        self.InteractiveRegion = Cut(self.LATCH, 1, 23)
        self.SecondaryParticle = Cut(self.LATCH, 24, 5)
        self.Charge = Cut(self.LATCH, 29, 2)
        self.MultiScore = Cut(self.LATCH, 31, 1)
        self.ZLast = ZLast
        self.Energy = Energy
        self.EkElectron = 0.5
        global NPHOTPHSP
        if self.Charge == 0:  #判断是否为光子
            self.EkAll = abs(Energy)
            NPHOTPHSP += 1
        elif self.Charge == -1:  #判断是否为电子
            self.EkAll = abs(Energy) - 0.511
            self.EkElectron = self.EkAll
            SumElectron += 1
        else:                       #判断是否为正电子
            self.EkAll = abs(Energy) - 0.511
        global EKMAXPHSP
        global EKMINPHSPE
        if self.EkAll > EKMAXPHSP:  #更新所有粒子的最大动能
            EKMAXPHSP = self.EkAll
        if self.EkElectron < EKMINPHSPE:   #更新所有电子的最小动能
            EKMINPHSPE = self.EkElectron
        self.X = X
        self.Y = Y
        self.U = U
        self.particle_type = particle_type
        if not -1 <= self.U <= 1:
            print('NO.{:8d}:U is wrong:{:8.3f}'.format(self.PID, self.U))
            raise AssertionError
        self.V = V
        if not -1 <= self.V <= 1:
            print('NO.{:8d}:V is wrong:{:8.3f}'.format(self.PID, self.V))
            raise AssertionError
        W_temp = (1 - U ** 2 - V ** 2)
        self.W = math.sqrt(W_temp)
        # if self.particle_type == b'\xff':  #判断W是否要带负号 add by FHC 2022/9/2
        #     self.W = self.W * -1
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
    def __init__(self, filename, headername=0):
        self.FileName = filename
        self.HeaderName = headername
        # 读取相空间文件基本信息  add by FHC 2022/9/7
        with open(filename, 'rb') as fid:
            self.NINCPHSP = 0
            if headername == 0:
                pass
            else:
                with open(headername, 'r', encoding='utf-8') as fid_header:     # 读取IAEAheader文件基本信息   add by FHC 2022/9/7
                    while (self.NINCPHSP == 0):
                        lines = fid_header.readline()  #整行读取数
                        if ("$ORIG_HISTORIES:") in lines:
                            self.NINCPHSP = int(next(fid_header).replace("\n"," "))     #History 数量
                        # elif ("$PARTICLES:") in lines:
                        #     NPPHSP = int(next(fid_header).replace("\n", " "))      #所有的粒子数量
                        # elif ("$PHOTONS:") in lines:
                        #     NPHOTPHSP = int(next(fid_header).replace("\n", " "))       #所有的光子数量
                    fid_header.close()
            self.TotalNumParticles = int(os.path.getsize(filename) / 33)
            self.NPPHSP = 0
            self.NPHOTPHSP = 0
            self.EKMAXPHSP = 0
            self.EKMINPHSPE = 1.0
        fid.close()
        self.startTime = datetime.now()


    def ReadIAEA(self):
        # 定义每个粒子的数据类型
        type = np.dtype([('particle_type', 'S1'), ('Energy', 'f4'), ('X', 'f4'), ('Y', 'f4'), ('Z', 'f4'), ('U', 'f4'), ('V', 'f4'), ('WT', 'f4'), ('LATCH', 'i4')])    #定义每个粒子的数据类型
        zEpid = 40    #EPID上表面的Z坐标
        with open(self.FileName, 'rb') as fid:
            Raw = np.fromfile(self.FileName, dtype=type, count=-1, sep="", offset=0)            #按照数据类型读取全部粒子信息
            PtypeIndex = np.where(Raw['particle_type'] == b'\xff')[0]                       #找到Z方向速度为负的粒子的index
            WIndex = np.where((1 - np.square(Raw['U']) - np.square(Raw['V'])) <= 0)[0]      #找到W^2小于等于0的粒子的index
            Raw_select = np.delete(Raw, list(set(PtypeIndex).union(set(WIndex))), axis=0)   #删除上述两种粒子的数据

            PhotonIndex = np.where(Raw_select['particle_type'] == b'\x01')[0]               #找到光子的index
            ElectronIndex = np.where(Raw_select['particle_type'] == b'\x02')[0]             #找到电子的index
            PositronIndex = np.where(Raw_select['particle_type'] == b'\x03')[0]             #找到正电子的index
            self.NPPHSP = len(Raw_select)                                                   #总粒子数
            self.NPHOTPHSP = len(PhotonIndex)                                               #总光子数
            self.EKMAXPHSP = max(abs(Raw_select['Energy']))                                 #所有粒子最大动能
            self.EKMINPHSPE = min(abs(Raw_select['Energy'][ElectronIndex]))                  #所有电子最小动能
            #将电子的动能转化为总能量同时保留其正负号
            Raw_select['Energy'][list(set(np.where(Raw_select['Energy'] >= 0)[0]).intersection(set(ElectronIndex)))] += 0.511
            Raw_select['Energy'][list(set(np.where(Raw_select['Energy'] < 0)[0]).intersection(set(ElectronIndex)))] -= 0.511
            Raw_select['LATCH'][ElectronIndex] += 2 << 29                                   #在LATCH中添加Charge信息
            # 将正电子的动能转化为总能量同时保留其正负号
            Raw_select['Energy'][list(set(np.where(Raw_select['Energy'] >= 0)[0]).intersection(set(PositronIndex)))] += 0.511
            Raw_select['Energy'][list(set(np.where(Raw_select['Energy'] < 0)[0]).intersection(set(PositronIndex)))] -= 0.511
            Raw_select['LATCH'][PositronIndex] += 1 << 29                                   #在LATCH中添加Charge信息
            #将粒子输运到EPID的上平面，即修改XY坐标
            WList = np.sqrt(1.0 - np.square(Raw_select['U']) - np.square(Raw_select['V']))
            Raw_select['X'] += (Raw_select['U'] / WList) * (zEpid - Raw_select['Z'])
            Raw_select['Y'] += (Raw_select['V'] / WList) * (zEpid - Raw_select['Z'])
            #输出读取IAEAphsp所用时间
            self.stopTime = datetime.now()
            print("ReadIAEA Time is {:d} seconds".format((self.stopTime - self.startTime).seconds))

            self.SaveIAEA(Raw_select)        #写入并保存输运后的相空间文件
            #输出全部时间
            self.stopTime = datetime.now()
            print("Total Time is {:d} seconds".format((self.stopTime - self.startTime).seconds))
            return self.FileName

    def SaveIAEA(self, Raw_select):
        self.FileName = self.FileName.split('.IAEA')[0] + ".egsphsp1"
        self.headtype = 'iifff'                         # 相空间文件Header 的数据类型
        self.datatype = 'iffffff'                       # 相空间文件粒子的数据类型
        self.Nothing = b'\x00\x00\x00'                  #空字节
        with open(self.FileName, 'wb') as fout:
            fout.write(b'MODE0')
            phspHead = struct.pack(self.headtype, self.NPPHSP, self.NPHOTPHSP, self.EKMAXPHSP, self.EKMINPHSPE, self.NINCPHSP)
            fout.write(phspHead)
            fout.write(self.Nothing)
            for i in range(len(Raw_select)):
                self.binData = struct.pack(self.datatype, Raw_select['LATCH'][i], Raw_select['Energy'][i], Raw_select['X'][i], Raw_select['Y'][i], Raw_select['U'][i], Raw_select['V'][i], Raw_select['WT'][i])
                fout.write(self.binData)
        fout.close()


    def ReadPhsp(self, ZPhantom):
        self.headtype = 'iifff'
        self.Ztrans = math.floor(40 + ZPhantom)
        with open(self.FileName, 'rb') as fid:
            MODE_RW = fid.read(5)
            phspHead = fid.read(4 * 5)
            Nothing = fid.read(3)
            self.NPPHSP, self.NPHOTPHSP, self.EKMAXPHSP, self.EKMINPHSPE, self.NINCPHSP = struct.unpack(self.headtype, phspHead)
            type = np.dtype([('LATCH', 'i4'), ('Energy', 'f4'), ('X', 'f4'), ('Y', 'f4'), ('U', 'f4'), ('V', 'f4'), ('WT', 'f4')])
            Raw = np.fromfile(self.FileName, dtype=type, count=-1, sep="", offset=28)
            #输运
            WList = np.sqrt(1.0 - np.square(Raw['U']) - np.square(Raw['V']))
            Raw['X'] += (Raw['U'] / WList) * (self.Ztrans - 0)
            Raw['Y'] += (Raw['V'] / WList) * (self.Ztrans - 0)
            # 输出读取egsphsp所用时间
            self.stopTime = datetime.now()
            print("Readegsphsp Time is {:d} seconds".format((self.stopTime - self.startTime).seconds))

            self.Filename = self.SaveEgsPhsp(MODE_RW, phspHead, Nothing, Raw)  # 写入并保存输运后的相空间文件
            # 输出全部时间
            self.stopTime = datetime.now()
            print("Total Time is {:d} seconds".format((self.stopTime - self.startTime).seconds))
        return self.FileName

    def ReadPhspandFilter(self):
        self.headtype = 'iifff'
        with open(self.FileName,'rb') as fid:
            MODE_RW = fid.read(5)
            phspHead = fid.read(4 * 5)
            Nothing = fid.read(3)
            self.NPPHSP, self.NPHOTPHSP, self.EKMAXPHSP, self.EKMINPHSPE, self.NINCPHSP = struct.unpack(self.headtype, phspHead)
            type = np.dtype([('LATCH', 'i4'), ('Energy', 'f4'), ('X', 'f4'), ('Y', 'f4'), ('U', 'f4'), ('V', 'f4'), ('WT', 'f4')])
            Raw = np.fromfile(self.FileName, dtype=type, count=-1, sep="", offset=28)
            #根据能量筛选光子
            LowEIdx = np.where(abs(Raw['Energy']) <= 0.12)[0]
            HighEIdx = np.where(abs(Raw['Energy']) > 0.12)[0]
            PhotonIdx = np.where((Raw['LATCH'] >> 29) % (2**2) == 0)[0]

            PhotonIdx_lowE = set(LowEIdx).intersection(set(PhotonIdx))
            Raw_LowE = Raw[list(PhotonIdx_lowE)]

            PhotonIdx_HighE = set(HighEIdx).intersection(set(PhotonIdx))
            Raw_HighE = Raw[list(PhotonIdx_HighE)]

            self.NPPHSP_LowE = len(Raw_LowE)  # 总粒子数
            self.NPHOTPHSP_LowE = len(PhotonIdx_lowE)  # 总光子数
            self.EKMAXPHSP_LowE = max(abs(Raw_LowE['Energy']))  # 所有粒子最大动能
            self.EKMINPHSPE_LowE = self.EKMINPHSPE

            self.NPPHSP_HighE = len(Raw_HighE)  # 总粒子数
            self.NPHOTPHSP_HighE = len(PhotonIdx_HighE)  # 总光子数
            self.EKMAXPHSP_HighE = max(abs(Raw_HighE['Energy']))  # 所有粒子最大动能
            self.EKMINPHSPE_HighE = self.EKMINPHSPE

            phspHead_LowE = struct.pack(self.headtype, self.NPPHSP_LowE, self.NPHOTPHSP_LowE, self.EKMAXPHSP_LowE, self.EKMINPHSPE_LowE, self.NINCPHSP)
            phspHead_HighE = struct.pack(self.headtype, self.NPPHSP_HighE, self.NPHOTPHSP_HighE, self.EKMAXPHSP_HighE, self.EKMINPHSPE_LowE, self.NINCPHSP)
            # 输出读取egsphsp所用时间
            self.stopTime = datetime.now()
            print("Readegsphsp Time is {:d} seconds".format((self.stopTime - self.startTime).seconds))

            self.SaveEgsPhsp(MODE_RW, phspHead_LowE, Nothing, Raw_LowE, '_LowE.egsphsp1')
            self.SaveEgsPhsp(MODE_RW, phspHead_HighE, Nothing, Raw_HighE, '_HighE.egsphsp1') # 写入并保存输运后的相空间文件
            # 输出全部时间
            self.stopTime = datetime.now()
            print("Total Time is {:d} seconds".format((self.stopTime - self.startTime).seconds))

    def SaveEgsPhsp(self, MODE_RW, phspHead, Nothing, Raw, name=0):
        if name != 0:
            self.NewFileName = self.FileName.split('.egs')[0] + name
        else:
            self.FileName = self.FileName.split('.egs')[0] + "_trans%d.egsphsp1" % int(self.Ztrans - 40)
        self.datatype = 'iffffff'
        with open(self.NewFileName, 'wb') as fout:
            fout.write(MODE_RW)
            fout.write(phspHead)
            fout.write(Nothing)
            for i in range(len(Raw)):
                self.binData = struct.pack(self.datatype, Raw['LATCH'][i], Raw['Energy'][i], Raw['X'][i], Raw['Y'][i], Raw['U'][i], Raw['V'][i], Raw['WT'][i])
                fout.write(self.binData)
        fout.close()
        return self.FileName


if __name__ == '__main__':
        path_phsp = "/home/uih/IBL_ESpectrum/E/N0_P11_1.2_D144/EGS_D60.egsphsp1"
        path_header = "/home/uih/EGSnrc/egs_home/dosxyznrc/AllSame_Test.IAEAheader"
        ph = Phsp(path_phsp)
        ph.ReadPhspandFilter()
        # ph.ReadIAEA()
        # ZPhant = -7.5
        # path = ph.ReadPhsp(ZPhant)
        # print(path)
