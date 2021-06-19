from PyQt5 import QtWidgets, QtCore
from PyQt5.QtGui import QPixmap
import pyxnat as xnat
import argparse
import requests
import tempfile
import urllib3
import glob
import time
import sys
import os

urllib3.disable_warnings()


class XNATLogin(QtWidgets.QDialog):
    """
    Window dialog to collect the XNAT login information
    """
    def __init__(self,
                 parent=None,
                 xnat_server='',
                 username='',
                 password=''
                 ):
        """

        :param parent:
        :param xnat_server: Default value to use for the xnat server url
        :param username: Default username
        :param password: Default password
        """
        super(XNATLogin, self).__init__(parent)
        # Dialog for xnat server input
        promptServer = QtWidgets.QLabel(self)
        promptServer.setText('XNAT Server URL:')
        self.textServer = QtWidgets.QLineEdit(self)
        self.textServer.setText(xnat_server)

        # Dialog for xnat username input
        promptUser = QtWidgets.QLabel(self)
        promptUser.setText('XNAT username:')
        self.textUser = QtWidgets.QLineEdit(self)
        self.textUser.setText(username)

        # Dialog for xnat password input
        promptPass = QtWidgets.QLabel(self)
        promptPass.setText('XNAT password:')
        self.textPass = QtWidgets.QLineEdit(self)
        self.textPass.setText(password)
        self.textPass.setEchoMode(QtWidgets.QLineEdit.Password)

        # Define a button to submit the information
        buttonLogin = QtWidgets.QPushButton('Login', self)
        buttonLogin.clicked.connect(self.handlelogin)

        # Set the layout
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(promptServer)
        layout.addWidget(self.textServer)
        layout.addWidget(promptUser)
        layout.addWidget(self.textUser)
        layout.addWidget(promptPass)
        layout.addWidget(self.textPass)
        layout.addWidget(buttonLogin)

    def handlelogin(self):
        """
        Check whether the provided url and credential are functional
        :return:
        """
        # remove the trailing '/' if needed
        if self.textServer.text().endswith('/'):
            self.textServer.setText(self.textServer.text()[:-1])
        anonymous = False
        if self.textUser.text() == '':
            anonymous = True
        self.interface = xnat.Interface(server=self.textServer.text(),
                                        user=self.textUser.text(),
                                        password=self.textPass.text(),
                                        verify=False,
                                        anonymous=anonymous)
        try:
            self.interface._exec('/data/JSESSION', method='DELETE')
        except:
            QtWidgets.QMessageBox.warning(
                self, 'Error', 'Unable to connect to XNAT')
        else:
            try:
                self.interface.manage.schemas.add('schemas/xnat.xsd')
            except:
                QtWidgets.QMessageBox.warning(
                    self, 'Error', 'Unable to download the XNAT schemas')
            self.accept()
            self.interface.disconnect()

    def getinterface(self):
        """
        Return the XNAT interface details
        :return: pyxnat interface object
        """
        return self.interface


class XNATSelectProjectPatient(QtWidgets.QDialog):
    """
    Window dialog to select the project and patient
    """
    def __init__(self,
                 parent=None,
                 interface=None):
        super(XNATSelectProjectPatient, self).__init__(parent)

        self.retrievexnatinfo(interface)

        promptProject = QtWidgets.QLabel(self)
        promptProject.setText('Select the XNAT project')
        self.boxProject = QtWidgets.QComboBox(self)
        for project in self.subject_data.keys():
            self.boxProject.addItem(project)
        self.boxProject.currentIndexChanged.connect(self.updatesubjectlist)

        promptSubject = QtWidgets.QLabel(self)
        promptSubject.setText('Select the XNAT subject')
        self.boxSubject = QtWidgets.QComboBox(self)
        self.updatesubjectlist()

        buttonSelect = QtWidgets.QPushButton('Select', self)
        buttonSelect.clicked.connect(self.handleselect)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(promptProject)
        layout.addWidget(self.boxProject)
        layout.addWidget(promptSubject)
        layout.addWidget(self.boxSubject)
        layout.addWidget(buttonSelect)

    def retrievexnatinfo(self, interface):
        """
        Retrive the patients and project labels from XNAT and
        store them into a dictionary where the project are the
        keys and the patients are the associated values
        :param interface: pyxnat interface object
        """
        raw_data = interface.select('xnat:subjectData').all()
        interface.disconnect()
        self.subject_data = {}
        for s in raw_data:
            project = s['project']
            subject = s['xnat_col_subjectdatalabel']
            if project in self.subject_data.keys():
                self.subject_data[project].append(subject)
            else:
                self.subject_data[project] = list()
                self.subject_data[project].append(subject)
        for p in self.subject_data.keys():
            self.subject_data[p].sort()

    def handleselect(self):
        """
        Closes the dialog when the button is clicked
        """
        self.accept()

    def updatesubjectlist(self):
        """
        Update the subject list combo box with the currently
        selected project
        """
        self.boxSubject.clear()
        for subject in self.subject_data[self.getproject()]:
            self.boxSubject.addItem(subject)

    def getproject(self):
        """
        Selected project getter
        :return: string containing the project label
        """
        return self.boxProject.currentText()

    def getsubject(self):
        """
        Selected subject getter
        :return: string containing the subject label
        """
        return self.boxSubject.currentText()


class ScanDisplayAndSaveWindow(QtWidgets.QDialog):
    """
    Dialog to display snapshot for selected scan
    """
    def __init__(self,
                 parent=None,
                 interface=None,
                 project=None,
                 subject=None,
                 output_path=''):
        """
        Main dialog to select and display scan snapshots
        :param parent:
        :param interface: pyxnat interface object
        :param project: string containing the xnat project id
        :param subject: string containing the xnat subject id
        """
        super(ScanDisplayAndSaveWindow, self).__init__(parent)
        # Retrieve a list of all xnat:mrSessionData type
        all_mr_sessions = interface.inspect.field_values(
            'xnat:mrSessionData/SESSION_ID')
        self.intf = interface
        self.proj = project
        self.subj = subject
        self.out = output_path
        # Extract a list of all experiments that are xnat:mrSessionData
        # for the selected subject
        experiment_ids = [e for e in self.intf.select.project(
            project).subject(subject).experiments().get()
                          if e in all_mr_sessions]
        if len(experiment_ids) == 0:
            QtWidgets.QMessageBox.warning(
                self, 'Error', 'This patient does not have any mrSessionData')
            self.close()
        # Store metadata information about all scans of all xnat:mrSessionData
        # into a dictionary. Moved to a requests call rather than pyxnat as to
        # limit the number of rest call and thus gain time
        self.mr_sessions = dict()
        reqSession = requests.session()
        for e in experiment_ids:
            url = self.intf._server + '/data/experiments/' + e + '?format=json'
            r = reqSession.get(url,
                               verify=False,
                               auth=(self.intf._user,
                                     self.intf._pwd))
            exp_json = r.json()
            # Extract some session information
            label = exp_json['items'][0]['data_fields']['label']
            date = exp_json['items'][0]['data_fields']['date']

            self.mr_sessions[e] = {'label': label,
                                   'date': date,
                                   'scanIds': []}

            # Iterate through children to find the scans
            for c in exp_json['items'][0]['children']:
                if c['field'] == 'scans/scan':
                    for s in c['items']:
                        scan_quality = s['data_fields']['quality']
                        scan_id = s['data_fields']['ID']
                        scan_type = s['data_fields']['type']

                        if not scan_id == '99':
                            self.mr_sessions[e]['scanIds'].append(scan_id)
                            self.mr_sessions[e][scan_id] = {
                                'type': scan_type,
                                'quality': scan_quality
                            }
        reqSession.close()

        # Create dialogs to select the session and display related
        # information
        promptSession = QtWidgets.QLabel(self)
        promptSession.setText('Select a session')
        self.boxSession = QtWidgets.QComboBox(self)
        for session in sorted(self.mr_sessions.keys()):
            self.boxSession.addItem(self.mr_sessions[session]['label'])
        self.boxSession.currentIndexChanged.connect(self.updateScanList)
        self.sessionDate = QtWidgets.QLabel(self)

        # Create dialogs to select the scan and display related information
        promptScan = QtWidgets.QLabel(self)
        promptScan.setText('Select a scan')
        self.boxScan = QtWidgets.QComboBox(self)
        self.boxScan.currentIndexChanged.connect(self.updateScanDetails)
        self.scanType = QtWidgets.QLabel(self)
        self.scanQuality = QtWidgets.QLabel(self)
        # Create a box to display the snapshots of selected scan
        self.boxImage = QtWidgets.QLabel(self)
        self.imgSize = (400, 400)
        self.boxImage.setFixedSize(self.imgSize[0], self.imgSize[1])

        promptType = QtWidgets.QLabel(self)
        promptType.setText('Image file format to save')
        self.boxType = QtWidgets.QComboBox(self)
        self.boxType.currentIndexChanged.connect(self.updateDefaultFilename)

        self.promptFilename = QtWidgets.QLabel(self)
        self.textFilename = QtWidgets.QLineEdit(self)

        # Create a button to save the file
        buttonSave = QtWidgets.QPushButton('Save file', self)
        buttonSave.clicked.connect(self.handleSave)

        # Create a button to close the window
        buttonClose = QtWidgets.QPushButton('Close', self)
        buttonClose.clicked.connect(self.handleClose)

        layout = QtWidgets.QVBoxLayout(self)

        layout.addWidget(promptSession)
        layout.addWidget(self.boxSession)
        layout.addWidget(self.sessionDate)

        layout.addWidget(promptScan)
        layout.addWidget(self.boxScan)
        layout.addWidget(self.scanType)
        layout.addWidget(self.scanQuality)
        layout.addWidget(self.boxImage)

        layout.addWidget(promptType)
        layout.addWidget(self.boxType)
        layout.addWidget(self.promptFilename)
        layout.addWidget(self.textFilename)

        layout.addWidget(buttonSave)
        layout.addWidget(buttonClose)

        self.updateScanList()

        self.start = time.time()

    def handleClose(self):
        """
        Display the time spent on this window,
        delete all downloaded snapshots and disconnect
        the pyxnat interface
        """
        end = time.time()
        print('Time it took to submit ' + str(end - self.start) + ' second(s)')
        for session_id in self.mr_sessions.keys():
            for f in glob.glob(tempfile.gettempdir() + os.sep +
                               'img_' + session_id + '_*.gif'):
                os.remove(f)
        self.intf.disconnect()
        self.close()

    def handleSave(self):
        """

        """
        session_id = self.getCurrentSessionId()
        scan_id = self.boxScan.currentText().split(' -')[0]
        scan = self.intf.select.experiment(session_id).scan(scan_id)
        if self.boxType.currentText() == 'NIFTI':
            # Ensure the filename contain .gz suffix if the source is gzipped
            filename = scan.resource('NIFTI').files('*.nii*')[0].label()
            self.textFilename.text().strip('.gz')
            self.textFilename.text().strip('.nii')
            self.textFilename.setText(self.textFilename.text() + '.nii')
            if '.nii.gz' in filename:
                self.textFilename.setText(self.textFilename.text() + '.gz')
            # Save the file
            scan.resource('NIFTI').files('*.nii*')[0].get(
                self.textFilename.text()
            )
        if self.boxType.currentText() == 'DICOM':
            scan.resource('DICOM').get(
                self.textFilename.text()
            )

    def getCurrentSessionId(self):
        """
        Retrieve the currently selected session id
        :return: string containing the selected session id
        """
        session_id = self.boxSession.currentText()
        for s in self.mr_sessions.keys():
            if self.mr_sessions[s]['label'] == session_id:
                session_id = s
                break
        return session_id

    def updateScanList(self):
        """
        Update the list of scan in the relevant combo box
        when a different session is selected
        """
        self.boxScan.clear()
        session_id = self.getCurrentSessionId()
        if session_id == '':
            return
        for scan_id in self.mr_sessions[session_id]['scanIds']:
            self.boxScan.addItem(scan_id + ' - ' +
                                 self.mr_sessions[session_id][scan_id]['type'])
        self.sessionDate.setText('Session Date: ' +
                                 self.mr_sessions[session_id]['date'])

    def updateScanDetails(self):
        """
        Update the scan details and snapshot
        when a different scan is selected
        """
        session_id = self.getCurrentSessionId()
        scan_id = self.boxScan.currentText().split(' -')[0]
        # The following statement ensures that no information
        # is retrieve when the box is empty
        # This occurs when the box is cleared to be updated.
        if scan_id == '':
            return
        # Update the display scan metadata
        self.scanType.setText('Scan Type: ' +
                              self.mr_sessions[
                                  session_id][scan_id]['type'])
        self.scanQuality.setText('Scan Type: ' +
                                 self.mr_sessions[
                                     session_id][scan_id]['quality'])

        # # Check the available resources
        self.boxType.clear()
        scan = self.intf.select.experiment(session_id).scan(scan_id)
        no_file = True
        if scan.resource('NIFTI').exists():
            no_file = False
            self.boxType.addItem('NIFTI')
        if scan.resource('DICOM').exists():
            no_file = False
            self.boxType.addItem('DICOM')
        if no_file:
            self.boxImage.clear()
            QtWidgets.QMessageBox.warning(
                self, 'Error', 'No Nifti or Dicom files for this scan')
            return

        # Download locally the scan's snapshot if it has not been previously
        # downloaded
        img_filename = tempfile.gettempdir() + os.sep +\
                       'img_' + session_id + '_' + scan_id + '.gif'
        if not os.path.exists(img_filename):
            # Here used direclty the rest call as did not manage with pyxnat
            url = [self.intf._server + '/xapi/experiments/' + session_id + \
                   '/scan/' + scan_id + '/snapshot/3X3',
                   self.intf._server + '/xapi/experiments/' + session_id + \
                   '/scan/' + scan_id + '/snapshot']
            for u in url:
                print('Retrieve snapshot: ' + u)
                r = requests.get(u,
                                 verify=False,
                                 auth=(self.intf._user,
                                       self.intf._pwd))
                with open(img_filename, 'wb') as f:
                    f.write(r.content)
                r.close()
                # Display the snapshot
                pixmap = QPixmap(img_filename)
                if not pixmap.isNull():
                    break
        if pixmap.isNull():
            QtWidgets.QMessageBox.warning(
                self, 'Error', 'Unable to retrieve snapshot. is XNAT v1.7.x?')
        else:
            self.boxImage.setPixmap(pixmap.scaled(self.imgSize[0],
                                                  self.imgSize[1],
                                                  QtCore.Qt.KeepAspectRatio))


    def updateDefaultFilename(self):
        """
        Update the default filename based on selected image type
        """
        session_id = self.getCurrentSessionId()
        scan_id = self.boxScan.currentText().split(' -')[0]
        scan = self.intf.select.experiment(session_id).scan(scan_id)
        if self.boxType.currentText() == 'NIFTI':
            self.promptFilename.setText('Save the file as:')
            filename = scan.resource('NIFTI').files('*.nii*')[0].label()
            self.textFilename.setText(
                self.out + os.sep + filename
            )
        if self.boxType.currentText() == 'DICOM':
            self.promptFilename.setText(
                'Save DICOM.zip in the following folder:')
            self.textFilename.setText(
                self.out
            )


if __name__ == '__main__':

    # Parser to set default values for xnat url and credentials
    parser = argparse.ArgumentParser()
    parser.add_argument('-x', '--xnat-url',
                        help='Default XNAT instance URL',
                        type=str,
                        default='')
    parser.add_argument('-u', '--xnat-user',
                        help='Default XNAT username',
                        type=str,
                        default='')
    parser.add_argument('-p', '--xnat-pwd',
                        help='Default XNAT password',
                        type=str,
                        default='')
    parser.add_argument('-o', '--output-path',
                        help='Default path to save files',
                        type=str,
                        default=tempfile.gettempdir())
    args = parser.parse_args()

    app = QtWidgets.QApplication(sys.argv)

    login = XNATLogin(xnat_server=args.xnat_url,
                      username=args.xnat_user,
                      password=args.xnat_pwd)
    if login.exec_() == QtWidgets.QDialog.Accepted:
        print('Successful connection to the XNAT server')

    xnat_project_subject = XNATSelectProjectPatient(
        interface=login.getinterface())
    if xnat_project_subject.exec_() == QtWidgets.QDialog.Accepted:
        print('Project has been selected:' + xnat_project_subject.getproject())
        print('Subject has been selected:' + xnat_project_subject.getsubject())

    window = ScanDisplayAndSaveWindow(
        interface=login.getinterface(),
        project=xnat_project_subject.getproject(),
        subject=xnat_project_subject.getsubject(),
        output_path=args.output_path
    )
    window.show()
    sys.exit(app.exec_())
