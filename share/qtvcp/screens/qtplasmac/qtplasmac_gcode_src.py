'''
plasmac_gcode.py

Copyright (C) 2019, 2020, 2021  Phillip A Carter
Copyright (C) 2020, 2021  Gregory D Carl

This program is free software; you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the
Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License along
with this program; if not, write to the Free Software Foundation, Inc
51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
'''

import os
import sys
import linuxcnc
import math
import shutil
import time
from subprocess import run as RUN
from PyQt5 import QtCore
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QDialog, QScrollArea, QWidget, QVBoxLayout, QLabel, QPushButton, QStyle

app = QApplication(sys.argv)
ini = linuxcnc.ini(os.environ['INI_FILE_NAME'])
cmd = linuxcnc.command()
inCode = sys.argv[1]
materialFile = '{}_material.cfg'.format(ini.find('EMC', 'MACHINE'))
tmpMaterialFile = '/tmp/qtplasmac/{}_material.gcode'.format(ini.find('EMC', 'MACHINE'))
tmpMatNum = 1000000
tmpMatNam = ''
prefsFile = 'qtplasmac.prefs'
response = RUN(['halcmd', 'getp', 'qtplasmac.cut_type'], capture_output = True)
cutType = int(response.stdout.decode())
response = RUN(['halcmd', 'getp', 'qtplasmac.material_change_number'], capture_output = True)
currentMat = int(response.stdout.decode())
response = RUN(['halcmd', 'getp', 'qtplasmac.color_fg'], capture_output = True)
fgColor = str(hex(int(response.stdout.decode()))).replace('0x', '#')
response = RUN(['halcmd', 'getp', 'qtplasmac.color_bg'], capture_output = True)
bgColor = str(hex(int(response.stdout.decode()))).replace('0x', '#')
response = RUN(['halcmd', 'getp', 'qtplasmac.color_bgalt'], capture_output = True)
bgAltColor = str(hex(int(response.stdout.decode()))).replace('0x', '#')
response = RUN(['halcmd', 'getp', 'plasmac.max-offset'], capture_output = True)
zMaxOffset = float(response.stdout.decode())
metric = ['mm', 4]
imperial = ['in', 6]
units, precision = imperial if ini.find('TRAJ', 'LINEAR_UNITS').lower() == 'inch' else metric
if units == 'mm':
    minDiameter = 32
    ocLength = 4
    unitsPerMm = 1
else:
    minDiameter = 1.26
    ocLength = 0.157
    unitsPerMm = 0.03937
unitMultiplier = 1
gcodeList = []
newMaterial = []
firstMaterial = ''
line = ''
rapidLine = ''
lastX = 0
lastY = 0
oBurnX = 0
oBurnY = 0
lineNum = 0
distMode = 90 # absolute
arcDistMode = 91.1 # incremental
holeVelocity = 60
material = [0, False]
overCut = False
holeActive = False
holeEnable = False
arcEnable = False
customDia = False
customLen = False
torchEnable = True
pierceOnly = False
scribing = False
spotting = False
offsetG4x = False
zSetup = False
zBypass = False
codeWarn = False
warnUnitsDep = []
warnPierceScribe = []
warnMatLoad = []
warnHoleDir = []
warnCompTorch = []
warnCompVel = []
warnFeed = []
warnings  = 'The following warnings may affect the quality of the process.\n'
warnings += 'It is recommended that all warnings are fixed before running this file.\n'
codeError = False
errorMath = []
errorMissMat = []
errorTempMat = []
errorNewMat = []
errorEditMat = []
errorWriteMat = []
errorReadMat = []
errorCompMat = []
errors  = 'The following errors will affect the process.\n'
errors += 'Errors must be fixed before reloading this file.\n'

# feedback dialog
def dialog_box(title, text, align):
    if align == Qt.AlignCenter:
        icon = QStyle.SP_MessageBoxCritical
    else:
        icon = QStyle.SP_MessageBoxWarning
    dlg = QDialog()
    scroll = QScrollArea(dlg)
    widget = QWidget()
    vbox = QVBoxLayout()
    label = QLabel()
    vbox.addWidget(label)
    widget.setLayout(vbox)
    btn = QPushButton('OK', dlg)
    dlg.setWindowTitle(title)
    dlg.setWindowIcon(QIcon(dlg.style().standardIcon(icon)))
    dlg.setWindowFlags(Qt.WindowStaysOnTopHint)
    dlg.setModal(False)
    dlg.setFixedWidth(600)
    dlg.setFixedHeight(310)
    dlg.setStyleSheet(' \
                      QWidget {{ color: {0}; background: {1} }} \
                      QScrollArea {{ color: {0}; background: {1}; border: 1px solid {0}; border-radius: 4px; padding: 4px }} \
                      QPushButton {{ border: 2px solid {0}; border-radius: 4px; \
                                     font: 12pt; width: 60px; height: 40px }} \
                      QPushButton:pressed {{ border: 1px solid {0} }} \
                      QScrollBar:vertical {{background: {2}; border: 0px; border-radius: 4px; margin: 0px; width: 20px }} \
                      QScrollBar::handle:vertical {{ background: {0}; border: 2px solid {0}; border-radius: 4px; margin: 2px; min-height: 40px }} \
                      QScrollBar::add-line:vertical {{ height: 0px }} \
                      QScrollBar::sub-line:vertical {{ height: 0px }}'.format(fgColor, bgColor, bgAltColor))
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setWidgetResizable(True)
    scroll.setWidget(widget)
    scroll.setGeometry(5, 5, 590, 250)
    btn.move(270,260)
    btn.clicked.connect(lambda w: dlg_ok_clicked(dlg))
    label.setAlignment(align)
    label.setText(text)
    dlg.exec()

def dlg_ok_clicked(dlg):
    dlg.accept()

# set hole type
def set_hole_type(h):
    global lineNum, holeEnable, overCut, arcEnable
    if h == 1:
        holeEnable = True
        arcEnable = False
        overCut = False
    elif h == 2:
        holeEnable = True
        arcEnable = False
        overCut = True
    elif h == 3:
        holeEnable = True
        arcEnable = True
        overCut = False
    elif h == 4:
        holeEnable = True
        arcEnable = True
        overCut = True
    else:
        holeEnable = False
        arcEnable = False
        overCut = False

# check if arc is a hole
def check_if_hole():
    global lineNum, lastX, lastY, minDiameter
    I, J, isHole = 0, 0, 0
    if distMode == 91: # get absolute X & Y from incremental coordinates
        endX = lastX + get_axis_value('x') if 'x' in line else lastX
        endY = lastY + get_axis_value('y') if 'y' in line else lastY
    else: # get absolute X & Y
        endX = get_axis_value('x') if 'x' in line else lastX
        endY = get_axis_value('y') if 'y' in line else lastY
    if arcDistMode == 90.1: # convert I & J to incremental to make diameter calculations easier
        if 'i' in line: I = get_axis_value('i') - lastX
        if 'j' in line: J = get_axis_value('j') - lastY
    else: # get incremental I & J
        if 'i' in line: I = get_axis_value('i')
        if 'j' in line: J = get_axis_value('j')
    if lastX and lastY and lastX == endX and lastY == endY:
        isHole = True
    diameter = get_hole_diameter(I, J, isHole)
    gcodeList.append(line)
    if isHole and overCut and diameter <= minDiameter:
        overburn(I, J, diameter / 2)
        return
    else:
        lastX = endX
        lastY = endY

# get hole diameter and set velocity percentage
def get_hole_diameter(I, J, isHole):
    global lineNum, holeActive, codeWarn, warnCompVel, warnHoleDir
    if offsetG4x:
        diameter = math.sqrt((I ** 2) + (J ** 2)) * 2
    else:
        kerfWidth = materialDict[material[0]][1] / 2 * unitMultiplier
        diameter = (math.sqrt((I ** 2) + (J ** 2)) * 2) + kerfWidth
    # velocity reduction is required
    if diameter <= minDiameter and (isHole or arcEnable):
        if offsetG4x:
            lineNum += 1
            gcodeList.append(';m67 e3 q0 (inactive due to g41)')
            codeWarn = True
            warnCompVel.append(lineNum)
        elif not holeActive:
            if diameter <= minDiameter:
                lineNum += 1
                gcodeList.append('m67 e3 q{0} (diameter:{1:0.3f}, velocity:{0}%)'.format(holeVelocity, diameter))
            holeActive = True
        if line.startswith('g2') and isHole:
            codeWarn = True
            warnHoleDir.append(lineNum)
    # no velocity reduction required
    else:
        if holeActive:
            lineNum += 1
            gcodeList.append('m67 e3 q0 (arc complete, velocity 100%)')
            holeActive = False
    return diameter

# turn torch off and move 4mm (0.157) past hole end
def overburn(I, J, radius):
    global lineNum, lastX, lastY, torchEnable, ocLength, warnCompTorch, arcDistMode, oBurnX, oBurnY
    centerX = lastX + I
    centerY = lastY + J
    cosA = math.cos(ocLength / radius)
    sinA = math.sin(ocLength / radius)
    cosB = ((lastX - centerX) / radius)
    sinB = ((lastY - centerY) / radius)
    lineNum += 1
    if offsetG4x:
        gcodeList.append(';m62 p3 (inactive due to g41)')
        codeWarn = True
        warnCompTorch.append(lineNum)
    else:
        gcodeList.append('m62 p3 (disable torch)')
        torchEnable = False
    #clockwise arc
    if line.startswith('g2'):
        endX = centerX + radius * ((cosB * cosA) + (sinB * sinA))
        endY = centerY + radius * ((sinB * cosA) - (cosB * sinA))
        dir = '2'
    #counterclockwise arc
    else:
        endX = centerX + radius * ((cosB * cosA) - (sinB * sinA))
        endY = centerY + radius * ((sinB * cosA) + (cosB * sinA))
        dir = '3'
    lineNum += 1
    # restore I & J back to absolute from incremental conversion in check_if_hole
    if arcDistMode == 90.1:
        I += lastX
        J += lastY
    if distMode == 91: # output incremental X & Y
        gcodeList.append('g{0} x{1:0.{5}f} y{2:0.{5}f} i{3:0.{5}f} j{4:0.{5}f}'.format(dir, endX - lastX, endY - lastY, I, J, precision))
    else: # output absolute X & Y
        gcodeList.append('g{0} x{1:0.{5}f} y{2:0.{5}f} i{3:0.{5}f} j{4:0.{5}f}'.format(dir, endX, endY, I, J, precision))
    oBurnX = endX - lastX
    oBurnY = endY - lastY

# fix incremental coordinates after overburn
def fix_overburn_incremental_coordinates(line):
    newLine = line[:2]
    if 'x' in line and 'y' in line:
        x = get_axis_value('x')
        if x is not None:
            newLine += 'x{:0.4f}'.format(x - oBurnX)
        y = get_axis_value('y')
        if y is not None:
            newLine += 'y{:0.4f}'.format(y - oBurnY)
        return newLine
    elif 'x in line':
        x = get_axis_value('x')
        if x is not None:
            newLine += 'x{:0.4f}y{:0.4f}'.format(x - oBurnX, oBurnY)
        return newLine
    elif 'y' in line:
        y = get_axis_value('y')
        if y is not None:
            newLine += 'x{:0.4f}y{:0.4f}'.format(oBurnX, y - oBurnY)
        return newLine
    else:
        return line

# get axis value
def get_axis_value(axis):
    tmp1 = line.split(axis)[1].replace(' ','')
    if not tmp1[0].isdigit() and not tmp1[0] == '.' and not tmp1[0] == '-':
        return None
    n = 0
    tmp2 = ''
    while 1:
        if tmp1[n].isdigit() or tmp1[n] == '.' or tmp1[n] == '-':
            tmp2 += tmp1[n]
            n += 1
        else:
            break
        if n >= len(tmp1):
            break
    return float(tmp2)

# set the last X and Y coordinates
def set_last_coordinates(Xpos, Ypos):
    if line[0] in ['g','x','y']:
        if 'x' in line:
            if get_axis_value('x') is not None:
                if distMode == 91: # get absolute X from incremental position
                    Xpos += get_axis_value('x')
                else: # get absolute X
                    Xpos = get_axis_value('x')
        if 'y' in line:
            if get_axis_value('y') is not None:
                if distMode == 91: # get absolute X from incremental position
                    Ypos += get_axis_value('y')
                else: # get absolute X
                    Ypos = get_axis_value('y')
    return Xpos, Ypos

# comment out all Z commands
def comment_out_z_commands():
    global lineNum, holeActive
    newline = ''
    newz = ''
    removing = 0
    comment = 0
    for bit in line:
        if comment:
            if bit == ')':
                comment = 0
            newline += bit
        elif removing:
            if bit in '0123456789.- ':
                newz += bit
            else:
                removing = 0
                if newz:
                    newz = newz.rstrip()
                newline += bit
        elif bit == '(':
            comment = 1
            newline += bit
        elif bit == 'z':
            removing = 1
            newz += '(' + bit
        else:
            newline += bit
    if holeActive:
        lineNum += 1
        gcodeList.append('m67 e3 q0 (arc complete, velocity 100%)')
        holeActive = False
    return '{} {})'.format(newline, newz)

# check if math used or explicit values
def check_math(axis):
    global lineNum, codeError
    tmp1 = line.split(axis)[1]
    if tmp1.startswith('[') or tmp1.startswith('#'):
        codeError = True
        if lineNum not in errorMath:
            errorMath.append(lineNum)

# do material change
def do_material_change():
    global lineNum, firstMaterial, codeError
    if '(' in line:
        c = line.split('(', 1)[0]
    elif ';' in line:
        c = line.split(';', 1)[0]
    else:
        c = line
    a, b = c.split('p', 1)
    m = ''
    # get the material number
    for mNum in b.strip():
        if mNum in '0123456789':
            m += mNum
    material[0] = int(m)
    material[1] = True
    if material[0] not in materialDict and material[0] < 1000000:
        codeError = True
        errorMissMat.append(lineNum)
    RUN(['halcmd', 'setp', 'qtplasmac.material_change_number', '{}'.format(material[0])])
    if not firstMaterial:
        firstMaterial = material[0]
    gcodeList.append(line)

# check if material edit required
def check_material_edit():
    global lineNum, tmpMatNum, tmpMatNam, codeError
    tmpMaterial = False
    newMaterial = []
    th = 0
    kw = jh = jd = ca = cv = pe = gp = cm = 0.0
    ca = 15
    cv = 100
    try:
        if 'ph=' in line and 'pd=' in line and 'ch=' in line and 'fr=' in line:
            if '(o=0' in line:
                tmpMaterial = True
                nu = tmpMatNum
                na = 'Temporary {}'.format(tmpMatNum)
                tmpMatNam = na
                newMaterial.append(0)
            elif '(o=1' in line and 'nu=' in line and 'na=' in line:
                newMaterial.append(1)
            elif '(o=2' in line and 'nu=' in line and 'na=' in line:
                newMaterial.append(2)
            if newMaterial[0] in [0, 1, 2]:
                for item in line.split('(')[1].split(')')[0].split(','):
                    # mandatory items
                    if 'nu=' in item and not tmpMaterial:
                        nu = int(item.split('=')[1])
                    elif 'na=' in item:
                        na = item.split('=')[1].strip()
                        if tmpMaterial:
                            tmpMatNam = na
                    elif 'ph=' in item:
                        ph = float(item.split('=')[1])
                        if unitMultiplier != 1:
                            ph = ph / unitMultiplier
                    elif 'pd=' in item:
                        pd = float(item.split('=')[1])
                    elif 'ch=' in item:
                        ch = float(item.split('=')[1])
                        if unitMultiplier != 1:
                            ch = ch / unitMultiplier
                    elif 'fr=' in item:
                        fr = float(item.split('=')[1])
                        if unitMultiplier != 1:
                            fr = fr / unitMultiplier
                    # optional items
                    elif 'kw=' in item:
                        kw = float(item.split('=')[1])
                        if unitMultiplier != 1:
                            kw = kw / unitMultiplier
                    elif 'th=' in item:
                        th = int(item.split('=')[1])
                    elif 'jh=' in item:
                        jh = float(item.split('=')[1])
                        if unitMultiplier != 1:
                            jh = ph / unitMultiplier
                    elif 'jd=' in item:
                        jd = float(item.split('=')[1])
                    elif 'ca=' in item:
                        ca = float(item.split('=')[1])
                    elif 'cv=' in item:
                        cv = float(item.split('=')[1])
                    elif 'pe=' in item:
                        pe = float(item.split('=')[1])
                    elif 'gp=' in item:
                        gp = float(item.split('=')[1])
                    elif 'cm=' in item:
                        cm = float(item.split('=')[1])
                for i in [nu,na,kw,th,ph,pd,jh,jd,ch,fr,ca,cv,pe,gp,cm]:
                    newMaterial.append(i)
                if newMaterial[0] == 0:
                    write_temporary_material(newMaterial)
                elif nu in materialDict and newMaterial[0] == 1:
                    codeError = True
                    errorNewMat.append(lineNum)
                else:
                    rewrite_material_file(newMaterial)
            else:
                codeError = True
                errorEditMat.append(lineNum)
    except:
        codeError = True
        errorEditMat.append(lineNum)

# write temporary materials file
def write_temporary_material(data):
    global lineNum, warnMatLoad, material, codeError
    try:
        with open(tmpMaterialFile, 'w') as fWrite:
            fWrite.write('#plasmac temporary material file\n')
            fWrite.write('\nnumber={}\n'.format(tmpMatNum))
            fWrite.write('name={}\n'.format(tmpMatNam))
            fWrite.write('kerf-width={}\n'.format(data[3]))
            fWrite.write('thc-enable={}\n'.format(data[4]))
            fWrite.write('pierce-height={}\n'.format(data[5]))
            fWrite.write('pierce-delay={}\n'.format(data[6]))
            fWrite.write('puddle-jump-height={}\n'.format(data[7]))
            fWrite.write('puddle-jump-delay={}\n'.format(data[8]))
            fWrite.write('cut-height={}\n'.format(data[9]))
            fWrite.write('cut-feed-rate={}\n'.format(data[10]))
            fWrite.write('cut-amps={}\n'.format(data[11]))
            fWrite.write('cut-volts={}\n'.format(data[12]))
            fWrite.write('pause-at-end={}\n'.format(data[13]))
            fWrite.write('gas-pressure={}\n'.format(data[14]))
            fWrite.write('cut-mode={}\n'.format(data[15]))
            fWrite.write('\n')
    except:
        codeError = True
        errorTempMat.append(lineNum)
    materialDict[tmpMatNum] = [data[10], data[3]]
    RUN(['halcmd', 'setp', 'qtplasmac.material_temp', '{}'.format(tmpMatNum)])
    material[0] = tmpMatNum
    matDelay = time.time()
    while 1:
        if time.time() > matDelay + 3:
            codeWarn = True
            warnMatLoad.append(lineNum)
            break
        response = RUN(['halcmd', 'getp', 'qtplasmac.material_temp'], capture_output = True)
        if not int(response.stdout.decode()):
            break

# rewrite the material file
def rewrite_material_file(newMaterial):
    global lineNum, warnMatLoad
    copyFile = '{}.bkp'.format(materialFile)
    shutil.copy(materialFile, copyFile)
    inFile = open(copyFile, 'r')
    outFile = open(materialFile, 'w')
    while 1:
        line = inFile.readline()
        if not line:
            break
        if not line.strip().startswith('[MATERIAL_NUMBER_'):
            outFile.write(line)
        else:
            break
    while 1:
        if not line:
            add_edit_material(newMaterial, outFile)
            break
        if line.strip().startswith('[MATERIAL_NUMBER_'):
            mNum = int(line.split('NUMBER_')[1].replace(']',''))
            if mNum == newMaterial[1]:
                add_edit_material(newMaterial, outFile)
        if mNum != newMaterial[1]:
            outFile.write(line)
        line = inFile.readline()
        if not line:
            break
    if newMaterial[1] not in materialDict:
        add_edit_material(newMaterial, outFile)
    inFile.close()
    outFile.close()
    RUN(['halcmd', 'setp', 'qtplasmac.material_reload', 1])
    get_materials()
    matDelay = time.time()
    while 1:
        if time.time() > matDelay + 3:
            codeWarn = True
            warnMatLoad.append(lineNum)
            break
        response = RUN(['halcmd', 'getp', 'qtplasmac.material_reload'], capture_output = True)
        if not int(response.stdout.decode()):
            break

# add a new material or or edit an existing material
def add_edit_material(material, outFile):
    global lineNum, codeError, ErrorWriteMat
    try:
        outFile.write('[MATERIAL_NUMBER_{}]\n'.format(material[1]))
        outFile.write('NAME               = {}\n'.format(material[2]))
        outFile.write('KERF_WIDTH         = {}\n'.format(material[3]))
        outFile.write('THC                = {}\n'.format(material[4]))
        outFile.write('PIERCE_HEIGHT      = {}\n'.format(material[5]))
        outFile.write('PIERCE_DELAY       = {}\n'.format(material[6]))
        outFile.write('PUDDLE_JUMP_HEIGHT = {}\n'.format(material[7]))
        outFile.write('PUDDLE_JUMP_DELAY  = {}\n'.format(material[8]))
        outFile.write('CUT_HEIGHT         = {}\n'.format(material[9]))
        outFile.write('CUT_SPEED          = {}\n'.format(material[10]))
        outFile.write('CUT_AMPS           = {}\n'.format(material[11]))
        outFile.write('CUT_VOLTS          = {}\n'.format(material[12]))
        outFile.write('PAUSE_AT_END       = {}\n'.format(material[13]))
        outFile.write('GAS_PRESSURE       = {}\n'.format(material[14]))
        outFile.write('CUT_MODE           = {}\n'.format(material[15]))
        outFile.write('\n')
    except:
        codeError = True
        errorWriteMat.append(lineNum)

# create a dict of material numbers and kerf widths
def get_materials():
    global lineNum, materialDict, codeError, errorReadMat
    try:
        with open(prefsFile, 'r') as rFile:
            fRate = kWidth = 0.0
            for line in rFile:
                if line.startswith('Cut feed rate'):
                    fRate = float(line.split('=')[1].strip())
                if line.startswith('Kerf width'):
                    kWidth = float(line.split('=')[1].strip())
        mNumber = 0
        with open(materialFile, 'r') as mFile:
            materialDict = {mNumber: [fRate, kWidth]}
            while 1:
                line = mFile.readline()
                if not line:
                    break
                elif line.startswith('[MATERIAL_NUMBER_') and line.strip().endswith(']'):
                    mNumber = int(line.rsplit('_', 1)[1].strip().strip(']'))
                    break
            while 1:
                line = mFile.readline()
                if not line:
                    materialDict[mNumber] = [fRate, kWidth]
                    break
                elif line.startswith('[MATERIAL_NUMBER_') and line.strip().endswith(']'):
                    materialDict[mNumber] = [fRate, kWidth]
                    mNumber = int(line.rsplit('_', 1)[1].strip().strip(']'))
                elif line.startswith('CUT_SPEED'):
                    fRate = float(line.split('=')[1].strip())
                elif line.startswith('KERF_WIDTH'):
                    kWidth = float(line.split('=')[1].strip())
    except:
        codeError = True
        errorReadMat.append(lineNum)

def check_f_word(line):
    global lineNum, materialDict, codeWarn, warnFeed
    begin, inFeed = line.split('f', 1)
    rawFeed = ''
    codeFeed = 0.0
    # get feed rate if it is digits
    while len(inFeed) and (inFeed[0].isdigit() or inFeed[0] == '.'):
        rawFeed = rawFeed + inFeed[0]
        inFeed = inFeed[1:].lstrip()
    if rawFeed:
        codeFeed = float(rawFeed)
    else:
        return line
    if inFeed.startswith('#<_hal[plasmac.cut-feed-rate]>'):
        # change feed rate if gcode file not in same units as machine units
        if unitMultiplier != 1:
            line = begin + '{}f[#<_hal[plasmac.cut-feed-rate]> * {}]\n'.format(begin, unitMultiplier)
    # warn if F word is not equal to the selected materials cut feed rate
    if codeFeed != float(materialDict[material[0]][0]):
        codeWarn = True
        warnFeed.append([lineNum, rawFeed, material[0], materialDict[material[0]][0]])
    return line

def message_set(msgType, msg):
    if len(msgType) > 1:
        msg += 'Lines: '
    else:
        msg += 'Line: '
    count = 0
    for line in msgType:
        if codeError:
            line += 1
        if count > 0:
            msg += ', {}'.format(line)
        else:
            msg += '{}'.format(line)
        count += 1
    msg += '\n'
    return msg

# get a dict of materials
get_materials()

# start processing the gcode file
with open(inCode, 'r') as fRead:
    for line in fRead:
        lineNum += 1
        # remove whitespace
        line = line.strip()
        # remove line numbers
        if line.lower().startswith('n'):
            line = line[1:]
            while line[0].isdigit() or line[0] == '.':
                line = line[1:].lstrip()
                if not line:
                    break
        # check for a material edit
        if line.startswith('(o='):
            check_material_edit()
            # add comment for temporary material
            if line.startswith('(o=0'):
                lineNum += 1
                gcodeList.append(';temporay material #{}'.format(tmpMatNum))
            gcodeList.append(line)
            # add material change for temporary material
            if line.startswith('(o=0'):
                lineNum += 1
                gcodeList.append('m190 p{}'.format(tmpMatNum))
                lineNum += 1
                gcodeList.append('m66 p3 l3 q1')
                tmpMatNum += 1
            continue
        # if line is a comment then gcodeList.append it and get next line
        if line.startswith(';') or line.startswith('('):
            gcodeList.append(line)
            continue
        # if a ; comment at end of line, convert line to lower case and remove spaces, preserve comment as is
        elif ';' in line:
            a,b = line.split(';', 1)
            line = '{} ({})'.format(a.strip().lower().replace(' ',''),b.replace(';','').replace('(','').replace(')',''))
        # if a () comment at end of line, convert line to lower case and remove spaces, preserve comment as is
        elif '(' in line:
            a,b = line.split('(', 1)
            line = '{} ({})'.format(a.strip().lower().replace(' ',''),b.replace('(','').replace(')',''))
        # if any other line, convert line to lower case and remove spaces
        else:
            line = line.lower().replace(' ','')
        # remove leading 0's from G & M codes
        if (line.lower().startswith('g') or \
           line.lower().startswith('m')) and \
           len(line) > 2:
            while line[1] == '0' and len(line) > 2:
                if line[2].isdigit():
                    line = line[:1] + line[2:]
                else:
                    break
        # if incremental distance mode fix overburn coordinates
        if line[:2] in ['g0', 'g1'] and distMode == 91 and (oBurnX or oBurnY):
            line = fix_overburn_incremental_coordinates(line)
        # if z motion is to be kept
        if line.startswith('#<keep-z-motion>'):
            if '(' in line:
                keepZ = int(line.split('=')[1].split('(')[0])
            else:
                keepZ = int(line.split('=')[1])
            if keepZ == 1:
                zBypass = True
            else:
                zBypass = False
            gcodeList.append(line)
            continue
        # remove any additional z max moves
        if '[#<_ini[axis_z]max_limit>' in line and zSetup:
            continue
        # set initial Z height
        if not zSetup and not zBypass and ('g0' in line or 'g1' in line or 'm3' in line):
            offsetTopZ = (zMaxOffset * unitsPerMm * unitMultiplier)
            moveTopZ = 'g53 g0 z[#<_ini[axis_z]max_limit> * {} - {:.3f}] (Z just below max height)'.format(unitMultiplier, offsetTopZ)
            if not '[#<_ini[axis_z]max_limit>' in line:
                lineNum += 1
                gcodeList.append(moveTopZ)
            else:
                line = moveTopZ
            zSetup = True
        # set default units
        if 'g21' in line:
            if units == 'in':
                unitMultiplier = 25.4
                if not customDia:
                    minDiameter = 32
                if not customLen:
                    ocLength = 4
        elif 'g20' in line:
            if units == 'mm':
                unitMultiplier = 0.03937
                if not customDia:
                    minDiameter = 1.26
                if not customLen:
                    ocLength = 0.157
        # check for g41 or g42 offsets
        if 'g41' in line or 'g42' in line:
            offsetG4x = True
            if 'kerf_width-f]>' in line and unitMultiplier != 1:
                line = line.replace('#<_hal[qtplasmac.kerf_width-f]>', \
                                   '[#<_hal[qtplasmac.kerf_width-f]> * {}]'.format(unitMultiplier))
        # check for g4x offset cleared
        elif 'g40' in line:
            offsetG4x = False
        # are we scribing
        if line.startswith('m3$1s'):
            if pierceOnly:
                codeWarn = True
                warnPierceScribe.append(lineNum)
                scribing = False
            else:
                scribing = True
                gcodeList.append(line)
                continue
        # if pierce only mode
        if pierceOnly:
            # Don't pierce spotting operations
            if line.startswith('m3$2'):
                spotting = True
                gcodeList.append('(Ignoring spotting operation as pierce-only is active)')
                continue
            # Ignore spotting blocks when pierceOnly
            if spotting:
                if line.startswith('m5$2'):
                    spotting = False
                continue
            if line.startswith('g0'):
                rapidLine = line
                continue
            if line.startswith('m3') and not line.startswith('m3$1'):
                pierces += 1
                gcodeList.append('\n(Pierce #{})'.format(pierces))
                gcodeList.append(rapidLine)
                gcodeList.append('M3 $0 S1')
                gcodeList.append('G91')
                gcodeList.append('G1 X.000001')
                gcodeList.append('G90\nM5 $0')
                rapidLine = ''
                continue
            if not pierces or line.startswith('o') or line.startswith('#'):
                gcodeList.append(line)
            continue
        # test for pierce only mode
        if (line.startswith('#<pierce-only>') and line.split('=')[1][0] == '1') or (not pierceOnly and cutType == 1):
            if scribing:
                codeWarn = True
                warnPierceScribe.append(lineNum)
            else:
                pierceOnly = True
                pierces = 0
                rapidLine = ''
                gcodeList.append(line)
            if not cutType == 1:
                continue
        if line.startswith('#<oclength>'):
            if '(' in line:
                ocLength = float(line.split('=')[1].split('(')[0])
            else:
                ocLength = float(line.split('=')[1])
            customLen = True
            gcodeList.append(line)
            continue
        # if hole sensing code
        if line.startswith('#<holes>'):
            if '(' in line:
                set_hole_type(int(line.split('=')[1].split('(')[0]))
            else:
                set_hole_type(int(line.split('=')[1]))
            gcodeList.append(line)
            continue
        # if hole diameter command
        if line.startswith('#<h_diameter>') or line.startswith('#<m_diameter>') or line.startswith('#<i_diameter>'):
            if '(' in line:
                minDiameter = float(line.split('=')[1].split('(')[0])
                customDia = True
            else:
                minDiameter = float(line.split('=')[1])
                customDia = True
            gcodeList.append(line)
            if '#<m_d' in line or '#<i_d' in line:
                codeWarn = True
                warnUnitsDep.append(lineNum)
            continue
        # if hole velocity command
        if line.startswith('#<h_velocity>'):
            if '(' in line:
                holeVelocity = float(line.split('=')[1].split('(')[0])
            else:
                holeVelocity = float(line.split('=')[1])
            gcodeList.append(line)
            continue
        # if material change
        if line.startswith('m190'):
            do_material_change()
            if not 'm66' in line:
                continue
        # wait for material change
        if 'm66' in line:
            if offsetG4x:
                codeError = True
                errorCompMat.append(lineNum)
            gcodeList.append(line)
            continue
        # set arc modes
        if 'g90' in line and not 'g90.' in line:
            distMode = 90 # absolute distance mode
        if 'g91' in line and not 'g91.' in line:
            distMode = 91 # incremental distance mode
        if 'g90.1' in line:
            arcDistMode = 90.1 # absolute arc distance mode
        if 'g91.1' in line:
            arcDistMode = 91.1 # incremental arc distance mode
        if not zBypass:
            # if z axis in line
            if 'z' in line and line.split('z')[1][0] in '0123456789.- ':
                # if no other axes comment it
                if 1 not in [c in line for c in 'xybcuvw']:
                    if '(' in line:
                        gcodeList.append('({} {}'.format(line.split('(')[0], line.split('(')[1]))
                    elif ';' in line:
                        gcodeList.append('({} {}'.format(line.split(';')[0], line.split(';')[1]))
                    else:
                        gcodeList.append('({})'.format(line))
                    continue
                # other axes in line, comment out the Z axis
                if not '(z' in line:
                    if holeEnable and ('x' in line or 'y' in line):
                        lastX, lastY = set_last_coordinates(lastX, lastY)
                    result = comment_out_z_commands()
                    gcodeList.append(result)
                    continue
        # if an arc command
        if (line.startswith('g2') or line.startswith('g3')) and line[2].isalpha():
            if holeEnable:
                # check if we can read the values correctly
                if 'x' in line: check_math('x')
                if 'y' in line: check_math('y')
                if 'i' in line: check_math('i')
                if 'j' in line: check_math('j')
                check_if_hole()
            else:
                gcodeList.append(line)
            continue
        # if torch off, flag it then gcodeList.append it
        if line.startswith('m62p3') or line.startswith('m64p3'):
            torchEnable = False
            gcodeList.append(line)
            continue
        # if torch on, flag it then gcodeList.append it
        if line.startswith('m63p3') or line.startswith('m65p3'):
            torchEnable = True
            gcodeList.append(line)
            continue
        # if spindle off
        if line.startswith('m5'):
            if len(line) == 2 or (len(line) > 2 and not line[2].isdigit()):
                gcodeList.append(line)
                # restore velocity if required
                if holeActive:
                    lineNum += 1
                    gcodeList.append('m68 e3 q0 (arc complete, velocity 100%)')
                    holeActive = False
                # if torch off, allow torch on
                if not torchEnable:
                    lineNum += 1
                    gcodeList.append('m65 p3 (enable torch)')
                    torchEnable = True
            else:
                gcodeList.append(line)
            continue
        # if program end
        if line.startswith('m2') or line.startswith('m30') or line.startswith('%'):
            # restore velocity if required
            if holeActive:
                lineNum += 1
                gcodeList.append('m68 e3 q0 (arc complete, velocity 100%)')
                holeActive = False
            # if torch off, allow torch on
            if not torchEnable:
                lineNum += 1
                gcodeList.append('m65 p3 (enable torch)')
                torchEnable = True
            # restore hole sensing to default
            if holeEnable:
                lineNum += 1
                gcodeList.append('(disable hole sensing)')
                holeEnable = False
            if firstMaterial:
                RUN(['halcmd', 'setp', 'qtplasmac.material_change_number', '{}'.format(firstMaterial)])
            gcodeList.append(line)
            continue
        # check feed rate
        if 'f' in line:
            line = check_f_word(line)
        # restore velocity if required
        if holeActive:
            lineNum += 1
            gcodeList.append('m67 e3 q0 (arc complete, velocity 100%)')
            holeActive = False
        # set last X/Y position
        if holeEnable and len(line) and ('x' in line or 'y' in line):
            lastX, lastY = set_last_coordinates(lastX, lastY)
        gcodeList.append(line)

# for pierce only mode
if pierceOnly:
    gcodeList.append('')
    if rapidLine:
        gcodeList.append('{}'.format(rapidLine))
    gcodeList.append('M2 (END)')

# warning notification
if codeWarn:
    if warnUnitsDep:
        msg  = '\n<m_diameter> and #<i_diameter> are deprecated in favour of #<h_diameter>.\n'
        msg += 'The diameter will be set in the current units of the G-Code file.\n'
        warnings += message_set(warnUnitsDep, msg)
    if warnPierceScribe:
        msg  = '\nPierce only mode is invalid while scribing.\n'
        warnings += message_set(warnPierceScribe, msg)
    if warnMatLoad:
        msg  = '\nMaterials were not reloaded in a timely manner.\n'
        msg  = 'Try reloading the G-Code file.\n'
        warnings += message_set(warnMatLoad, msg)
    if warnHoleDir:
        msg  = '\nThis cut appears to be a hole, did you mean to cut it clockwise?\n'
        warnings += message_set(warnHoleDir, msg)
    if warnCompTorch:
        msg  = '\nCannot enable/disable torch with G41/G42 compensation active.\n'
        warnings += message_set(warnCompTorch, msg)
    if warnCompVel:
        msg  = '\nCannot reduce velocity with G41/G42 compensation active.\n'
        warnings += message_set(warnCompVel, msg)
    if warnFeed:
        warnings += '\n'
        for n in range(0, len(warnFeed)):
            msg0 = 'Line'
            msg1 = 'does not match Material'
            msg2 = 'feed rate of '
            warnings += '{} {:0.0f}: F{} {}_{}\'s {} {:0.0f}\n'.format(msg0, warnFeed[n][0], warnFeed[n][1], msg1, warnFeed[n][2], msg2, warnFeed[n][3])
    dialog_box('G-CODE WARNING', warnings, Qt.AlignLeft)

# error notification
if codeError:
    if errorMath:
        msg  = '\nG2 and G3 moves require explicit values if hole sensing is enabled.\n'
        errors += message_set(errorMath, msg)
    if errorMissMat:
        msg  = '\nThe Material selected is missing from the material file.\n'
        errors += message_set(errorMissMat, msg)
    if errorTempMat:
        msg  = '\nError attempting to add a temporary material.\n'
        errors += message_set(errorTempMat, msg)
    if errorNewMat:
        msg  = '\nCannot add new material, number is in use.\n'
        errors += message_set(errorNewMat, msg)
    if errorEditMat:
        msg  = '\nCannot add or edit material from G-Code file with invalid parameter or value.\n'
        errors += message_set(errorEditMat, msg)
    if errorWriteMat:
        msg  = '\nError attempting to write to the material file.\n'
        errors += message_set(errorWriteMat, msg)
    if errorReadMat:
        msg  = '\nError attempting to read from the material file.\n'
        errors += message_set(errorReadMat, msg)
    if errorCompMat:
        msg  = '\nCannot validate a material change with cutter compensation active.\n'
        errors += message_set(errorCompMat, msg)
    dialog_box('G-CODE ERROR', errors, Qt.AlignLeft)
    print('M2 (end program)')

# output the finalised g-code
for line in gcodeList:
    print(line)
