import pyxnat as xnat
import pandas as pd
import argparse
import requests
import urllib3

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
    parser.add_argument('-p', '--project',
                        help='XNAT project where the data will be uploaded',
                        type=str,
                        default='ADNI')
    requests.session().close()
    args = parser.parse_args()

    # # Check the xnat credentials
    intf = getinterface(args.xnat_url,
                        args.xnat_user,
                        args.xnat_pwd)

    # Extract information about the mrSessionsData
    info = intf.select('xnat:mrSessionData',
                       ['xnat:mrSessionData/SESSION_ID',
                        'xnat:mrSessionData/PROJECT',
                        'xnat:mrSessionData/SCANNER',
                        'xnat:mrSessionData/SUBJECT_ID',
                        'xnat:mrSessionData/VISIT',
                        'xnat:mrSessionData/TYPE',
                        'xnat:mrSessionData/'
                        'XNAT_COL_MRSESSIONDATAFIELDSTRENGTH']
                       ).all()
    intf.disconnect()

    # Store the data in a pandas DataFrame
    raw_data = pd.DataFrame(info)
    raw_data = raw_data[raw_data['project'] == args.project]

    print('List of visit types:')
    for v in set(raw_data['type']):
        print('- ' + v)

    # Select only the baseline sessions
    baseline = raw_data[(raw_data['type'] == 'ADNI Screening') |
                        (raw_data['type'] == 'ADNI Baseline')]
    scanner_types = dict()
    scan_number = [0, 0]
    scanner_number = [0, 0]
    siemens_number = [0, 0]
    ge_number = [0, 0]
    philips_number = [0, 0]
    subject_list = []
    for i, r in baseline.iterrows():
        if r['subject_id'] in subject_list:
            continue
        subject_list.append(r['subject_id'])
        site = r['session_id'].split('_')[0]
        strength = r['xnat_col_mrsessiondatafieldstrength']
        scanner = r['scanner'] + ' ' + strength
        strength = 0 if float(strength) < 2 else 1
        if site not in scanner_types.keys():
            scanner_types[site] = dict()
        if scanner not in scanner_types[site].keys():
            scanner_types[site][scanner] = 0
            scanner_number[strength] += 1
        scanner_types[site][scanner] += 1
        scan_number[strength] += 1
        if 'SIEMENS' in scanner.upper():
            siemens_number[strength] += 1
        elif 'GE' in scanner.upper():
            ge_number[strength] += 1
        elif 'PHILIPS' in scanner.upper():
            philips_number[strength] += 1
    print(scanner_types)
    print('Number of unique site = {}'.format(len(scanner_types.keys())))
    print('Number of scanner = {} ({}/{})'.format(sum(scanner_number),
                                                  scanner_number[0],
                                                  scanner_number[1]))
    print('Total number of scans = {} ({}/{})'.format(sum(scan_number),
                                                      scan_number[0],
                                                      scan_number[1]))
    print('Number of siemens scans = {} ({}/{})'.format(sum(siemens_number),
                                                        siemens_number[0],
                                                        siemens_number[1]))
    print('Number of ge scans = {} ({}/{})'.format(sum(ge_number),
                                                   ge_number[0],
                                                   ge_number[1]))
    print('Number of philips scans = {} ({}/{})'.format(sum(philips_number),
                                                        philips_number[0],
                                                        philips_number[1]))
