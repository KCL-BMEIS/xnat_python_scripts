from PyQt5 import QtWidgets, QtCore
from PyQt5.QtGui import QPixmap
import pyxnat as xnat
import argparse
import requests
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
        self.interface = xnat.Interface(server=self.textServer.text(),
                                        user=self.textUser.text(),
                                        password=self.textPass.text(),
                                        verify=False)
        try:
            self.interface.manage.schemas.add('schemas/xnat.xsd')
            self.interface._exec('/data/JSESSION', method='DELETE')
        except:
            QtWidgets.QMessageBox.warning(
                self, 'Error', 'Unable to connect to XNAT')
        else:
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


class DataEntryWindow(QtWidgets.QDialog):
    """
    Dialog to display snapshot for selected scan
    """
    def __init__(self,
                 parent=None,
                 interface=None,
                 project=None,
                 subject=None):
        """
        Main dialog to select and display scan snapshots
        :param parent:
        :param interface: pyxnat interface object
        :param project: string containing the xnat project id
        :param subject: string containing the xnat subject id
        """
        super(DataEntryWindow, self).__init__(parent)
        # Retrieve a list of all xnat:mrSessionData type
        all_mr_sessions = interface.inspect.field_values(
            'xnat:mrSessionData/SESSION_ID')
        self.intf = interface
        self.proj = project
        self.subj = subject
        # Extract a list of all experiments that are xnat:mrSessionData
        # for the selected subject
        experiment_ids = [e for e in self.intf.select.project(
            project).subject(subject).experiments().get()
                          if e in all_mr_sessions]
        # Store metadata information about all scans of all xnat:mrSessionData
        # into a dictionary
        self.mr_sessions = dict()
        for e in experiment_ids:
            exp = interface.select.project(project).subject(
                subject).experiment(e)
            label, date = exp.attrs.mget([
                'xnat:mrSessionData/label',
                'xnat:mrSessionData/date',
            ])
            scan_ids = exp.scans().get()
            if '99' in scan_ids:
                scan_ids.remove('99')
            self.mr_sessions[e] = {'label': label,
                              'date': date,
                              'scanIds': scan_ids}
            for sc in scan_ids:
                quality, scan_type = interface.select.project(
                    project).subject(
                    subject).experiment(e).scan(sc).attrs.mget([
                    'xnat:mrScanData/quality',
                    'xnat:mrScanData/type',
                ])
                self.mr_sessions[e][sc] = {'type': scan_type, 'quality': quality}

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

        # Create a buttom to close the window
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
            for f in glob.glob('/tmp/img_' + session_id + '_*.gif'):
                os.remove(f)
        self.intf.disconnect()
        self.close()

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
        # The following statement ensures that no information is retrieve when the box is empty
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

        # Download locally the scan's snapshot if it has not been previously
        # downloaded
        img_filename = '/tmp/img_' + session_id + '_' + scan_id + '.gif'
        if not os.path.exists(img_filename):
            # Here used direclty the rest call as did not manage with pyxnat
            url = self.intf._server + '/xapi/experiments/' + session_id +\
                  '/scan/' + scan_id + '/snapshot/3X3'
            print('Retrieve snapshot: ' + url)
            r = requests.get(url,
                             verify=False,
                             auth=(self.intf._user, self.intf._pwd))
            with open(img_filename, 'wb') as f:
                f.write(r.content)
            r.close()
        # Display the snapshot
        pixmap = QPixmap(img_filename)
        self.boxImage.setPixmap(pixmap.scaled(self.imgSize[0], self.imgSize[1],
                                              QtCore.Qt.KeepAspectRatio))

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

    window = DataEntryWindow(
        interface=login.getinterface(),
        project=xnat_project_subject.getproject(),
        subject=xnat_project_subject.getsubject()
    )
    window.show()
    sys.exit(app.exec_())
