#
from nipype.interfaces.fsl import Slicer
from nipype.interfaces.fsl import SwapDimensions
import xml.etree.ElementTree as ET
import os.path as path
import pyxnat as xnat
from PIL import Image
import tempfile
import argparse
import urllib3
import glob
import os

urllib3.disable_warnings()


def getinterface(url, user, passwd):
    """
    Create and test a connection to XNAT and returns the a pyxnat interface
    object
    :param url: xnat url as a string
    :param user: xnat username as a string
    :param passwd: xnat password as a string
    "return: pyxnat interface object
    """
    # Remove the last '/' to avoid requests issue
    if url.endswith('/'):
        url = url[:-1]
    # Create the interface
    intf = xnat.Interface(server=url,
                          user=user,
                          password=passwd,
                          verify=False)
    try:
        intf._exec('/data/JSESSION', method='DELETE')
    except:
        raise ValueError('Unable to connect to XNAT')
    else:
        try:
            intf.manage.schemas.add('schemas/xnat.xsd')
        except:
            raise ValueError('Unable to download XNAT schema')
    return intf


def getscaninfo(scan_info_file):
    """
    Extract the metadata information from the provide xml file
    :param scan_info_file: xml filename
    :return: dictionary containing scan metadata
    """
    # Read the xml file to extract information
    tree = ET.parse(scan_info_file[0])
    root = tree.getroot()

    scan_info = dict()

    # Extract subject data
    scan_info['subject_id'] = root.find(".//*subjectIdentifier").text
    scan_info['APOEA1'] = root.find(".//*[@item='APOE A1']").text
    scan_info['APOEA2'] = root.find(".//*[@item='APOE A2']").text
    if root.find(".//*subjectSex").text == "M":
        scan_info['gender'] = 'Male'
    else:
        scan_info['gender'] = 'Female'

    # Extract session data
    scan_info['session_id'] = root.find(".//*seriesIdentifier").text
    scan_info['date'] = root.find(".//*dateAcquired").text
    scan_info['age'] = root.find(".//*subjectAge").text
    scan_info['site'] = root.find(".//*siteKey").text
    scan_info['manufacturer'] = root.find(".//*[@term='Manufacturer']").text
    scan_info['scanner'] = root.find(".//*[@term='Mfg Model']").text
    scan_info['modality'] = root.find(".//*modality").text
    scan_info['fieldStrength'] = root.find(".//*[@term='Field Strength']").text
    scan_info['coil'] = root.find(".//*[@term='Coil']").text
    scan_info['visittype'] = root.find(".//*visitIdentifier").text
    scan_info['clinicalgroup'] = root.find(".//*researchGroup").text
    if root.find(".//*[@attribute='mmse']") is not None:
        scan_info['mmse'] = root.find(".//*[@attribute='MMSCORE']").text
    else:
        scan_info['mmse'] = 'Unknown'
    if root.find(".//*[@attribute='cdr']") is not None:
        scan_info['cdr'] = root.find(".//*[@attribute='CDGLOBAL']").text
    else:
        scan_info['cdr'] = 'Unknown'
    if root.find(".//*[@attribute='gds']") is not None:
        scan_info['gds'] = root.find(".//*[@attribute='GDTOTAL']").text
    else:
        scan_info['gds'] = 'Unknown'
    if root.find(".//*[@attribute='faq']") is not None:
        scan_info['faq'] = root.find(".//*[@attribute='FAQTOTAL']").text
    else:
        scan_info['faq'] = 'Unknown'
    if root.find(".//*[@attribute='NPISCORE']") is not None:
        scan_info['npi'] = root.find(".//*[@attribute='NPISCORE']").text
    else:
        scan_info['npi'] = 'Unknown'

    # Extract the scan info
    scan_info['type'] = root.find(".//*[@term='Weighting']").text
    scan_info['series_description'] = root.find(".//*processedDataLabel").text
    scan_info['tr'] = root.find(".//*[@term='TR']").text
    scan_info['ti'] = root.find(".//*[@term='TE']").text
    scan_info['te'] = root.find(".//*[@term='TI']").text
    scan_info['flip'] = int(float(root.find(".//*[@term='Flip Angle']").text))
    scan_info['scanSequence'] = root.find(".//*[@term='Pulse Sequence']").text
    scan_info['units'] = 'mm'
    scan_info['resx'] = root.find(".//*[@term='Pixel Spacing X']").text
    scan_info['resy'] = root.find(".//*[@term='Pixel Spacing Y']").text
    scan_info['resz'] = root.find(".//*[@term='Slice Thickness']").text
    scan_info['nx'] = int(float(root.find(".//*[@term='Matrix X']").text))
    scan_info['ny'] = int(float(root.find(".//*[@term='Matrix Y']").text))
    scan_info['nz'] = int(float(root.find(".//*[@term='Matrix Z']").text))
    scan_info['acqType'] = root.find(".//*[@term='Acquisition Plane']").text

    return scan_info


if __name__ == '__main__':
    # Parser to set default values for xnat url and credentials
    parser = argparse.ArgumentParser()
    parser.add_argument('xnat_url',
                        help='Default XNAT instance URL',
                        type=str)
    parser.add_argument('xnat_user',
                        help='Default XNAT username',
                        type=str)
    parser.add_argument('xnat_pwd',
                        help='Default XNAT password',
                        type=str)
    parser.add_argument('input_path',
                        help='Path to the folder containing the ADNI data',
                        type=str)
    parser.add_argument('-p', '--project',
                        help='XNAT project where the data will be uploaded',
                        type=str,
                        default='ADNI')
    parser.add_argument('-o', '--output-path',
                        help='Default path to save files',
                        type=str,
                        default=tempfile.gettempdir())
    args = parser.parse_args()

    # # Check the xnat credentials
    intf = getinterface(args.xnat_url,
                        args.xnat_user,
                        args.xnat_pwd)

    # Check all the locally available scans
    all_scans = glob.glob(
        '/'.join([args.input_path, 'ADNI', '*', '*', '*', '*', '*.nii.gz']))
    if len(all_scans) == 0:
        raise ValueError('No Nifti files in the specified path')
    else:
        print('Number of nifti files: {}'.format(len(all_scans)))

    # Connect to the ADNI project
    project = intf.select.project(args.project)

    # Iterate over all scan files
    for scan_file in all_scans:

        # Extract the metadata information
        scan_id = path.basename(scan_file).removesuffix(
            '.nii.gz').split('_')[-1]
        scan_info_file = glob.glob(
            '/'.join([args.input_path, 'ADNI', '*' + scan_id + '.xml']))
        if not len(scan_info_file) == 1:
            raise ValueError('To many info file for scan ' + scan_id)
        scan_info = getscaninfo(scan_info_file)

        # Create the subject on xnat if needed
        subject = project.subject(scan_info['subject_id'])
        experiment = subject.experiment(scan_info['subject_id'] + '_' +
                                        scan_info['session_id'])
        scan = experiment.scan(str(scan_id[1:]))

        if scan.exists():
            continue

        if not subject.exists():
            print('Subject started ' + scan_info['subject_id'])
            subject.insert()
            subject.attrs.mset({
                'xnat:subjectData/fields/field[name=apoe1]/field':
                    scan_info['APOEA1'],
                'xnat:subjectData/fields/field[name=apoe2]/field':
                    scan_info['APOEA2'],
                'xnat:subjectData/demographics'
                '[@xsi:type=xnat:demographicData]/gender': scan_info['gender']
            })
            print('Subject created ' + scan_info['subject_id'])

        # Create the experiment on xnat if needed
        if not experiment.exists():
            print('Session started ' +
                  scan_info['subject_id'] + '_' + scan_info['session_id'])
            experiment.insert(**{
                'experiments': 'xnat:mrSessionData',
                'xnat:mrSessionData/date': scan_info['date'],
                'xnat:mrSessionData/age': scan_info['age'],
                'xnat:mrSessionData/acquisition_site': scan_info['site'],
                'xnat:mrSessionData/scanner/manufacturer':
                    scan_info['manufacturer'],
                'xnat:mrSessionData/scanner':
                    scan_info['manufacturer'] + '_' + scan_info['scanner'],
                'xnat:mrSessionData/scanner/model': scan_info['scanner'],
                'xnat:mrSessionData/modality': scan_info['modality'],
                'xnat:mrSessionData/fieldStrength': scan_info['fieldStrength'],
                'xnat:mrSessionData/coil': scan_info['coil'],
                'xnat:mrSessionData/session_type': scan_info['visittype'],
            })
            experiment.attrs.mset({
                'xnat:mrSessionData/fields/field[name=visittype]/field':
                    scan_info['visittype'],
                'xnat:mrSessionData/fields/field[name=clinicalgroup]/field':
                    scan_info['clinicalgroup'],
                'xnat:mrSessionData/fields/field[name=mmse]/field':
                    scan_info['mmse'],
                'xnat:mrSessionData/fields/field[name=cdr]/field':
                    scan_info['cdr'],
                'xnat:mrSessionData/fields/field[name=gds]/field':
                    scan_info['gds'],
                'xnat:mrSessionData/fields/field[name=faq]/field':
                    scan_info['faq'],
                'xnat:mrSessionData/fields/field[name=npi]/field':
                    scan_info['npi'],
            })
            print('Session created ' +
                  scan_info['subject_id'] + '_' + scan_info['session_id'])

        # Create the scan on xnat if needed
        scan = experiment.scan(str(scan_id[1:]))
        if scan.exists() is False:
            print('Scan started ' + scan_id[1:])
            scan.insert(**{
                'scans': 'xnat:mrScanData',
                'xnat:mrScanData/type': scan_info['type'],
                'xnat:mrScanData/series_description':
                    scan_info['series_description'],
                'xnat:mrScanData/scanner/manufacturer':
                    scan_info['manufacturer'],
                'xnat:mrScanData/scanner/model': scan_info['scanner'],
                'xnat:mrScanData/modality': scan_info['modality'],
                'xnat:mrScanData/fieldStrength': scan_info['fieldStrength'],
                'xnat:mrScanData/parameters/tr': scan_info['tr'],
                'xnat:mrScanData/parameters/ti': scan_info['ti'],
                'xnat:mrScanData/parameters/te': scan_info['te'],
                'xnat:mrScanData/parameters/flip': scan_info['flip'],
                'xnat:mrSessionData/coil': scan_info['coil'],
                'xnat:mrScanData/parameters/scanSequence':
                    scan_info['scanSequence'],
                'xnat:mrScanData/parameters/voxelRes/units': 'mm',
                'xnat:mrScanData/parameters/voxelRes/x': scan_info['resx'],
                'xnat:mrScanData/parameters/voxelRes/y': scan_info['resy'],
                'xnat:mrScanData/parameters/voxelRes/z': scan_info['resz'],
                'xnat:mrScanData/parameters/matrix/x': scan_info['nx'],
                'xnat:mrScanData/parameters/matrix/y': scan_info['ny'],
                'xnat:mrScanData/frames': int(float(scan_info['nz'])),
                'xnat:mrScanData/parameters/acqType': scan_info['acqType'],
            })
            print('Scan created ' + scan_id[1:])

        # Upload the data
        nii = scan.resource('NIFTI')
        if not nii.exists():
            scan.resource('NIFTI').file(path.basename(scan_file)).put(
                scan_file, 'NII', 'PROCESSED')
            scan.resource('NIFTI').file(path.basename(scan_info_file[0])).put(
                scan_info_file[0], 'XML')
            print('Data uploaded ' + scan_file)

        # Create a snapshot

        snap = scan.resource('SNAPSHOTS')
        if not snap.exists():

            filename_swap = tempfile.gettempdir() + os.sep + \
                            scan_info['subject_id'] + '_' + \
                            scan_info['session_id'] + '_' + \
                            scan_id[1:] + '._s.nii.gz'
            filename_snap = tempfile.gettempdir() + os.sep + \
                            scan_info['subject_id'] + '_' + \
                            scan_info['session_id'] + '_' + \
                            scan_id[1:] + '.png'
            filename_thumb = tempfile.gettempdir() + os.sep + \
                             scan_info['subject_id'] + '_' + \
                             scan_info['session_id'] + '_' + \
                             scan_id[1:] + '_t.png'

            swapdim = SwapDimensions(command='fsl5.0-fslswapdim')
            slicer_snap = Slicer(command='fsl5.0-slicer')

            try:
                swapdim.inputs.new_dims = ('LR', 'PA', 'IS')
                swapdim.inputs.in_file = scan_file
                swapdim.inputs.out_file = filename_swap
                swapdim.run()

                slicer_snap.inputs.in_file = filename_swap
                slicer_snap.inputs.out_file = filename_snap
                slicer_snap.inputs.middle_slices = True
                slicer_snap.run()

                snap.file(path.basename(filename_snap)).put(
                    filename_snap, 'PNG', 'ORIGINAL')
                thumbnail = Image.open(filename_snap)
                thumbnail.thumbnail((300, 300))
                thumbnail.save(filename_thumb)
                snap.file(path.basename(filename_thumb)).put(
                    filename_thumb, 'PNG', 'THUMBNAIL')
            except:
                pass
            os.remove(swapdim.inputs.out_file)
            os.remove(filename_snap)
            os.remove(filename_thumb)

    # Disconnect the xnat interface
    intf.disconnect()
