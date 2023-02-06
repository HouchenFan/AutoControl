import subprocess
import numpy as np
import os, re



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
        self.info = info


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


def Inputs(input_info):
    if isinstance(input_info, list):
        txt = input_info
    elif os.path.isfile(input_info):
        with open(input_info, 'r') as fid:
            txt=fid.readlines()
    else:
        raise ValueError("Unvalid input.")
    inputs = ''.join(txt)
    inputs = bytes(inputs, 'utf-8')
    return inputs


def Thickness(filename):
    return float(re.search("\d+\.\d+cm", filename)[0][:-2])


def BeamDP(input_info):
    print("BeamDP")
    p = subprocess.Popen(['/home/uih/EGSnrc/HEN_HOUSE/bin/linux64/beamdp'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    inputs = Inputs(input_info)
    output, err = p.communicate(inputs)
    print('Output: ', output.decode('utf-8'))
    print('Error: ', err.decode('utf-8'))
    print('Exit code:', p.returncode)


def BeamDPSet(phsp_dir, input_path, string):
    phsp_files = list(os.listdir(phsp_dir))
    phsp_files = list(filter(lambda x: os.path.splitext(x)[1][:-1] == '.egsphsp', phsp_files))
    # phsp_files = sorted(phsp_files, key=Thickness)
    # phsp_files = phsp_files[50:]
    print(phsp_files)
    for idx, pf in enumerate(phsp_files):
        full_path = os.path.join(phsp_dir, pf)
        i_phsp = Info(5, 0, full_path)
        i_agr = Info(6, 0, os.path.splitext(full_path)[0] +'_%d' % (idx+1) + string)
        # i_radius = Info(2, 2, str(0.5))
        # i_energy = Info(3, 2, phsp_dir.split(os.sep)[-2].split('MV')[0])
        script = os.path.join(phsp_dir, 'beamdp.script')
        ModifyFile(input_path, script, [i_phsp, i_agr])
        BeamDP(script)
    return (os.path.splitext(full_path)[0] + string)

def ReadBeamdp(path):
    data = []
    with open(path, 'r') as fid:
        all_lines = fid.readlines()
        for line in all_lines:
            if not (line.startswith('@') or line.startswith('&')):
                for item in line.split('     '):
                    if item:
                        data.append(item)
    fid.close()
    data = np.array(data, dtype='float64').reshape(-1, 3)[0, 1]
    return data

if __name__ == "__main__":
    # phsp_dir = [r"/home/uih/Data/15MV/W_new", r"/home/uih/Data/20MV/W_new", r"/home/uih/Data/30MV/W_new", r"/home/uih/Data/50MV/W_new", r"/home/uih/Data/100MV/W_new"]
    list_pho = []
    list_ele = []
    for i in [7]:#range(0, 16):
        for j in [3]:#range(0, 21):

            phsp_dir = [r"/home/uih/UIH_MRL_Target/UIH_MRL_ISO_W%dCu%d_DBS" % (i, j)]
            inputs_path_pho = r"/home/uih/UIH_MRL_Target/EF_pho_B1.script"
            inputs_path_ele = r"/home/uih/UIH_MRL_Target/EF_ele_B1.script"
            for ph in phsp_dir:
                # if i not in [0, 1, 2, 3, 4, 5]:
                path = BeamDPSet(ph, inputs_path_pho, '_EF_pho.agr')
                # path = '/home/uih/UIH_MRL_Target/UIH_MRL_Target_W%dCu%d' % (i, j) + '/EGS_EF_pho.agr'
                # value = ReadBeamdp(path)
                # list_pho.append(str(value))
                if j != 20:
                    list_pho.append('\t')
                else:
                    list_pho.append('\n')
            print("Finished.")
            for ph in phsp_dir:
                # if i not in [0, 1, 2, 3, 4, 5]:
                path = BeamDPSet(ph, inputs_path_ele, '_EF_ele.agr')
                # path = '/home/uih/UIH_MRL_Target/UIH_MRL_Target_W%dCu%d' % (i, j) + '/EGS_EF_ele.agr'
                # value = ReadBeamdp(path)
                # list_ele.append(str(value))
                if j != 20:
                    list_ele.append('\t')
                else:
                    list_ele.append('\n')
            print(phsp_dir)
            print("Finished.")
    # with open('/home/uih/UIH_MRL_Target/EF_Target_Photon.txt', 'w') as fout:
    #     fout.writelines(list_pho)
    #     fout.close()
    # with open('/home/uih/UIH_MRL_Target/EF_Target_Electrons.txt', 'w') as fout:
    #     fout.writelines(list_ele)
    #     fout.close()


