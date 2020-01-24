import os
import time
import unittest
import subprocess
import sys


@unittest.skipIf(os.name != 'nt', reason='Windows installer tests must be run on Windows.')
def test_it():
    try:
        subprocess.check_call(['certbot', '--version'])
    except (subprocess.CalledProcessError, OSError):
        pass
    else:
        raise AssertionError('Expect certbot to not be available in the PATH.')

    root_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

    try:
        # Build the installer
        subprocess.check_call([sys.executable, os.path.join(root_path, 'windows-installer', 'construct.py')])

        # Install certbot
        subprocess.check_call([os.path.join(root_path, 'windows-installer', 'build', 'nsis', 'certbot-beta-installer-win32.exe'), '/S'])

        # Assert certbot is installed and runnable
        output = subprocess.check_output(['certbot', '--version'], universal_newlines=True)
        assert 'certbot 1.' in output, 'Flag --version does not output a version.'

        # Assert renew task is installed and ready
        output = _ps('(Get-ScheduledTask -TaskName "Certbot Renew & Auto-Update Task").State', capture_stdout=True)
        assert output.strip() == 'Ready'

        # Assert renew task is working
        now = time.time()
        _ps('Start-ScheduledTask -TaskName "Certbot Renew & Auto-Update Task"')

        status = 'Running'
        while status != 'Ready':
            status = _ps('(Get-ScheduledTask -TaskName "Certbot Renew & Auto-Update Task").State', capture_stdout=True).strip()
            time.sleep(1)

        log_path = os.path.join('C:\\', 'Certbot', 'log', 'letsencrypt.log')

        modification_time = os.path.getmtime(log_path)
        assert now < modification_time, 'Certbot log file has not been modified by the renew task.'

        with open(log_path) as file_h:
            data = file_h.read()
        assert 'DEBUG:certbot._internal.renewal:no renewal failures' in data, 'Renew task did not execute properly.'

    finally:
        # Sadly this command cannot work in non interactive mode: uninstaller will ask explicitly permission in an UAC prompt
        # print('Uninstalling Certbot ...')
        # uninstall_path = _ps('(gci "HKLM:\\SOFTWARE\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall"'
        #                      ' | foreach { gp $_.PSPath }'
        #                      ' | ? { $_ -match "Certbot" }'
        #                      ' | select UninstallString)'
        #                      '.UninstallString', capture_stdout=True)
        # subprocess.check_call([uninstall_path, '/S'])
        pass


def _ps(powershell_str, capture_stdout=False):
    fn = subprocess.check_output if capture_stdout else subprocess.check_call
    return fn(['powershell.exe', '-c', powershell_str], universal_newlines=True)